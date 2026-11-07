"""Real PostgreSQL retrieval checks in isolated schemas on an explicit test target."""
import contextlib
import inspect
import io
import os
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from academic_search import SearchDatabaseError, SearchService, SearchValidationError
from postgres_search_support import (adapt_request, adapt_task, read_fixture,
                                     read_test_target, reviewed_schema, validate_live_target)

CLOCK = "2026-10-30T12:00:00+07:00"
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]
ACTIVE_IDS = [
    "asg-csc10004-lab", "asg-csc10004-project", "asg-csc10005-lab", "asg-csc10005-project",
    "asg-ct-proposal", "asg-db-sql", "asg-english", "asg-network", "asg-overdue", "asg-update",
    "class-csc10004", "evt-beach", "evt-cancel", "evt-debate", "evt-delete", "evt-end-midnight",
    "evt-future-reg", "evt-green", "evt-missing-both", "evt-missing-end", "evt-missing-start",
    "evt-next-midnight", "evt-overlap", "evt-reg-after", "evt-reg-before", "evt-reg-exact",
    "evt-speaking", "evt-today", "exam-csc10005", "fee-english", "fee-hk1", "fee-installment",
    "fee-mixed", "personal-study",
]
DEFAULT_IDS = [
    "asg-overdue", "asg-csc10004-lab", "asg-csc10005-lab", "asg-update", "asg-network",
    "asg-ct-proposal", "asg-db-sql", "asg-english", "asg-csc10004-project", "asg-csc10005-project",
    "fee-english", "fee-mixed", "fee-hk1", "fee-installment", "class-csc10004", "evt-beach",
    "evt-cancel", "evt-debate", "evt-delete", "evt-end-midnight",
]


