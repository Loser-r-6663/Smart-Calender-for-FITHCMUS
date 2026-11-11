import sys
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.database_manager import DatabaseManager
from Database.daily_task_objects import DailyTaskObject
from Database.task_objects import TaskObject
from Database.user_objects import UserObject, UserTaskObject
from Database.db_connection import DatabaseConnection


class TransactionConnection:
    def __init__(self) -> None:
        self.commit = Mock()
        self.rollback = Mock()
        self.close = Mock()


class DatabaseConnectionTests(unittest.TestCase):
    def test_transaction_commits_and_closes_on_success(self) -> None:
        raw_connection = TransactionConnection()

        with patch.object(
            DatabaseConnection, "connect", return_value=raw_connection
        ):
            with DatabaseConnection().transaction() as connection:
                self.assertIs(connection, raw_connection)

        raw_connection.commit.assert_called_once_with()
        raw_connection.rollback.assert_not_called()
        raw_connection.close.assert_called_once_with()

    def test_transaction_rolls_back_and_closes_on_error(self) -> None:
        raw_connection = TransactionConnection()

        with patch.object(
            DatabaseConnection, "connect", return_value=raw_connection
        ):
            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                with DatabaseConnection().transaction():
                    raise RuntimeError("operation failed")

        raw_connection.commit.assert_not_called()
        raw_connection.rollback.assert_called_once_with()
        raw_connection.close.assert_called_once_with()


class DatabaseManagerTests(unittest.TestCase):
    def test_get_methods_convert_records_to_result_objects(self) -> None:
        timestamp = datetime(2026, 11, 7, tzinfo=timezone.utc)
        task_record = {
            "id": "test-task",
            "title": "Test task",
            "type": "personal",
            "course": None,
            "description": None,
            "target_audience": None,
            "location": None,
            "registration_start": None,
            "registration_end": None,
            "start_time": None,
            "end_time": None,
            "deadline": None,
            "estimated_hours": None,
            "training_points": 0,
            "drl_category": None,
            "recurrence": None,
            "status": "active",
            "is_manual": False,
            "source_url": None,
            "source_platform": "custom",
            "updated_at": timestamp,
        }
        user_record = {
            "id": 1,
            "username": "student",
            "email": "student@example.edu",
            "full_name": None,
        }
        user_task_record = {
            "user_id": 1,
            "task_id": "test-task",
            "assigned_at": timestamp,
        }
        daily_task_record = {
            **task_record,
            "work_date": "2026-11-07",
            "is_completed_today": False,
        }
        transaction_connection = object()

        @contextmanager
        def transaction():
            yield transaction_connection

        database = Mock()
        database.transaction = transaction
        manager = DatabaseManager(database=database)
        manager.tasks.get_by_id = Mock(return_value=task_record)
        manager.tasks.list_tasks = Mock(return_value=[task_record])
        manager.users.get_by_id = Mock(return_value=user_record)
        manager.user_tasks.get_for_user = Mock(return_value=[user_task_record])
        manager.daily_tasks.get_for_user_date = Mock(
            return_value=[daily_task_record]
        )

        task = manager.get_task("test-task")
        tasks = manager.list_tasks(status="active", task_type="personal")
        user = manager.get_user(1)
        assignments = manager.get_user_tasks(1)
        daily_tasks = manager.get_tasks_by_date(1, datetime(2026, 11, 7).date())

        self.assertIsInstance(task, TaskObject)
        self.assertEqual(len(tasks), 1)
        self.assertIsInstance(tasks[0], TaskObject)
        self.assertEqual(tasks[0].id, "test-task")
        self.assertIsInstance(user, UserObject)
        self.assertEqual(len(assignments), 1)
        self.assertIsInstance(assignments[0], UserTaskObject)
        self.assertEqual(len(daily_tasks), 1)
        self.assertIsInstance(daily_tasks[0], DailyTaskObject)
        self.assertEqual(daily_tasks[0].work_date.isoformat(), "2026-11-07")

        manager.tasks.get_by_id.assert_called_once_with(
            transaction_connection, "test-task"
        )
        manager.tasks.list_tasks.assert_called_once_with(
            transaction_connection, "active", "personal"
        )


if __name__ == "__main__":
    unittest.main()
