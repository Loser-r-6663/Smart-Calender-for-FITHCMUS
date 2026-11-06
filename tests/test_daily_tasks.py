import unittest
from datetime import date
from unittest.mock import Mock

from Database import api
from Database.daily_tasks import DailyTaskRepository


class FakeCursor:
    def __init__(self, row=None, rows=None, rowcount=1):
        self.row = row
        self.rows = rows or []
        self.rowcount = rowcount
        self.query = ""
        self.params = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.query = " ".join(query.split())
        self.params = params

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor

    def cursor(self, cursor_factory=None):
        return self.fake_cursor


class DailyTaskRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.work_date = date(2026, 11, 3)
        self.cursor = FakeCursor(
            row={
                "user_id": 7,
                "work_date": self.work_date,
                "task_id": "task-1",
                "is_completed_today": True,
            },
            rows=[
                {
                    "user_id": 7,
                    "work_date": self.work_date,
                    "task_id": "task-1",
                    "is_completed_today": True,
                }
            ],
        )
        self.connection = FakeConnection(self.cursor)
        self.repository = DailyTaskRepository()

    def test_upsert_key_and_values_include_user(self):
        result = self.repository.set_for_date(
            self.connection, 7, self.work_date, "task-1", True
        )

        self.assertIn("ON CONFLICT (user_id, work_date, task_id)", self.cursor.query)
        self.assertEqual(self.cursor.params, (7, self.work_date, "task-1", True))
        self.assertEqual(result["user_id"], 7)

    def test_daily_read_is_scoped_to_user_and_date(self):
        result = self.repository.get_for_user_date(
            self.connection, 7, self.work_date
        )

        self.assertIn(
            "WHERE daily_tasks.user_id = %s AND daily_tasks.work_date = %s",
            self.cursor.query,
        )
        self.assertEqual(self.cursor.params, (7, self.work_date))
        self.assertEqual(result[0]["user_id"], 7)

    def test_completion_update_is_scoped_to_user(self):
        self.repository.set_completion(
            self.connection, 7, self.work_date, "task-1", True
        )

        self.assertIn(
            "WHERE user_id = %s AND work_date = %s AND task_id = %s",
            self.cursor.query,
        )
        self.assertEqual(self.cursor.params, (True, 7, self.work_date, "task-1"))

    def test_delete_is_scoped_to_user(self):
        self.assertTrue(
            self.repository.remove(self.connection, 7, self.work_date, "task-1")
        )

        self.assertIn(
            "WHERE user_id = %s AND work_date = %s AND task_id = %s",
            self.cursor.query,
        )
        self.assertEqual(self.cursor.params, (7, self.work_date, "task-1"))


class DailyTaskApiTests(unittest.TestCase):
    def test_daily_task_routes_are_user_scoped(self):
        paths = api.app.openapi()["paths"]

        self.assertIn(
            "/users/{user_id}/daily-tasks/{work_date}/{task_id}", paths
        )
        self.assertIn(
            "/users/{user_id}/daily-tasks/{work_date}/{task_id}/completion",
            paths,
        )
        self.assertNotIn("/daily-tasks/{work_date}/{task_id}", paths)

    def test_api_reads_daily_tasks_for_requested_user(self):
        manager = Mock()
        manager.get_tasks_by_date.return_value = [{"user_id": 7}]
        work_date = date(2026, 11, 3)

        result = api.get_daily_tasks(
            work_date=work_date, user_id=7, database=manager
        )

        manager.get_tasks_by_date.assert_called_once_with(7, work_date)
        self.assertEqual(result, [{"user_id": 7}])

    def test_api_passes_user_id_to_database_manager(self):
        manager = Mock()
        manager.set_daily_task.return_value = {"user_id": 7}
        manager.set_daily_task_completion.return_value = {"user_id": 7}
        manager.remove_daily_task.return_value = True
        work_date = date(2026, 11, 3)

        api.set_daily_task(
            work_date,
            "task-1",
            api.DailyTaskUpdate(is_completed_today=True),
            user_id=7,
            database=manager,
        )
        api.set_daily_task_completion(
            work_date,
            "task-1",
            api.CompletionUpdate(is_completed=True),
            user_id=7,
            database=manager,
        )
        api.remove_daily_task(
            work_date, "task-1", user_id=7, database=manager
        )

        manager.set_daily_task.assert_called_once_with(7, work_date, "task-1", True)
        manager.set_daily_task_completion.assert_called_once_with(
            7, work_date, "task-1", True
        )
        manager.remove_daily_task.assert_called_once_with(7, work_date, "task-1")


if __name__ == "__main__":
    unittest.main()
