import os
import sys
import unittest
from datetime import date
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Database.database_manager import DatabaseManager
from Database.daily_task_objects import DailyTaskObject
from Database.task_objects import TaskObject
from Database.user_objects import UserObject, UserTaskObject


INTEGRATION_ENABLED = os.getenv("RUN_POSTGRES_INTEGRATION") == "1"


@unittest.skipUnless(
    INTEGRATION_ENABLED,
    "Set RUN_POSTGRES_INTEGRATION=1 to run tests against configured PostgreSQL.",
)
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_user_task_daily_task_crud_flow(self) -> None:
        database = DatabaseManager()
        token = uuid4().hex
        username = f"dbtest_{token[:16]}"
        email = f"dbtest_{token}@example.edu"
        task_id = f"dbtest-{token}"
        work_date = date.today()
        user_id: int | None = None
        task_created = False

        try:
            user = database.create_user(username, email, "Database integration test")
            user_id = user["id"]
            task = database.create_task(
                {
                    "id": task_id,
                    "title": f"Integration test {token[:8]}",
                    "type": "personal",
                    "course": "Database",
                }
            )
            task_created = True

            self.assertEqual(task["course"], "Database")
            self.assertTrue(database.assign_task(user_id, task_id))
            self.assertFalse(database.assign_task(user_id, task_id))

            scheduled = database.set_daily_task(work_date, task_id)
            self.assertEqual(scheduled["task_id"], task_id)
            self.assertFalse(scheduled["is_completed_today"])

            fetched_task = database.get_task(task_id)
            fetched_user = database.get_user(user_id)
            assigned_tasks = database.get_user_tasks(user_id)
            daily_tasks = database.get_tasks_by_date(user_id, work_date)

            self.assertIsInstance(fetched_task, TaskObject)
            self.assertIsInstance(fetched_user, UserObject)
            self.assertEqual(fetched_user.email, email)
            self.assertTrue(all(isinstance(item, UserTaskObject) for item in assigned_tasks))
            self.assertTrue(all(isinstance(item, DailyTaskObject) for item in daily_tasks))
            self.assertIn(task_id, [item.task_id for item in assigned_tasks])
            self.assertIn(task_id, [item.id for item in daily_tasks])

            completed = database.set_daily_task_completion(
                work_date, task_id, True
            )
            self.assertTrue(completed["is_completed_today"])

            daily_tasks = database.get_tasks_by_date(user_id, work_date)
            self.assertTrue(
                next(item for item in daily_tasks if item.id == task_id)
                .is_completed_today
            )

            updated_task = database.update_task(
                task_id, {"title": "Updated integration"}
            )
            self.assertEqual(updated_task["title"], "Updated integration")
            self.assertTrue(database.remove_daily_task(work_date, task_id))
            self.assertTrue(database.unassign_task(user_id, task_id))
            self.assertTrue(database.delete_task(task_id))
            task_created = False
            self.assertTrue(database.delete_user(user_id))
            user_id = None
        finally:
            if task_created:
                database.delete_task(task_id)
            if user_id is not None:
                database.delete_user(user_id)


if __name__ == "__main__":
    unittest.main()
