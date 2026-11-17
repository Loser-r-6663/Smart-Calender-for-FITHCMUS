"""Live checks of the reviewed transaction-based Search profile."""
import os
import re
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from academic_search import (
    SearchDatabaseError,
    SearchInterpretationError,
    SearchValidationError,
    TransactionalSearch,
)
from postgres_search_support import (
    adapt_request,
    adapt_task,
    read_fixture,
    read_test_target,
    validate_live_target,
)
from transactional_search_profile import reviewed_transactional_schema

OPT_IN = "RUN_TRANSACTIONAL_SEARCH_POSTGRES_INTEGRATION"
SCRATCH_NAME = re.compile(r"search_tx_it_[0-9a-f]{32}")
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]


def scratch_provider(provider_class, connect, target, schema):
    if not SCRATCH_NAME.fullmatch(schema):
        raise RuntimeError("Unexpected transactional Search scratch schema name")

    class ScratchDatabase(provider_class):
        def __init__(self):
            # The test target is explicit and independent of application dotenv settings.
            pass

        def connect(self):
            path = f"{schema},pg_catalog,pg_temp"
            try:
                connection = connect(
                    **target.manager_kwargs(), options=f"-c search_path={path}", connect_timeout=5,
                )
            except Exception:
                raise RuntimeError("Dedicated PostgreSQL connection failed; check settings privately") from None
            try:
                validate_live_target(connection, target)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_catalog.current_setting('search_path')")
                    if cursor.fetchone() != (path,):
                        raise RuntimeError("Dedicated connection has an unexpected search_path")
            except BaseException:
                connection.close()
                raise
            return connection

    return ScratchDatabase()