@unittest.skipUnless(
    os.getenv("RUN_SEARCH_POSTGRES_INTEGRATION") == "1",
    "Real PostgreSQL suite disabled; requires explicit dedicated SEARCH_TEST_DB_* configuration.",
)
class PostgreSQLSearchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = read_test_target(os.environ)
        try:
            import psycopg2
            from psycopg2 import sql
            from Database.DatabaseManager import DatabaseManager
            from Database.tasks import TaskRepository
        except ImportError:
            raise RuntimeError("Provide the reviewed Database package, psycopg2, Pydantic v2 and python-dotenv") from None
        directory = Path(inspect.getfile(DatabaseManager)).resolve().parent
        if directory.name != "Database" or Path(inspect.getfile(TaskRepository)).resolve() != directory / "tasks.py":
            raise RuntimeError("Expected the selected Database/DatabaseManager.py and its matching task repository")
        cls.schema_sql = reviewed_schema(directory)
        if DatabaseManager._instance is not None:
            raise RuntimeError("Refusing to reuse an existing DatabaseManager singleton; run this suite in a fresh process")
        try:
            # The selected manager prints connection exceptions, so suppress that output.
            with contextlib.redirect_stdout(io.StringIO()):
                cls.manager = DatabaseManager(**cls.target.manager_kwargs())
        except Exception:
            raise RuntimeError("Dedicated PostgreSQL connection failed; check test settings privately") from None
        cls.connection = cls.manager.connection
        cls.addClassCleanup(cls.close_connection)
        validate_live_target(cls.connection, cls.target)
        cls.connection.rollback()
        if cls.connection.autocommit:
            raise RuntimeError("Integration setup requires the manager's transactional connection")
        cls.sql, cls.pg_error, cls.integrity_error = sql, psycopg2.Error, psycopg2.IntegrityError
        cls.repository = TaskRepository()

    @classmethod
    def close_connection(cls):
        if not cls.connection.closed:
            try:
                cls.connection.rollback()
            finally:
                cls.connection.close()

    def setUp(self):
        validate_live_target(self.connection, self.target)
        self.connection.rollback()
        self.schema = "search_it_" + uuid4().hex
        self.schema_created = False
        self.addCleanup(self.drop_schema)
        with self.connection.cursor() as cursor:
            cursor.execute(self.sql.SQL("CREATE SCHEMA {}").format(self.sql.Identifier(self.schema)))
            self.schema_created = True
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute(self.sql.SQL("SET SESSION search_path TO {}, pg_catalog").format(self.sql.Identifier(self.schema)))
            cursor.execute(self.schema_sql)
            cursor.execute("INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id",
                           ("search_owner", "owner@search.example.invalid"))
            self.user_id = cursor.fetchone()[0]
            cursor.execute("INSERT INTO users (username, email) VALUES (%s, %s) RETURNING id",
                           ("search_other", "other@search.example.invalid"))
            self.other_id = cursor.fetchone()[0]
        self.tasks = {task["id"]: adapt_task(task) for task in read_fixture("tasks")}
        for task in self.tasks.values():
            self.insert_task(task)
        self.connection.commit()
        self.search = SearchService(self.manager, user_id=self.user_id)

    def drop_schema(self):
        if not self.schema_created:
            return
        if not re.fullmatch(r"search_it_[0-9a-f]{32}", self.schema):
            raise RuntimeError("Refusing cleanup of an unexpected schema name")
        self.connection.rollback()
        validate_live_target(self.connection, self.target)
        with self.connection.cursor() as cursor:
            cursor.execute("SET SESSION search_path TO pg_catalog")
            cursor.execute(self.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(self.sql.Identifier(self.schema)))
        self.connection.commit()
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = %s", (self.schema,))
            remains = cursor.fetchone() is not None
        self.connection.rollback()
        if remains:
            raise RuntimeError("Scratch schema remained after committed cleanup")
        self.schema_created = False

    def insert_task(self, task, *, owner=None):
        self.repository.create(self.connection, task)
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (%s, %s)",
                           (self.user_id if owner is None else owner, task["id"]))

    def variant(self, task_id, *, original="evt-green", owner=None, **changes):
        task = {**self.tasks[original], **changes, "id": task_id}
        self.insert_task(task, owner=owner)
        self.connection.commit()
        return task

    def ids(self, filters=None, **options):
        request = {"filters": {} if filters is None else filters, "sort": "id", "limit": 100, **options}
        return [task["id"] for task in self.search.search_tasks(request)]

    def test_existing_structured_expectations(self):
        queries = [query for query in read_fixture("queries") if query["mode"] == "structured"]
        self.assertEqual([query["id"] for query in queries],
                         ["q01", "q05", "q09", "q10", "q19", "q20", "q23", "q24", "q27"])
        for query in queries:
            with self.subTest(query=query["id"]):
                self.assertEqual(query["state"], "base")
                request = {**adapt_request(query["request"]), "limit": 100}
                actual = self.search.search_tasks(request)
                self.assertEqual({row["id"] for row in actual}, set(query["expected_ids"]))
                self.assertFalse({row["id"] for row in actual}.intersection(query["excluded_ids"]))

    def test_lookup_defaults_all_types_and_missing(self):
        self.assertEqual(self.search.get_task_by_id("asg-csc10004-lab"), self.tasks["asg-csc10004-lab"])
        self.assertIsNone(self.search.get_task_by_id("does-not-exist"))
        self.assertEqual(self.search.get_task_by_id("evt-cancelled")["status"], "cancelled")
        self.assertEqual(self.ids(), ACTIVE_IDS)
        self.assertEqual([row["id"] for row in self.search.search_tasks({})], DEFAULT_IDS)
        self.assertEqual({row["type"] for row in self.search.search_tasks({"limit": 100})},
                         {"class", "assignment", "exam", "event", "personal", "tuition"})
        self.variant("Task_é 1", original="personal-study")
        self.assertEqual(self.search.get_task_by_id("  Task_é 1  ")["id"], "Task_é 1")

    def test_types_statuses_course_and_combined_sources(self):
        self.assertEqual(self.ids({"types": ["class", "exam"]}), ["class-csc10004", "exam-csc10005"])
        self.assertEqual(self.ids({"statuses": ["done"]}), ["asg-done", "evt-done", "fee-done"])
        self.assertEqual(self.ids({"statuses": ["archived", "cancelled"], "types": ["assignment"]}),
                         ["asg-archived", "asg-cancelled"])
        self.assertEqual(self.ids({"course": "CSC10004"}),
                         ["asg-csc10004-lab", "asg-csc10004-project", "asg-overdue", "class-csc10004"])
        self.assertEqual(self.ids({"course": "CSC10005"}),
                         ["asg-csc10005-lab", "asg-csc10005-project", "exam-csc10005"])
        self.assertEqual(self.ids({"course": "CSC10004", "source_platform": "moodle", "types": ["assignment"]}),
                         ["asg-csc10004-lab", "asg-csc10004-project", "asg-overdue"])
        self.assertEqual(self.ids({"types": ["class", "exam"], "source_platforms": ["portal", "custom"]}),
                         ["class-csc10004", "exam-csc10005"])
        self.assertEqual(self.ids({"source_platform": "moodle", "source_platforms": ["custom"]}), [])
        self.assertEqual(self.ids({"source_platforms": ["moodle", "portal", "facebook", "custom"]}), ACTIVE_IDS)
        self.variant("course-name", original="personal-study", course="Cấu trúc dữ liệu / CSC10004")
        self.assertEqual(self.ids({"course": "Cấu trúc dữ liệu / CSC10004"}), ["course-name"])
        self.assertNotIn("course-name", self.ids({"course": "CSC10004"}))

    def test_points_zero_limits_and_unsupported_unknown(self):
        self.variant("points-zero", training_points=0, drl_category=None)
        self.variant("points-hundred", training_points=100)
        self.assertEqual(self.ids({"min_training_points": 7, "max_training_points": 10}), ["evt-beach", "evt-green"])
        self.assertEqual(self.ids({"min_training_points": 100, "max_training_points": 100}), ["points-hundred"])
        self.assertEqual(self.ids({"types": ["event"], "min_training_points": 0, "max_training_points": 0}),
                         ["evt-delete", "points-zero"])
        self.assertEqual(self.search.get_task_by_id("points-zero")["training_points"], 0)
        with self.assertRaises(ValueError):
            self.manager.create_task(self.user_id, {"title": "Unknown points", "training_points": None}, date(2026, 10, 30))
        with self.assertRaises(self.integrity_error):
            with self.connection.cursor() as cursor:
                cursor.execute("UPDATE tasks SET training_points = NULL WHERE id = %s", ("points-zero",))
        self.connection.rollback()
        self.assertEqual(self.search.get_task_by_id("points-zero")["training_points"], 0)

    def test_deadlines_registration_event_and_update_dates(self):
        self.assertEqual(self.ids({"deadline_within": DAY}), ["asg-csc10004-lab", "asg-csc10005-lab", "asg-update"])
        self.assertEqual(self.ids({"registration_end_within": DAY}), ["evt-reg-after", "evt-reg-before", "evt-reg-exact"])
        self.assertEqual(self.ids({"types": ["event"], "start_time_within": DAY}), ["evt-today"])
        self.assertEqual(self.ids({"types": ["event"], "event_overlaps": DAY}), ["evt-overlap", "evt-today"])
        self.assertEqual(self.ids({"updated_at_within": DAY}), [])
        start = datetime.fromisoformat(DAY[0])
        end = datetime.fromisoformat(DAY[1])
        self.variant("due-lower", original="personal-study", deadline=start, updated_at=start)
        self.variant("due-upper", original="personal-study", deadline=end, updated_at=end)
        self.assertEqual(self.ids({"course": "absent", "deadline_within": DAY}), [])
        self.assertEqual(self.ids({"types": ["personal"], "deadline_within": DAY}), ["due-lower"])
        self.assertEqual(self.ids({"updated_at_within": DAY}), ["due-lower"])

    def test_registration_closing_boundaries_and_missing_dates(self):
        for at, expected in [("2026-10-30T10:59:59+07:00", ["evt-reg-after", "evt-reg-before", "evt-reg-exact"]),
                             ("2026-10-30T11:00:00+07:00", ["evt-reg-after", "evt-reg-before", "evt-reg-exact"]),
                             (CLOCK, ["evt-reg-after", "evt-reg-exact"]),
                             ("2026-10-30T12:00:01+07:00", ["evt-reg-after"]),
                             ("2026-10-30T13:00:01+07:00", [])]:
            with self.subTest(at=at):
                self.assertEqual(self.ids({"registration_end_within": DAY, "registration_open_at": at}), expected)
        self.variant("reg-opens", registration_start=datetime.fromisoformat(CLOCK))
        matches = self.ids({"registration_open_at": CLOCK})
        self.assertEqual(matches, ["evt-beach", "evt-cancel", "evt-debate", "evt-delete", "evt-green",
                                   "evt-reg-after", "evt-reg-exact", "evt-speaking", "reg-opens"])
        self.variant("no-event-end", start_time=datetime.fromisoformat(CLOCK), end_time=None)
        self.variant("no-event-start", start_time=None, end_time=datetime.fromisoformat(DAY[1]))
        self.assertEqual(self.ids({"event_overlaps": DAY}), ["evt-overlap", "evt-today"])
        self.assertEqual(self.ids({"types": ["event"], "start_time_within": DAY}), ["evt-today", "no-event-end"])

    def test_equivalent_offsets_and_microseconds(self):
        instant = datetime(2026, 10, 30, 5, 0, 0, 1, tzinfo=timezone.utc)
        self.variant("micro-event", start_time=instant, end_time=instant + timedelta(microseconds=1))
        self.assertEqual(self.ids({"start_time_within": [CLOCK, "2026-10-30T05:00:00.000001Z"]}), [])
        self.assertEqual(self.ids({"event_overlaps": [CLOCK, "2026-10-30T05:00:00.000002Z"]}),
                         ["evt-overlap", "micro-event"])
        self.assertEqual(self.ids({"registration_open_at": CLOCK}),
                         self.ids({"registration_open_at": "2026-10-30T05:00:00Z"}))
        self.assertEqual(self.search.get_task_by_id("micro-event")["start_time"], instant)

    def test_literal_prefix_unicode_audience_and_empty_results(self):
        self.assertEqual(self.ids({"target_audience": "K26", "location_prefix": "CS1"}), ["evt-debate", "evt-speaking"])
        self.assertEqual(self.ids({"location_prefix": "cs1"}), [])
        self.variant("literal-prefix", location="CS2_%' room", target_audience="ĐRL K26")
        self.assertEqual(self.ids({"location_prefix": "CS2_%'", "target_audience": "ĐRL K26"}), ["literal-prefix"])
        self.assertEqual(self.ids({"course": "CSC99999"}), [])
        self.assertEqual(self.ids({"types": ["tuition"], "course": "CSC10004"}), [])
        self.assertEqual(self.ids({"target_audience": "' OR 1=1 --"}), [])

    def test_sorting_nulls_id_ties_and_pagination(self):
        instant = datetime.fromisoformat(CLOCK)
        for suffix, value, points in [("a", instant - timedelta(days=1), 0), ("b", instant, 5),
                                      ("c", instant, 5), ("d", None, 10)]:
            self.variant("sort-" + suffix, original="personal-study", target_audience="sort-group",
                         deadline=value, start_time=value, end_time=None, training_points=points,
                         drl_category=None if points == 0 else "dieu_3",
                         updated_at=value if value is not None else instant + timedelta(days=1))
        for sort, ascending, descending in [
            ("id", ["a", "b", "c", "d"], ["d", "c", "b", "a"]),
            ("deadline", ["a", "b", "c", "d"], ["b", "c", "a", "d"]),
            ("start_time", ["a", "b", "c", "d"], ["b", "c", "a", "d"]),
            ("updated_at", ["a", "b", "c", "d"], ["d", "b", "c", "a"]),
            ("training_points", ["a", "b", "c", "d"], ["d", "b", "c", "a"]),
        ]:
            for direction, expected in [("asc", ascending), ("desc", descending)]:
                with self.subTest(sort=sort, direction=direction):
                    self.assertEqual(self.ids({"target_audience": "sort-group"}, sort=sort, direction=direction),
                                     ["sort-" + suffix for suffix in expected])
        pages = [self.ids({"target_audience": "sort-group"}, limit=2, offset=offset) for offset in (0, 2)]
        self.assertEqual(pages, [["sort-a", "sort-b"], ["sort-c", "sort-d"]])
        self.assertEqual(self.ids(offset=100000), [])
        self.assertEqual(self.ids({"course": "CSC10004"}, limit=2, offset=1), ["asg-csc10004-project", "asg-overdue"])

    def test_mutations_via_selected_manager_are_visible(self):
        self.assertEqual(self.ids({"course": "CSC10014", "deadline_within": DAY}), ["asg-update"])
        before = datetime.now(timezone.utc) - timedelta(seconds=1)
        changed_deadline = datetime(2026, 11, 2, 23, 59, tzinfo=timezone(timedelta(hours=7)))
        self.assertTrue(self.manager.update_task("asg-update", {"title": "Final retrieval report", "deadline": changed_deadline}))
        after = datetime.now(timezone.utc) + timedelta(seconds=1)
        self.assertEqual(self.ids({"course": "CSC10014", "deadline_within": DAY}), [])
        self.assertEqual(self.ids({"course": "CSC10014", "deadline_within": ["2026-11-02T00:00:00+07:00", "2026-11-03T00:00:00+07:00"]}), ["asg-update"])
        self.assertEqual(self.ids({"updated_at_within": [before.isoformat(), after.isoformat()]}), ["asg-update"])
        self.assertEqual(self.search.get_task_by_id("asg-update")["title"], "Final retrieval report")
        self.assertTrue(self.manager.update_task("evt-cancel", {"status": "cancelled"}))
        self.assertNotIn("evt-cancel", self.ids())
        self.assertEqual(self.ids({"statuses": ["cancelled"]}), ["asg-cancelled", "evt-cancel", "evt-cancelled"])
        self.assertEqual(self.search.get_task_by_id("evt-cancel")["status"], "cancelled")
        self.assertTrue(self.manager.delete_task("evt-delete"))
        self.assertIsNone(self.search.get_task_by_id("evt-delete"))
        self.assertEqual(self.ids({"types": ["event"], "min_training_points": 0, "max_training_points": 0}), [])
        created = self.manager.create_task(self.user_id, {"title": "Created through selected manager", "type": "personal",
                                                       "course": "Manager-created"}, date(2026, 10, 30))
        self.assertIsInstance(created, str)
        self.assertEqual(self.ids({"course": "Manager-created"}), [created])
        self.assertTrue(self.manager.delete_task(created))
        self.assertEqual(self.ids({"course": "Manager-created"}), [])

    def test_ownership_isolation_and_deduplicated_shared_assignment(self):
        self.variant("other-private", original="personal-study", owner=self.other_id)
        self.repository.create(self.connection, {**self.tasks["personal-study"], "id": "unassigned-private"})
        self.connection.commit()
        self.assertIsNone(self.search.get_task_by_id("other-private"))
        self.assertIsNone(self.search.get_task_by_id("unassigned-private"))
        other = SearchService(self.manager, user_id=self.other_id)
        self.assertEqual([row["id"] for row in other.search_tasks({})], ["other-private"])
        self.assertIsNone(other.get_task_by_id("personal-study"))
        with self.connection.cursor() as cursor:
            cursor.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (%s, %s)", (self.other_id, "personal-study"))
        self.connection.commit()
        self.assertEqual(self.ids({"types": ["personal"]}), ["personal-study"])
        self.assertEqual([row["id"] for row in other.search_tasks({"sort": "id"})], ["other-private", "personal-study"])

    def test_invalid_requests_are_validation_errors(self):
        for request in ({"filters": {"course_code": "CSC10004"}}, {"filters": {"types": []}},
                        {"filters": {"statuses": ["completed"]}}, {"limit": True}, {"offset": -1},
                        {"sort": "title"}, {"filters": {"event_overlaps": DAY[::-1]}},
                        {"filters": {"registration_open_at": "2026-10-30T12:00:00"}}):
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                self.search.search_tasks(request)
        for task_id in ("", "a" * 65, "bad\x00id"):
            with self.subTest(task_id=task_id), self.assertRaises(SearchValidationError):
                self.search.get_task_by_id(task_id)
        self.assertEqual(self.ids(), ACTIVE_IDS)

    def test_real_database_failure_is_distinct_from_empty_results(self):
        self.assertEqual(self.ids({"course": "missing"}), [])
        self.connection.rollback()
        for lookup in (False, True):
            with self.connection.cursor() as cursor:
                cursor.execute("SET LOCAL search_path TO pg_catalog")
            with self.assertRaises(SearchDatabaseError) as caught:
                if lookup:
                    self.search.get_task_by_id("personal-study")
                else:
                    self.search.search_tasks({})
            self.assertIsInstance(caught.exception.__cause__, self.pg_error)
            self.connection.rollback()
        self.assertEqual(self.ids(), ACTIVE_IDS)


if __name__ == "__main__":
    unittest.main()
