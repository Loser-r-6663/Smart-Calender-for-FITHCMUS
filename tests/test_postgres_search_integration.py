"""Opt-in SELECT-only checks against a dedicated, already populated database."""
import os
import unittest

from academic_search import SearchService


@unittest.skipUnless(
    os.getenv("RUN_SEARCH_POSTGRES_INTEGRATION") == "1",
    "Requires an explicitly configured dedicated PostgreSQL test database.",
)
class PostgreSQLSearchIntegrationTests(unittest.TestCase):
    def test_existing_assigned_task_lookup_and_filters(self):
        from Database.DatabaseManager import DatabaseManager

        user_id = int(os.environ["SEARCH_TEST_USER_ID"])
        task_id = os.environ["SEARCH_TEST_TASK_ID"]
        manager = DatabaseManager()
        try:
            manager.connection.set_session(isolation_level="REPEATABLE READ", readonly=True)
            search = SearchService(manager, user_id=user_id)
            task = search.get_task_by_id(task_id)
            self.assertIsNotNone(task, "The configured task must already be assigned to the test user.")
            rows = search.search_tasks({"filters": {"types": [task["type"]],
                                                     "statuses": [task["status"]]}, "limit": 1})
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["type"], task["type"])
            self.assertEqual(rows[0]["status"], task["status"])
            self.assertTrue(all(row["status"] == "active" for row in search.search_tasks({})))
        finally:
            manager.connection.rollback()
            manager.close()


if __name__ == "__main__":
    unittest.main()
