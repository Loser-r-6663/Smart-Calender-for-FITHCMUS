"""Offline presentation tests; no PostgreSQL connection or query execution."""
from copy import deepcopy
from datetime import datetime
import unittest

from academic_search import Interpretation, interpret_request
from academic_search.postgres import task_record
from search_sample.output import SearchOutputError, render_search, timestamp
from test_postgres_search import record


class SearchOutputTests(unittest.TestCase):
    def test_original_query_structured_filters_and_blank_queries(self):
        output = render_search({"keyword": "sự kiện 5 điểm", "filters": {
            "types": ["event", "personal"], "course": "Tên môn / CSC10004"}}, [])
        for text in ("Original query: sự kiện 5 điểm", "Mode: literal keyword search", "Type: event, personal",
                     "Course: Tên môn / CSC10004", "Status: active", "Returned page: 0 task(s)"):
            self.assertIn(text, output)
        self.assertNotIn("Training points: exactly", output)
        self.assertNotIn("Remaining keyword:", output)
        self.assertNotIn("{", output)
        for query in (None, "", " \t\n "):
            request = {} if query is None else {"keyword": query}
            output = render_search(request, [])
            self.assertIn("Original query: No keyword constraint.", output)
            self.assertIn("Type: all six task types", output)
            self.assertEqual(output.splitlines()[-1], "No matching tasks")

    def test_interpretation_uses_metadata_and_preserves_unrelated_effective_filters(self):
        metadata = Interpretation("sự kiện 5 điểm", "tình nguyện", {}, {
            "statuses": ["done", "active"], "types": ["event"], "min_training_points": 5,
            "max_training_points": 10, "course": "Tên môn", "source_platforms": ["custom", "portal"],
            "target_audience": "K26", "location_prefix": "CS1", "registration_open_at": "2026-10-30T00:00:00Z"})
        output = render_search({"keyword": "ignored"}, [], metadata)
        for text in ("Original query: sự kiện 5 điểm", "Remaining keyword: tình nguyện", "Effective filters:",
                     "Status: done, active", "Type: event", "Training points: 5 through 10", "Course: Tên môn",
                     "Source platforms: custom, portal", "Target audience: K26", "Location prefix: CS1",
                     "Registration open at: 2026-10-30 07:00:00 GMT+7"):
            self.assertIn(text, output)
        self.assertNotIn("exactly 5", output)
        self.assertNotIn("{", output)
        metadata = interpret_request({"keyword": "sự kiện 5 điểm"})
        self.assertIn("Remaining keyword: No keyword constraint.", render_search({}, [], metadata))

    def test_training_point_constraint_variants_include_zero(self):
        for filters, expected in (({"min_training_points": 5, "max_training_points": 5}, "exactly 5"),
                                  ({"min_training_points": 5}, "at least 5"),
                                  ({"max_training_points": 5}, "at most 5"),
                                  ({"min_training_points": 5, "max_training_points": 10}, "5 through 10"),
                                  ({"min_training_points": 0, "max_training_points": 0}, "exactly 0")):
            with self.subTest(filters=filters):
                self.assertIn("Training points: " + expected, render_search({"filters": filters}, []))

    def test_full_identifiers_long_vietnamese_titles_missing_values_and_page_count(self):
        long_title = "Tình nguyện mùa hè " * 12
        rows = [task_record(record(id="first-task", title=long_title, type="personal")),
                task_record(record(id="second-task", title="Học phí", type="tuition", training_points=None))]
        output = render_search({}, rows)
        for text in ("Task ID: first-task", "Title: " + long_title, "Task ID: second-task", "Title: Học phí",
                     "Type: personal", "Type: tuition", "Training points: 0", "Training points: Unknown",
                     "Starts: Not provided", "Ends: Not provided", "Due: Not provided", "Returned page: 2 task(s)"):
            self.assertIn(text, output)
        self.assertNotIn("total matches", output.lower())

    def test_equivalent_offsets_calendar_boundary_and_timestamp_precision(self):
        self.assertEqual(timestamp(datetime.fromisoformat("2026-10-30T17:00:01.000123+00:00")),
                         "2026-10-31 00:00:01.000123 GMT+7")
        self.assertEqual(timestamp(datetime.fromisoformat("2026-10-30T17:00:01.000123+00:00")),
                         timestamp(datetime.fromisoformat("2026-10-31T00:00:01.000123+07:00")))
        self.assertEqual(timestamp(datetime.fromisoformat("2026-10-30T23:59:59-05:00")),
                         "2026-10-31 11:59:59 GMT+7")

    def test_deadlines_intervals_and_registration_closing_are_distinct(self):
        due = datetime.fromisoformat("2026-10-31T10:00:30.123456+07:00")
        start = datetime.fromisoformat("2026-10-30T17:00:00+00:00")
        end = datetime.fromisoformat("2026-10-31T02:00:00+00:00")
        registration = datetime.fromisoformat("2026-10-29T23:59:59+07:00")
        for kind in ("class", "assignment", "exam", "event", "personal", "tuition"):
            with self.subTest(kind=kind):
                row = task_record(record(type=kind, deadline=due, start_time=start, end_time=end,
                                         registration_end=registration))
                output = render_search({}, [row])
                for text in ("Due: 2026-10-31 10:00:30.123456 GMT+7", "Starts: 2026-10-31 00:00:00 GMT+7",
                             "Ends: 2026-10-31 09:00:00 GMT+7", "Registration closes: 2026-10-29 23:59:59 GMT+7"):
                    self.assertIn(text, output)
        row = task_record(record(type="tuition", registration_end=registration))
        self.assertIn("Due: Not provided", render_search({}, [row]))

    def test_naive_or_invalid_timestamps_are_rejected(self):
        for value in (datetime(2026, 10, 30), "2026-10-30T00:00:00", 42):
            with self.subTest(value=value), self.assertRaisesRegex(SearchOutputError, "timezone"):
                timestamp(value)

    def test_formatting_does_not_mutate_requests_metadata_or_results(self):
        request = {"keyword": "tình nguyện 5 điểm", "filters": {"statuses": ["active"], "course": "Tên môn"}}
        metadata = interpret_request(request)
        rows = [task_record(record(start_time=datetime.fromisoformat("2026-10-30T17:00:00+00:00")))]
        originals = deepcopy((request, metadata, rows))
        render_search(request, rows, metadata)
        render_search(request, rows)
        self.assertEqual((request, metadata, rows), originals)


if __name__ == "__main__":
    unittest.main()
