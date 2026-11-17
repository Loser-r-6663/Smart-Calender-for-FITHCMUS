"""Offline checks of target refusal, source guards and test-fixture adaptation."""
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from postgres_search_support import (REVIEWED_FILES, adapt_request, adapt_task,
                                     read_fixture, read_test_target, reviewed_schema,
                                     validate_live_target)


class PostgreSQLSetupTests(unittest.TestCase):
    def settings(self):
        return {"SEARCH_TEST_DB_HOST": "localhost", "SEARCH_TEST_DB_NAME": "calendar_search_test",
                "SEARCH_TEST_DB_USER": "search_tester", "SEARCH_TEST_DB_PASSWORD": "private-test-value",
                "SEARCH_TEST_DB_PORT": "5432", "SEARCH_TEST_DB_CONFIRM": "calendar_search_test"}

    def test_no_application_configuration_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "Explicit SEARCH_TEST_DB"):
            read_test_target({"DB_HOST": "localhost", "DB_NAME": "task_manager_db", "DB_USER": "postgres",
                              "DB_PASSWORD": "application-secret", "DB_PORT": "5432"})
        for key in self.settings():
            settings = self.settings()
            settings.pop(key)
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                read_test_target(settings)

    def test_database_name_confirmation_and_port_guards(self):
        for name in ("postgres", "template1", "task_manager_db", "calendar_dev", "bad-search_test"):
            settings = self.settings()
            settings.update(SEARCH_TEST_DB_NAME=name, SEARCH_TEST_DB_CONFIRM=name)
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                read_test_target(settings)
        settings = self.settings()
        settings["SEARCH_TEST_DB_CONFIRM"] = "different_search_test"
        with self.assertRaisesRegex(RuntimeError, "exactly match"):
            read_test_target(settings)
        for value in ("bad", "0", "65536"):
            settings = self.settings()
            settings["SEARCH_TEST_DB_PORT"] = value
            with self.subTest(port=value), self.assertRaises(RuntimeError):
                read_test_target(settings)
        target = read_test_target(self.settings())
        self.assertEqual(target.database, "calendar_search_test")
        self.assertEqual(target.port, 5432)
        self.assertNotIn("private-test-value", repr(target))

    def test_connected_identity_is_checked_before_mutations(self):
        target = read_test_target(self.settings())
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (target.database, target.user)
        connection.get_dsn_parameters.return_value = {"host": target.host, "port": "5432"}
        validate_live_target(connection, target)
        self.assertEqual(cursor.execute.call_args.args, ("SELECT current_database(), session_user",))
        for identity in (("task_manager_db", target.user), (target.database, "other_user")):
            cursor.fetchone.return_value = identity
            with self.subTest(identity=identity), self.assertRaisesRegex(RuntimeError, "Connected target"):
                validate_live_target(connection, target)
        cursor.fetchone.return_value = (target.database, target.user)
        connection.get_dsn_parameters.return_value = {"host": "other-host", "port": "5432"}
        with self.assertRaises(RuntimeError):
            validate_live_target(connection, target)
        self.assertTrue(all(call.args[0].startswith("SELECT ") for call in cursor.execute.call_args_list))

    def test_reviewed_source_guard_normalizes_line_endings_and_refuses_drift(self):
        source = "-- reviewed test SQL\nSELECT 1;\n"
        digest = hashlib.sha256(source.encode()).hexdigest()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(Path(__file__).resolve().parent))
            path = Path(directory) / "Db_query.sql"
            path.write_bytes(source.replace("\n", "\r\n").encode())
            with patch.dict(REVIEWED_FILES, {"Db_query.sql": digest}, clear=True):
                self.assertEqual(reviewed_schema(Path(directory)), source)
                path.write_text("-- unreviewed\n", encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "Review Database/Db_query.sql"):
                    reviewed_schema(Path(directory))

    def test_cleanup_refuses_unowned_or_unexpected_schemas_without_database_access(self):
        from test_postgres_search_integration import PostgreSQLSearchIntegrationTests

        case = PostgreSQLSearchIntegrationTests("test_lookup_defaults_all_types_and_missing")
        case.connection = MagicMock()
        case.schema_created = False
        case.drop_schema()
        case.schema_created = True
        for name in ("public", "search_it_", "search_it_not_a_uuid"):
            case.schema = name
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "unexpected schema name"):
                case.drop_schema()
        self.assertEqual(case.connection.mock_calls, [])


class PostgreSQLFixtureAdapterTests(unittest.TestCase):
    def test_adapted_records_preserve_identity_points_and_expected_query_ids(self):
        original = read_fixture("tasks")
        snapshot = copy.deepcopy(original)
        adapted = [adapt_task(task) for task in original]
        self.assertEqual(original, snapshot)
        self.assertEqual([task["id"] for task in adapted], [task["id"] for task in original])
        self.assertEqual({task["type"] for task in adapted}, {"class", "assignment", "exam", "event", "personal", "tuition"})
        fields = {"id", "title", "type", "course", "description", "target_audience", "location",
                  "registration_start", "registration_end", "start_time", "end_time", "deadline",
                  "estimated_hours", "training_points", "drl_category", "recurrence", "status",
                  "is_manual", "source_url", "source_platform", "updated_at"}
        for before, after in zip(original, adapted):
            self.assertEqual(set(after), fields)
            self.assertEqual(after["course"], before["course_code"])
            self.assertEqual(after["training_points"], before["training_points"])
            self.assertIsNotNone(after["updated_at"].utcoffset())
        self.assertEqual(next(t for t in adapted if t["id"] == "class-csc10004")["recurrence"], "T6 07:30-11:00")
        queries = read_fixture("queries")
        saved = copy.deepcopy(queries)
        for query in queries:
            mapped = adapt_request(query["request"])
            self.assertNotIn("course_code", mapped.get("filters", {}))
            if "course_code" in query["request"].get("filters", {}):
                self.assertEqual(mapped["filters"]["course"], query["request"]["filters"]["course_code"])
        self.assertEqual(queries, saved)

    def test_unsupported_values_are_not_silently_coerced(self):
        base = read_fixture("tasks")[0]
        for changes in ({"training_points": None}, {"training_points": True}, {"recurrence": "WEEKLY:MON"},
                        {"embedding": [0.1]}, {"course_code": "A course name"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                adapt_task({**base, **changes})
        for value in (None, "A course name", "csc10004"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                adapt_request({"filters": {"course_code": value}})


if __name__ == "__main__":
    unittest.main()
