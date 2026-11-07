"""Validate requests independently and exercise the SQLite compatibility boundary."""
import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from academic_search import SearchService, SearchValidationError
from academic_search.fixture_adapter import create_demo_database
from academic_search.service import compile_request, validate_sqlite_request
from academic_search.validation import TYPES, parse_instant, validate_request, validate_task_id

CLOCK = "2026-10-30T12:00:00+07:00"
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]


class RequestValidationTests(unittest.TestCase):
    def test_defaults_and_all_types_need_no_database(self):
        with patch("sqlite3.connect", side_effect=AssertionError("unexpected connection")):
            request = validate_request({})
            self.assertEqual(request.filters, {"statuses": ("active",)})
            self.assertEqual((request.sort, request.direction, request.limit, request.offset),
                             ("deadline", "asc", 20, 0))
            selected = validate_request({"filters": {"types": sorted(TYPES)}})
            self.assertEqual(set(selected.filters["types"]),
                             {"class", "assignment", "exam", "event", "personal", "tuition"})

    def test_normalized_request_is_detached_and_immutable(self):
        raw = {"filters": {"types": ["class", "exam"], "deadline_within": list(DAY)}}
        request = validate_request(raw)
        raw["filters"]["types"].append("event")
        raw["filters"]["deadline_within"][0] = "bad"
        self.assertEqual(request.filters["types"], ("class", "exam"))
        self.assertEqual(request.filters["deadline_within"][0],
                         datetime(2026, 10, 29, 17, tzinfo=timezone.utc))
        with self.assertRaises(TypeError):
            request.filters["statuses"] = ("done",)
        with self.assertRaises(FrozenInstanceError):
            request.limit = 100

    def test_timestamps_are_aware_datetimes_not_storage_integers(self):
        for key in ("deadline_within", "registration_end_within", "start_time_within",
                    "updated_at_within", "event_overlaps"):
            with self.subTest(key=key):
                request = validate_request({"filters": {key: [CLOCK, "2026-10-30T05:00:00.000001Z"]}})
                start, end = request.filters[key]
                self.assertEqual(start, datetime(2026, 10, 30, 5, tzinfo=timezone.utc))
                self.assertEqual((end - start).microseconds, 1)
        request = validate_request({"filters": {"registration_open_at": CLOCK}})
        self.assertEqual(request.filters["registration_open_at"], parse_instant("2026-10-30T05:00:00Z"))

    def test_invalid_requests_fail_without_a_connection(self):
        invalid = [None, [], {"keyword": "tuition"}, {"filters": None},
                   {"filters": {"unknown": 1}}, {"filters": {"course_code": "CSC10004"}},
                   {"sort": "title"}, {"direction": "ASC"}, {"limit": True},
                   {"limit": 101}, {"offset": -1}, {"offset": "0"},
                   {"filters": {"source_platform": "web"}},
                   {"filters": {"target_audience": ""}},
                   {"filters": {"location_prefix": "x" * 101}},
                   {"filters": {"min_training_points": True}},
                   {"filters": {"max_training_points": 1.5}},
                   {"filters": {"min_training_points": 8, "max_training_points": 7}}]
        for key in ("types", "statuses", "source_platforms"):
            invalid.extend({"filters": {key: value}} for value in ([], None, [["event"]], ["bad"], ["event", "event"]))
        with patch("sqlite3.connect", side_effect=AssertionError("unexpected connection")):
            for request in invalid:
                with self.subTest(request=request), self.assertRaises(SearchValidationError):
                    validate_request(request)

    def test_invalid_times_and_ranges(self):
        for value in ("2026-10-30", "2026-10-30T12:00:00", "2026-02-30T12:00:00Z",
                      "2026-10-30T12:00:00+00:60", None, 12):
            with self.subTest(value=value), self.assertRaises(SearchValidationError):
                validate_request({"filters": {"registration_open_at": value}})
        for key in ("deadline_within", "registration_end_within", "start_time_within",
                    "updated_at_within", "event_overlaps"):
            for value in ([CLOCK, CLOCK], DAY[::-1], [CLOCK], [], "today"):
                with self.subTest(key=key, value=value), self.assertRaises(SearchValidationError):
                    validate_request({"filters": {key: value}})

    def test_course_text_is_not_a_course_code_alias(self):
        course = "Cấu trúc dữ liệu / CSC10004"
        request = validate_request({"filters": {"course": course}})
        self.assertEqual(request.filters["course"], course)
        self.assertNotIn("course_code", request.filters)
        for value in (None, "", "   ", "bad\x00text"):
            with self.subTest(value=value), self.assertRaises(SearchValidationError):
                validate_request({"filters": {"course": value}})
        with self.assertRaisesRegex(SearchValidationError, "unknown filter"):
            validate_sqlite_request({"filters": {"course": course}})
        legacy = validate_sqlite_request({"filters": {"course_code": "CSC10004"}})
        self.assertEqual(legacy.course_code, "CSC10004")
        self.assertNotIn("course", legacy.common.filters)
        self.assertNotIn("course_code", legacy.common.filters)

    def test_database_ids_are_broader_than_sqlite_fixture_ids(self):
        for value in ("A", "ID_é with spaces", "a" * 64, "id' OR 1=1 --"):
            with self.subTest(value=value):
                self.assertEqual(validate_task_id(value), value)
                with self.assertRaises(SearchValidationError):
                    SearchService(None).get_task_by_id(value)
        self.assertEqual(validate_task_id("  Task_1  "), "Task_1")
        for value in (None, "", "   ", "a" * 65, "a\x00b"):
            with self.subTest(value=value), self.assertRaises(SearchValidationError):
                validate_task_id(value)


class SQLiteCompilationTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "fixtures/search/tasks.json"
        self.connection = create_demo_database(json.loads(path.read_text(encoding="utf-8")))
        self.addCleanup(self.connection.close)

    def test_compiler_consumes_normalized_values_without_revalidation(self):
        raw = {"filters": {"types": ["event"], "location_prefix": "CS2",
                           "event_overlaps": list(DAY)}, "sort": "id"}
        request = validate_sqlite_request(raw)
        raw["filters"]["event_overlaps"][0] = "bad"
        with patch("academic_search.service.validate_request", side_effect=AssertionError("revalidation")), \
             patch("academic_search.validation.parse_instant", side_effect=AssertionError("reparsing")):
            sql, params = compile_request(request)
        results = [json.loads(row[0])["id"] for row in self.connection.execute(sql, params)]
        self.assertEqual(results, ["evt-overlap", "evt-today"])
        self.assertTrue(all(not isinstance(value, datetime) for value in params))

    def test_service_uses_all_types_and_only_reads_supplied_connection(self):
        connection = Mock(wraps=self.connection)
        search = SearchService(connection)
        results = search.search_tasks({"limit": 100})
        self.assertEqual({row["type"] for row in results}, set(TYPES))
        self.assertEqual({row["status"] for row in results}, {"active"})
        self.assertEqual(search.get_task_by_id("evt-cancelled")["status"], "cancelled")
        self.assertEqual([call[0] for call in connection.mock_calls], ["execute", "execute"])
        self.assertTrue(all(call.args[0].startswith("SELECT ") for call in connection.mock_calls))

    def test_invalid_requests_do_not_touch_connection(self):
        connection = Mock()
        search = SearchService(connection)
        for request in ({"limit": 0}, {"filters": {"course": "CSC10004"}},
                        {"filters": {"course_code": "csc10004"}}):
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                search.search_tasks(request)
        connection.assert_not_called()
        self.assertEqual(connection.mock_calls, [])


if __name__ == "__main__":
    unittest.main()