@unittest.skipUnless(os.getenv(OPT_IN) == "1", f"Live transactional Search requires {OPT_IN}=1")
class TransactionalSearchPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema_sql = reviewed_transactional_schema()
        cls.target = read_test_target(os.environ)
        try:
            import psycopg2
            from psycopg2 import sql
            from Database.database_manager import DatabaseManager
            from Database.db_connection import DatabaseConnection
        except ImportError:
            raise RuntimeError("Install psycopg2-binary, Pydantic v2 and python-dotenv") from None
        cls.driver, cls.sql, cls.manager_class = psycopg2, sql, DatabaseManager
        cls.provider_class = DatabaseConnection

    @contextmanager
    def scratch_schema(self, schema, schema_sql):
        database = scratch_provider(self.provider_class, self.driver.connect, self.target, schema)
        identifier = self.sql.Identifier(schema)
        created = False
        try:
            with database.transaction() as connection, connection.cursor() as cursor:
                cursor.execute(self.sql.SQL("CREATE SCHEMA {}").format(identifier))
                created = True
                cursor.execute("SELECT pg_catalog.current_schema()")
                self.assertEqual(cursor.fetchone(), (schema,))
                cursor.execute(schema_sql)
            yield database
        finally:
            if created:
                with database.transaction() as connection, connection.cursor() as cursor:
                    cursor.execute(self.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(identifier))
                with database.transaction() as connection, connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s", (schema,))
                    self.assertIsNone(cursor.fetchone(), f"Scratch schema remains: {schema}")
                print(f"Verified scratch schema absent: {schema}")

    def setUp(self):
        self.schema = "search_tx_it_" + uuid4().hex
        self.database = self.enterContext(self.scratch_schema(self.schema, self.schema_sql))
        self.manager = self.manager_class(database=self.database)
        self.owner = self.manager.create_user("owner", "owner@search.example.invalid")["id"]
        self.other = self.manager.create_user("other", "other@search.example.invalid")["id"]
        self.search = TransactionalSearch(self.manager, user_id=self.owner)
        self.other_search = TransactionalSearch(self.manager, user_id=self.other)

    def seed_fixtures(self, *task_ids):
        fixtures = {task["id"]: task for task in read_fixture("tasks")}
        for task_id in task_ids:
            self.manager.create_task(adapt_task(fixtures[task_id]))
            self.assertTrue(self.manager.assign_task(self.owner, task_id))

    def create_personal(self, task_id, title, **fields):
        return self.manager.create_personal_task(self.owner, {"id": task_id, "title": title, **fields})

    def test_lookup_and_structured_pagination(self):
        self.seed_fixtures("asg-csc10004-lab", "asg-csc10004-project", "asg-csc10005-lab", "asg-cancelled")
        self.assertEqual(self.search.get_task_by_id(" asg-cancelled ")["status"], "cancelled")
        self.assertIsNone(self.search.get_task_by_id("ASG-CANCELLED"))
        self.assertIsNone(self.search.get_task_by_id("missing"))
        request = adapt_request({
            "filters": {"course_code": "CSC10004", "types": ["assignment"]},
            "sort": "deadline", "limit": 1,
        })
        self.assertEqual(ids(self.search.search_tasks(request)), ["asg-csc10004-lab"])
        self.assertEqual(ids(self.search.search_tasks({**request, "offset": 1})), ["asg-csc10004-project"])
        self.assertEqual(self.search.search_tasks({**request, "offset": 2}), [])

    def test_literal_and_interpreted_keyword(self):
        self.create_personal("literal", "Review 50%_! today")
        self.create_personal("wildcard-decoy", "Review 50xyz! today")
        self.assertEqual(ids(self.search.search_tasks({"keyword": "50%_!"})), ["literal"])
        self.seed_fixtures("evt-green")
        self.manager.update_task("evt-green", {"title": "Thiện nguyện cuối tuần", "training_points": 5})
        result = self.search.interpret_and_search({"keyword": "sự kiện thiện nguyện 5 điểm"})
        self.assertEqual(ids(result.results), ["evt-green"])
        self.assertEqual(result.interpretation.remaining_keyword, "thiện nguyện")
        self.assertEqual(result.interpretation.effective_filters, {
            "types": ["event"], "statuses": ["active"], "min_training_points": 5, "max_training_points": 5,
        })

    def test_half_open_timestamp_window_and_stable_ties(self):
        for task_id, deadline in (
            ("lower-b", "2026-10-29T17:00:00Z"),
            ("lower-a", DAY[0]),
            ("before-upper", "2026-10-30T23:59:59.999999+07:00"),
            ("upper", DAY[1]),
        ):
            self.create_personal(task_id, "Boundary fixture", deadline=deadline)
        request = {"filters": {"deadline_within": DAY}, "sort": "deadline"}
        self.assertEqual(ids(self.search.search_tasks(request)), ["lower-a", "lower-b", "before-upper"])
        self.assertEqual(ids(self.search.search_tasks({**request, "limit": 1, "offset": 1})), ["lower-b"])

    def test_assignment_isolation_sharing_and_revocation(self):
        self.create_personal("private", "Shared topic")
        self.create_personal("shared", "Shared topic")
        request = {"keyword": "shared topic", "sort": "id"}
        self.assertIsNone(self.other_search.get_task_by_id("shared"))
        self.assertEqual(self.other_search.search_tasks(request), [])
        self.assertTrue(self.manager.assign_task(self.other, "shared"))
        self.assertFalse(self.manager.assign_task(self.other, "shared"))
        self.assertEqual(ids(self.search.search_tasks(request)), ["private", "shared"])
        self.assertEqual(ids(self.other_search.search_tasks(request)), ["shared"])
        self.assertTrue(self.manager.unassign_task(self.other, "shared"))
        self.assertIsNone(self.other_search.get_task_by_id("shared"))
        self.assertEqual(self.other_search.search_tasks(request), [])
        self.assertEqual(ids(self.search.search_tasks(request)), ["private", "shared"])

    def test_committed_creation_update_status_and_deletion(self):
        self.assertIsNone(self.search.get_task_by_id("editable"))
        self.create_personal("editable", "Initial title")
        self.assertEqual(self.search.get_task_by_id("editable")["title"], "Initial title")
        self.manager.update_task("editable", {"title": "Revised title"})
        self.assertEqual(self.search.search_tasks({"keyword": "initial"}), [])
        self.assertEqual(ids(self.search.search_tasks({"keyword": "revised"})), ["editable"])
        self.manager.update_task("editable", {"status": "done"})
        self.assertEqual(self.search.search_tasks({}), [])
        self.assertEqual(self.search.get_task_by_id("editable")["status"], "done")
        done = {"filters": {"statuses": ["done"]}}
        self.assertEqual(ids(self.search.search_tasks(done)), ["editable"])
        self.assertTrue(self.manager.delete_task("editable"))
        self.assertIsNone(self.search.get_task_by_id("editable"))
        self.assertEqual(self.search.search_tasks(done), [])
        self.assertEqual(self.manager.get_user_tasks(self.owner), [])

    def test_sql_failure_recovers_with_new_closed_connections(self):
        self.create_personal("recoverable", "Recovery fixture")
        connections = []
        connect = self.database.connect

        def observe_connection():
            connection = connect()
            connections.append(connection)
            return connection

        with patch.object(self.database, "connect", side_effect=observe_connection):
            with self.database.transaction() as connection, connection.cursor() as cursor:
                cursor.execute("ALTER TABLE tasks RENAME TO tasks_hidden")
            with self.assertRaises(SearchDatabaseError) as caught:
                self.search.search_tasks({})
            self.assertIsInstance(caught.exception.__cause__, self.driver.errors.UndefinedTable)
            with self.database.transaction() as connection, connection.cursor() as cursor:
                cursor.execute("ALTER TABLE tasks_hidden RENAME TO tasks")
            self.assertEqual(ids(self.search.search_tasks({})), ["recoverable"])
            self.assertEqual(self.search.get_task_by_id("recoverable")["title"], "Recovery fixture")
        self.assertEqual(len(connections), 5)
        self.assertEqual(len({id(connection) for connection in connections}), 5)
        self.assertTrue(all(connection.closed for connection in connections))

    def test_validation_errors_do_not_connect(self):
        with patch.object(self.database, "connect", wraps=self.database.connect) as connect:
            with self.assertRaises(SearchValidationError):
                self.search.search_tasks({"filters": {"deadline_within": DAY[::-1]}})
            with self.assertRaises(SearchInterpretationError):
                self.search.interpret_and_search({"keyword": "sự kiện 5 điểm", "filters": {"types": ["exam"]}})
            connect.assert_not_called()

    def test_cleanup_after_schema_setup_and_test_body_failures(self):
        schema = "search_tx_it_" + uuid4().hex
        with self.assertRaises(self.driver.errors.DivisionByZero):
            with self.scratch_schema(schema, self.schema_sql + "\nSELECT 1 / 0;"):
                self.fail("Schema setup should have failed")
        schema = "search_tx_it_" + uuid4().hex
        with self.assertRaisesRegex(ValueError, "deliberate test failure"):
            with self.scratch_schema(schema, self.schema_sql):
                raise ValueError("deliberate test failure")


def ids(rows):
    return [row["id"] for row in rows]
