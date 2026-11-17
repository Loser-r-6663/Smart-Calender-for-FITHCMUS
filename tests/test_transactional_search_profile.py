"""Offline refusal and isolation checks for the transactional Search profile."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import transactional_search_profile as profile
import test_transactional_search_postgres as live
from postgres_search_support import read_test_target


class TransactionalSearchProfileTests(unittest.TestCase):
    def test_reviewed_checkout_passes_current_profile_and_fails_historical_profile(self):
        from postgres_search_support import reviewed_schema

        self.assertIn("CREATE TABLE IF NOT EXISTS user_tasks", profile.reviewed_transactional_schema())
        with self.assertRaisesRegex(RuntimeError, "Database/Db_query.sql"):
            reviewed_schema(profile.DATABASE_DIRECTORY)

    def test_normalizes_line_endings_and_rejects_drift_or_missing_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            database = Path(directory)
            for name in profile.REVIEWED_SOURCES:
                source = (profile.DATABASE_DIRECTORY / name).read_text(encoding="utf-8")
                (database / name).write_bytes(source.replace("\n", "\r\n").encode("utf-8"))

            def local_spec(name):
                if name == "Database":
                    return SimpleNamespace(submodule_search_locations=[str(database), str(database)])
                return SimpleNamespace(origin=str(database / (name.split(".")[-1] + ".py")))

            with patch.object(profile, "DATABASE_DIRECTORY", database), patch.object(
                profile, "find_spec", side_effect=local_spec
            ):
                self.assertIn("CREATE TABLE", profile.reviewed_transactional_schema())
                for name in ("Db_query.sql", "db_connection.py", "user_tasks.py"):
                    with self.subTest(name=name):
                        path = database / name
                        reviewed = path.read_bytes()
                        path.write_bytes(reviewed + b"\r\n# drift\r\n")
                        with self.assertRaisesRegex(RuntimeError, f"source mismatch: Database/{name}"):
                            profile.reviewed_transactional_schema()
                        path.write_bytes(reviewed)
                (database / "task_validation.py").unlink()
                with self.assertRaisesRegex(RuntimeError, "Cannot read.*Database/task_validation.py"):
                    profile.reviewed_transactional_schema()

    def test_refuses_wrong_package_and_mixed_module_origins(self):
        foreign = str(profile.DATABASE_DIRECTORY / "other")
        for locations in ([foreign], [str(profile.DATABASE_DIRECTORY), foreign]):
            with self.subTest(locations=locations), patch.object(
                profile, "find_spec", return_value=SimpleNamespace(submodule_search_locations=locations)
            ):
                with self.assertRaisesRegex(RuntimeError, "Database package from this checkout"):
                    profile.reviewed_transactional_schema()
        with patch.object(profile, "find_spec", side_effect=[
            SimpleNamespace(submodule_search_locations=[str(profile.DATABASE_DIRECTORY)]),
            SimpleNamespace(origin=str(profile.DATABASE_DIRECTORY / "other" / "database_manager.py")),
        ]):
            with self.assertRaisesRegex(RuntimeError, "Unexpected transactional profile import"):
                profile.reviewed_transactional_schema()

    def test_source_mismatch_stops_live_setup_before_target_selection(self):
        with patch("test_transactional_search_postgres.reviewed_transactional_schema",
                   side_effect=RuntimeError("source mismatch")), patch(
            "test_transactional_search_postgres.read_test_target"
        ) as read_target:
            with self.assertRaisesRegex(RuntimeError, "source mismatch"):
                live.TransactionalSearchPostgreSQLTests.setUpClass()
            read_target.assert_not_called()

    def test_provider_refuses_unexpected_schema_and_connection_path(self):
        target = read_test_target({
            "SEARCH_TEST_DB_HOST": "127.0.0.1", "SEARCH_TEST_DB_NAME": "calendar_search_test",
            "SEARCH_TEST_DB_USER": "tester", "SEARCH_TEST_DB_PASSWORD": "private-test-value",
            "SEARCH_TEST_DB_PORT": "55432", "SEARCH_TEST_DB_CONFIRM": "calendar_search_test",
        })
        connect = MagicMock()
        with self.assertRaisesRegex(RuntimeError, "Unexpected.*scratch schema"):
            live.scratch_provider(object, connect, target, "search_sample")
        connect.assert_not_called()

        schema = "search_tx_it_" + "0" * 32
        database = live.scratch_provider(object, connect, target, schema)
        connection = connect.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        connection.get_dsn_parameters.return_value = {"host": target.host, "port": str(target.port)}
        cursor.fetchone.side_effect = [(target.database, target.user), ("public",)]
        with self.assertRaisesRegex(RuntimeError, "unexpected search_path"):
            database.connect()
        connect.assert_called_once_with(
            **target.manager_kwargs(), options=f"-c search_path={schema},pg_catalog,pg_temp", connect_timeout=5,
        )
        connection.close.assert_called_once_with()
