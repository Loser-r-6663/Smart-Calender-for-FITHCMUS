import sys
import unittest
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from psycopg2.sql import Composed

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.daily_tasks import DailyTaskRepository
from Database.task_config import TASK_DEFAULTS
from Database.task_validation import TaskData
from Database.tasks import TaskRepository
from Database.user_tasks import UserTaskRepository
from Database.users import UserRepository


class FakeCursor:
    def __init__(
        self,
        *,
        one: dict[str, Any] | None = None,
        many: list[dict[str, Any]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self.one = one
        self.many = many or []
        self.rowcount = rowcount
        self.executions: list[tuple[Any, tuple[Any, ...] | None]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def execute(self, query: Any, values: tuple[Any, ...] | None = None) -> None:
        self.executions.append((query, values))

    def fetchone(self) -> dict[str, Any] | None:
        return self.one

    def fetchall(self) -> list[dict[str, Any]]:
        return self.many


class FakeConnection:
    def __init__(self, *cursors: FakeCursor) -> None:
        self.cursors = deque(cursors)
        self.used_cursors: list[FakeCursor] = []

    def cursor(self, **_: Any) -> FakeCursor:
        cursor = self.cursors.popleft()
        self.used_cursors.append(cursor)
        return cursor


def task_record(**updates: Any) -> dict[str, Any]:
    values = {
        "id": "test-task",
        "title": "Test task",
        "type": "personal",
        **TASK_DEFAULTS,
        "updated_at": datetime(2026, 11, 7, tzinfo=timezone.utc),
    }
    values.update(updates)
    return TaskData.model_validate(values).model_dump()


class TaskRepositoryTests(unittest.TestCase):
    def test_create_inserts_all_fields_with_defaults(self) -> None:
        saved = task_record(course="Database")
        cursor = FakeCursor(one=saved)
        connection = FakeConnection(cursor)

        result = TaskRepository().create(
            connection,
            {"id": "test-task", "title": "Test task", "type": "personal", "course": "Database"},
        )

        self.assertEqual(result["course"], "Database")
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["source_platform"], "custom")
        query, values = cursor.executions[0]
        self.assertIsInstance(query, Composed)
        self.assertIn("INSERT INTO tasks", query.seq[0].string)
        self.assertEqual(len(values), len(task_record()))
        self.assertEqual(values[0], "test-task")

    def test_create_rejects_bad_data_before_opening_cursor(self) -> None:
        connection = FakeConnection()

        with self.assertRaises(ValueError):
            TaskRepository().create(
                connection,
                {"id": "bad-task", "title": "Bad task", "type": "personal", "course_code": "OLD"},
            )

        self.assertEqual(connection.used_cursors, [])

    def test_create_rejects_empty_data_before_opening_cursor(self) -> None:
        connection = FakeConnection()

        with self.assertRaises(ValueError):
            TaskRepository().create(connection, {})

        self.assertEqual(connection.used_cursors, [])

    def test_get_by_id_returns_record_or_none(self) -> None:
        record = task_record()
        found = TaskRepository().get_by_id(
            FakeConnection(FakeCursor(one=record)), "test-task"
        )
        missing = TaskRepository().get_by_id(
            FakeConnection(FakeCursor(one=None)), "missing"
        )

        self.assertEqual(found["id"], "test-task")
        self.assertIsNone(missing)

    def test_list_tasks_supports_optional_filters_and_rejects_invalid_values(self) -> None:
        def flatten_sql(node: Any) -> str:
            if hasattr(node, "string"):
                return node.string
            if hasattr(node, "seq"):
                return "".join(flatten_sql(part) for part in node.seq)
            return str(node)

        all_cursor = FakeCursor(many=[task_record(id="t1"), task_record(id="t2")])
        all_rows = TaskRepository().list_tasks(FakeConnection(all_cursor))
        self.assertEqual([row["id"] for row in all_rows], ["t1", "t2"])
        all_query, all_params = all_cursor.executions[0]
        self.assertIsInstance(all_query, Composed)
        self.assertEqual(all_params, ())
        self.assertNotIn("WHERE", flatten_sql(all_query))

        filtered_cursor = FakeCursor(many=[task_record(id="ev1", type="event")])
        filtered_rows = TaskRepository().list_tasks(
            FakeConnection(filtered_cursor), status="active", task_type="event"
        )
        self.assertEqual([row["id"] for row in filtered_rows], ["ev1"])
        filtered_query, filtered_params = filtered_cursor.executions[0]
        self.assertEqual(filtered_params, ("active", "event"))
        query_sql = flatten_sql(filtered_query)
        self.assertIn("WHERE", query_sql)
        self.assertIn("status = %s", query_sql)
        self.assertIn("type = %s", query_sql)

        bad_connection = FakeConnection()
        with self.assertRaises(ValueError):
            TaskRepository().list_tasks(bad_connection, status="invalid")
        self.assertEqual(bad_connection.used_cursors, [])

    def test_update_validates_merged_record_and_refreshes_timestamp(self) -> None:
        existing = task_record()
        updated = task_record(title="Updated")
        lookup_cursor = FakeCursor(one=existing)
        update_cursor = FakeCursor(one=updated)
        connection = FakeConnection(lookup_cursor, update_cursor)

        result = TaskRepository().update(
            connection, "test-task", {"title": "Updated"}
        )

        self.assertEqual(result["title"], "Updated")
        query = update_cursor.executions[0][0]
        self.assertIsInstance(query, Composed)
        self.assertIn("UPDATE tasks SET", query.seq[0].string)
        update_values = update_cursor.executions[0][1]
        self.assertEqual(update_values[0], "Updated")
        self.assertIsInstance(update_values[-2], datetime)
        self.assertEqual(update_values[-1], "test-task")

    def test_update_rejects_invalid_columns_and_immutable_id(self) -> None:
        repository = TaskRepository()

        with self.assertRaises(ValueError):
            repository.update(FakeConnection(), "test-task", {"course_code": "OLD"})
        with self.assertRaises(ValueError):
            repository.update(FakeConnection(), "test-task", {"id": "other"})

    def test_update_returns_existing_record_for_empty_updates(self) -> None:
        record = task_record()

        result = TaskRepository().update(
            FakeConnection(FakeCursor(one=record)), "test-task", {}
        )

        self.assertEqual(result["id"], "test-task")

    def test_update_missing_record_does_not_execute_update(self) -> None:
        lookup_cursor = FakeCursor(one=None)
        connection = FakeConnection(lookup_cursor)

        result = TaskRepository().update(
            connection, "missing", {"title": "Updated"}
        )

        self.assertIsNone(result)
        self.assertEqual(len(connection.used_cursors), 1)

    def test_update_rejects_invalid_merged_task_before_update(self) -> None:
        existing = task_record()
        lookup_cursor = FakeCursor(one=existing)
        connection = FakeConnection(lookup_cursor)

        with self.assertRaises(ValidationError):
            TaskRepository().update(
                connection, "test-task", {"type": "assignment"}
            )

        self.assertEqual(len(connection.used_cursors), 1)

    def test_delete_reports_whether_a_row_was_removed(self) -> None:
        repository = TaskRepository()

        self.assertTrue(
            repository.delete(
                FakeConnection(FakeCursor(rowcount=1)), "test-task"
            )
        )
        self.assertFalse(
            repository.delete(
                FakeConnection(FakeCursor(rowcount=0)), "missing"
            )
        )


class UserRepositoryTests(unittest.TestCase):
    def test_create_validates_and_returns_user_record(self) -> None:
        expected = {
            "id": 5,
            "username": "student",
            "email": "student@example.edu",
            "full_name": "Student",
        }
        cursor = FakeCursor(one=expected)

        result = UserRepository().create(
            FakeConnection(cursor), "student", "student@example.edu", "Student"
        )

        self.assertEqual(result, expected)
        self.assertEqual(
            cursor.executions[0][1],
            ("student", "student@example.edu", "Student"),
        )

    def test_create_rejects_invalid_email_before_database_write(self) -> None:
        connection = FakeConnection()

        with self.assertRaises(ValidationError):
            UserRepository().create(connection, "student", "not-an-email")

        self.assertEqual(connection.used_cursors, [])

    def test_update_validates_user_and_returns_none_for_missing_user(self) -> None:
        existing = {
            "id": 5,
            "username": "student",
            "email": "student@example.edu",
            "full_name": None,
        }
        lookup = FakeCursor(one=existing)
        update = FakeCursor(one={**existing, "username": "student-new"})
        result = UserRepository().update(
            FakeConnection(lookup, update), 5, {"username": "student-new"}
        )
        self.assertEqual(result["username"], "student-new")

        missing = UserRepository().update(
            FakeConnection(FakeCursor(one=None)), 99, {"username": "nobody"}
        )
        self.assertIsNone(missing)

    def test_get_by_id_and_delete(self) -> None:
        user = {
            "id": 5,
            "username": "student",
            "email": "student@example.edu",
            "full_name": None,
        }
        repository = UserRepository()

        self.assertEqual(
            repository.get_by_id(
                FakeConnection(FakeCursor(one=user)), 5
            ),
            user,
        )
        self.assertIsNone(
            repository.get_by_id(
                FakeConnection(FakeCursor(one=None)), 99
            )
        )
        self.assertTrue(
            repository.delete(FakeConnection(FakeCursor(rowcount=1)), 5)
        )
        self.assertFalse(
            repository.delete(FakeConnection(FakeCursor(rowcount=0)), 99)
        )

    def test_update_rejects_invalid_fields_and_user_data(self) -> None:
        repository = UserRepository()

        with self.assertRaises(ValueError):
            repository.update(FakeConnection(), 5, {"is_admin": True})

        existing = {
            "id": 5,
            "username": "student",
            "email": "student@example.edu",
            "full_name": None,
        }
        connection = FakeConnection(FakeCursor(one=existing))
        with self.assertRaises(ValidationError):
            repository.update(connection, 5, {"email": "invalid"})
        self.assertEqual(len(connection.used_cursors), 1)

    def test_empty_update_returns_current_user(self) -> None:
        user = {
            "id": 5,
            "username": "student",
            "email": "student@example.edu",
            "full_name": None,
        }

        result = UserRepository().update(
            FakeConnection(FakeCursor(one=user)), 5, {}
        )

        self.assertEqual(result, user)


class LinkRepositoryTests(unittest.TestCase):
    def test_user_task_assignment_listing_and_removal(self) -> None:
        assigned_at = datetime(2026, 11, 7, tzinfo=timezone.utc)
        row = {"user_id": 1, "task_id": "test-task", "assigned_at": assigned_at}
        repository = UserTaskRepository()

        self.assertTrue(
            repository.assign(
                FakeConnection(FakeCursor(one=row)), 1, "test-task"
            )
        )
        self.assertFalse(
            repository.assign(
                FakeConnection(FakeCursor(one=None)), 1, "test-task"
            )
        )
        self.assertEqual(
            repository.get_for_user(
                FakeConnection(FakeCursor(many=[row])), 1
            ),
            [row],
        )
        self.assertEqual(
            repository.get_for_task(
                FakeConnection(FakeCursor(many=[row])), "test-task"
            ),
            [row],
        )
        self.assertTrue(
            repository.unassign(
                FakeConnection(FakeCursor(rowcount=1)), 1, "test-task"
            )
        )
        self.assertFalse(
            repository.unassign(
                FakeConnection(FakeCursor(rowcount=0)), 1, "test-task"
            )
        )

    def test_daily_task_upsert_completion_and_removal(self) -> None:
        work_date = date(2026, 11, 7)
        row = {
            "work_date": work_date,
            "task_id": "test-task",
            "is_completed_today": True,
        }
        repository = DailyTaskRepository()

        self.assertEqual(
            repository.set_for_date(
                FakeConnection(FakeCursor(one=row)),
                work_date,
                "test-task",
                True,
            ),
            row,
        )
        self.assertEqual(
            repository.get_for_user_date(
                FakeConnection(FakeCursor(many=[task_record()])),
                1,
                work_date,
            ),
            [task_record()],
        )
        self.assertEqual(
            repository.set_completion(
                FakeConnection(FakeCursor(one=row)),
                work_date,
                "test-task",
                True,
            ),
            row,
        )
        self.assertIsNone(
            repository.set_completion(
                FakeConnection(FakeCursor(one=None)),
                work_date,
                "missing",
                True,
            )
        )
        self.assertTrue(
            repository.remove(
                FakeConnection(FakeCursor(rowcount=1)), work_date, "test-task"
            )
        )
        self.assertFalse(
            repository.remove(
                FakeConnection(FakeCursor(rowcount=0)), work_date, "missing"
            )
        )


if __name__ == "__main__":
    unittest.main()
