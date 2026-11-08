"""Offline checks for local sample targets, data, ownership and connection injection."""
import contextlib
import io
import os
import sys
import unittest
from unittest.mock import MagicMock, Mock, patch

from academic_search import SearchDatabaseError, SearchService, SearchValidationError
from academic_search.postgres import TASK_FIELDS
from search_sample.__main__ import (OWNER_TAG, SCHEMA_HASH, demo, main, owned_schema,
                                    reset, sample_target, schema_source, seed)
from search_sample.data import OWNER, OTHER, owner_for, sample_tasks
from search_sample.examples import ACTIVE_IDS, EXAMPLES
from test_postgres_search import Cursor, record


class SampleTests(unittest.TestCase):
    def settings(self):
        return {"SEARCH_SAMPLE_DB_HOST": "127.0.0.1", "SEARCH_SAMPLE_DB_NAME": "calendar_sample_search_test",
                "SEARCH_SAMPLE_DB_USER": "search_sample", "SEARCH_SAMPLE_DB_PASSWORD": "local-test-secret",
                "SEARCH_SAMPLE_DB_PORT": "55432", "SEARCH_SAMPLE_DB_CONFIRM": "calendar_sample_search_test"}

    def connection(self):
        target = sample_target(self.settings())
        connection = MagicMock()
        connection.autocommit = False
        connection.get_dsn_parameters.return_value = {"host": target.host, "port": str(target.port)}
        cursor = connection.cursor.return_value.__enter__.return_value
        return target, connection, cursor

    def test_requires_separate_explicit_local_target(self):
        for settings in ({}, {"DB_HOST": "localhost", "DB_NAME": "team", "DB_PASSWORD": "secret"},
                         {**self.settings(), "SEARCH_SAMPLE_DB_HOST": "remote.example.invalid"},
                         {**self.settings(), "SEARCH_SAMPLE_DB_CONFIRM": "wrong"},
                         {**self.settings(), "SEARCH_SAMPLE_DB_NAME": "task_manager_db"}):
            with self.assertRaises(RuntimeError):
                sample_target(settings)
        self.assertNotIn("local-test-secret", repr(sample_target(self.settings())))
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as caught:
            main(["demo"])
        self.assertEqual(caught.exception.code, 2)

    def test_schema_snapshot_preserves_reviewed_constraints_and_relations(self):
        source = schema_source()
        self.assertIn("training_points INT NOT NULL DEFAULT 0", source)
        self.assertIn("updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP", source)
        self.assertIn("REFERENCES tasks(id) ON DELETE CASCADE", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_tasks", source)
        self.assertIn("CONSTRAINT tasks_deadline_required", source)

    def test_write_commands_refuse_autocommit_before_accessing_the_target(self):
        target, connection, cursor = self.connection()
        connection.autocommit = True
        for operation in (seed, reset):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(RuntimeError, "autocommit"):
                operation(connection, target)
        cursor.execute.assert_not_called()

    def test_data_is_fixed_valid_and_covers_text_points_types_and_scope(self):
        tasks = sample_tasks()
        self.assertEqual(tasks, sample_tasks())
        self.assertEqual(len(tasks), 45)
        self.assertEqual(len({task["id"] for task in tasks}), 45)
        self.assertEqual({task["type"] for task in tasks}, {"class", "assignment", "exam", "event", "personal", "tuition"})
        self.assertTrue({0, 5, 7, 10} <= {task["training_points"] for task in tasks})
        self.assertEqual(sum(owner_for(task["id"]) == OTHER for task in tasks), 1)
        self.assertEqual(owner_for("sample-other-private"), OTHER)
        for task in tasks:
            self.assertEqual(set(task), set(TASK_FIELDS))
            self.assertTrue(1 <= len(task["id"]) <= 64)
            self.assertIs(type(task["training_points"]), int)
            self.assertIsNotNone(task["updated_at"].utcoffset())
            if task["training_points"] > 0:
                self.assertIsNotNone(task["drl_category"])
            if task["type"] in {"assignment", "tuition"}:
                self.assertIsNotNone(task["deadline"])
            for start, end in (("start_time", "end_time"), ("registration_start", "registration_end")):
                if task[start] is not None and task[end] is not None:
                    self.assertLess(task[start], task[end])
        visible = [task for task in tasks if owner_for(task["id"]) == OWNER and task["status"] == "active"]
        self.assertEqual(sorted(task["id"] for task in visible), ACTIVE_IDS)
        text_ids = sorted(task["id"] for task in visible if all(
            term in task["title"].casefold() or term in (task["description"] or "").casefold()
            for term in ("tình", "nguyện")))
        self.assertEqual(text_ids, ["sample-cross-field", "sample-description-only", "sample-title-only"])
        self.assertEqual(EXAMPLES[3][2], text_ids)

    def test_borrowed_connection_uses_real_service_without_a_manager_or_lifetime_changes(self):
        connection = Mock()
        cursor = Cursor()
        cursor.fetchall.return_value = [record()]
        connection.cursor.return_value = cursor
        search = SearchService.from_connection(connection, user_id=1)
        self.assertIsNone(search.database_manager)
        self.assertEqual([row["id"] for row in search.search_tasks({"keyword": "Search"})], ["Task_é 1"])
        self.assertIn("ILIKE", cursor.execute.call_args.args[0])
        cursor.execute.side_effect = RuntimeError("server unavailable")
        with self.assertRaises(SearchDatabaseError):
            search.get_task_by_id("Task_1")
        self.assertEqual([call[0] for call in connection.mock_calls], ["cursor", "cursor"])
        with self.assertRaises(SearchValidationError):
            SearchService.from_connection(connection, user_id=True)

    def test_seed_is_conflict_safe_and_existing_seed_does_not_apply_schema_again(self):
        target, connection, cursor = self.connection()
        cursor.fetchone.side_effect = [(target.database, target.user), None,
                                      (1, "sample_owner@fixtures.example.invalid"),
                                      (2, "sample_other@fixtures.example.invalid"), (45,)]
        self.assertEqual(seed(connection, target), 45)
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(schema_source(), calls)
        self.assertIn("SET LOCAL search_path TO search_sample, pg_catalog", calls)
        inserts = [query for query in calls if query.startswith("INSERT INTO tasks")]
        self.assertEqual(len(inserts), 45)
        self.assertTrue(all("ON CONFLICT (id) DO NOTHING" in query for query in inserts))
        cursor.reset_mock()
        cursor.fetchone.side_effect = [(target.database, target.user), (target.user,), ("search_sample._sample_meta",),
                                      (1, "sample_owner@fixtures.example.invalid"),
                                      (2, "sample_other@fixtures.example.invalid"), (45,)]
        cursor.fetchall.return_value = [(OWNER_TAG, SCHEMA_HASH)]
        self.assertEqual(seed(connection, target), 45)
        calls = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertNotIn(schema_source(), calls)
        self.assertFalse(any(query.startswith("CREATE ") for query in calls))

    def test_unmarked_schema_and_wrong_owner_are_refused_before_writes(self):
        target, connection, cursor = self.connection()
        for responses in ([("other_role",)], [(target.user,), (None,)]):
            cursor.reset_mock()
            cursor.fetchone.side_effect = responses
            with self.assertRaises(RuntimeError):
                owned_schema(connection, target)
            self.assertTrue(all(call.args[0].startswith("SELECT ") for call in cursor.execute.call_args_list))
        cursor.fetchone.side_effect = [(target.database, target.user), None]
        cursor.reset_mock()
        with self.assertRaisesRegex(RuntimeError, "not initialized"), patch("search_sample.data.sample_tasks", side_effect=AssertionError("fixture load")):
            demo(connection, target)
        self.assertTrue(all(call.args[0].startswith("SELECT ") for call in cursor.execute.call_args_list))

    def test_reset_is_explicit_restrict_only_and_cli_rolls_back_failed_drops(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["reset"])
        target, connection, cursor = self.connection()
        cursor.fetchone.side_effect = [(target.database, target.user), (target.user,), ("search_sample._sample_meta",)]
        cursor.fetchall.return_value = [(OWNER_TAG, SCHEMA_HASH)]
        reset(connection, target)
        drops = [call.args[0] for call in cursor.execute.call_args_list if call.args[0].startswith("DROP ")]
        self.assertEqual(drops, [f"DROP TABLE search_sample.{name} RESTRICT" for name in
                                ("daily_tasks", "user_tasks", "tasks", "users", "_sample_meta")]
                         + ["DROP SCHEMA search_sample RESTRICT"])
        cursor.reset_mock()
        cursor.fetchone.side_effect = [(target.database, target.user), (target.user,), ("search_sample._sample_meta",)]
        def fail_drop(query, *args):
            if query == "DROP TABLE search_sample.tasks RESTRICT":
                raise RuntimeError("external dependency")

        cursor.execute.side_effect = fail_drop
        driver = Mock()
        driver.Error = Exception
        driver.connect.return_value = connection
        with patch.dict(os.environ, self.settings(), clear=True), patch.dict(sys.modules, {"psycopg2": driver}), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["reset", "--confirm-reset"])
        self.assertEqual(caught.exception.code, 1)
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        connection.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
