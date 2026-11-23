"""Authored matching and ordering expectations over fictional authorized records."""

from copy import deepcopy
from datetime import date, datetime
import unicodedata
import unittest
from unittest.mock import patch

from academic_search import SearchFilterError, SearchSnapshot, map_task, search_records
from test_search_records import task


IDS = {
    1: "11111111-1111-4111-8111-111111111111",
    2: "22222222-2222-4222-8222-222222222222",
    3: "33333333-3333-4333-8333-333333333333",
    4: "44444444-4444-4444-8444-444444444444",
    5: "55555555-5555-4555-8555-555555555555",
    6: "66666666-6666-4666-8666-666666666666",
}


def key(number, scope="public"):
    return scope, IDS[number]


def record(number, *, scope="public", **fields):
    return map_task(task(id=IDS[number], **fields), scope=scope)


def keys(records):
    return [record.key for record in records]


class SearchMatcherTests(unittest.TestCase):
    def test_exact_minimum_points_topic_and_effective_filters(self):
        records = tuple(record(n, title="Thiện nguyện", training_points=points)
                        for n, points in ((1, 4), (2, 5), (3, 7), (4, None)))
        for query, expected, bounds, topic in (
            ("5 điểm", [key(2)], {"min_training_points": 5, "max_training_points": 5}, ""),
            ("thiện nguyện 5 điểm", [key(2)], {"min_training_points": 5, "max_training_points": 5}, "thiện nguyện"),
            ("từ 5 điểm", [key(2), key(3)], {"min_training_points": 5}, ""),
            ("thiện nguyện từ 5 điểm", [key(2), key(3)], {"min_training_points": 5}, "thiện nguyện"),
        ):
            with self.subTest(query=query):
                result = search_records(records, query)
                self.assertEqual(keys(result.hits), expected)
                self.assertEqual(keys(result.eligible_records), expected)
                self.assertEqual(dict(result.effective_filters), {
                    "types": ("class", "assignment", "event", "announcement"), **bounds,
                })
                self.assertEqual(result.topic, topic)

    def test_zero_and_unknown_are_distinct(self):
        records = (record(1, training_points=0), record(2, training_points=None))
        self.assertEqual(keys(search_records(records).hits), [key(1), key(2)])
        self.assertEqual(keys(search_records(records, "0 điểm").hits), [key(1)])
        self.assertEqual(keys(search_records(records, filters={"max_training_points": 0}).hits), [key(1)])
        self.assertEqual(keys(search_records(records, "từ 0 điểm").hits), [key(1)])

    def test_description_cross_field_case_accents_and_punctuation(self):
        records = (
            record(1, title="Bản tin", description="THIỆN NGUYỆN"),
            record(2, title="Thiện đầu tuần", description="nguyện"),
            record(3, title="Thien nguyen"),
            record(4, title="50%_! O'Reilly", description="\\ ' OR 1=1 --"),
        )
        self.assertEqual(keys(search_records(records, "  THIỆN\tnguyện\n").hits), [key(1), key(2)])
        self.assertEqual(keys(search_records(records, "thien nguyen").hits), [key(3)])
        self.assertEqual(keys(search_records(records, "50%_! O'Reilly \\ ' OR 1=1 --").hits), [key(4)])
        self.assertEqual(search_records(records, "quantum pineapple").hits, ())
        self.assertEqual(search_records(records, "%wildcard").hits, ())

    def test_exact_course_only_and_exact_title_priority(self):
        records = (
            record(1, title="Các bài tập", course="CSC10004"),
            record(2, title="CSC10004 thông báo"),
            record(3, title="Thông báo", description="CSC10004"),
            record(4, title="CSC10004"),
        )
        self.assertEqual(keys(search_records(records, "csc10004").hits), [key(1), key(4), key(2), key(3)])
        self.assertEqual(keys(search_records(records, "csc100").hits), [key(2), key(4), key(3)])

    def test_all_sorts_keep_matching_keys_and_full_scope_ties(self):
        records = (
            record(4, title="Topic extra", description=None),
            record(3, title="Topic", deadline="2026-11-25T08:00:00+07:00"),
            record(2, title="Topic extra", deadline="2026-11-24T08:00:00+07:00"),
            record(1, title="Topic extra", scope="public", deadline="2026-11-24T08:00:00+07:00"),
            record(1, title="TOPIC extra", scope="personal", deadline="2026-11-24T01:00:00Z"),
            record(5, title="Other", description="topic"),
            record(6, title="Unmatched candidate"),
        )
        snapshot = SearchSnapshot(records, ("public", "personal"), 100)
        expected = {
            "best_match": [key(3), key(1, "personal"), key(1), key(2), key(4), key(5)],
            "soonest_deadline": [key(1, "personal"), key(1), key(2), key(3), key(4), key(5)],
            "latest_deadline": [key(3), key(1, "personal"), key(1), key(2), key(4), key(5)],
            "title": [key(5), key(3), key(1, "personal"), key(1), key(2), key(4)],
        }
        with patch("academic_search.loader.load_snapshot", side_effect=AssertionError("Unexpected fetch")):
            for sort, ordered in expected.items():
                with self.subTest(sort=sort):
                    result = search_records(snapshot.records, "topic", sort=sort)
                    self.assertEqual(keys(result.hits), ordered)
                    self.assertEqual(set(keys(result.hits)), set(expected["best_match"]))
                    self.assertEqual(result.eligible_records, records)
                    self.assertIn(key(6), keys(result.eligible_records))
                    self.assertNotIn(key(6), keys(result.hits))
        self.assertIs(snapshot.records, records)
        self.assertEqual(keys(search_records(records, "topic").hits), expected["best_match"])
        self.assertEqual(search_records(records).sort, "soonest_deadline")
        self.assertEqual(keys(search_records(records).hits),
                         [key(1, "personal"), key(1), key(2), key(3), key(4), key(5), key(6)])

    def test_combined_filters_for_blank_and_point_only_queries(self):
        records = (
            record(1, type="assignment", course="CSC10004", training_points=5,
                   deadline="2026-11-23T17:30:00Z"),
            record(2, type="assignment", course="CSC10004", training_points=7,
                   deadline="2026-11-25T23:59:59+07:00"),
            record(3, type="class", course="CSC10004", training_points=5),
            record(4, type="assignment", course="CSC10005", training_points=5),
            record(5, type="assignment", course="CSC10004", training_points=None),
        )
        filters = {"types": ["assignment"], "course": "csc10004", "min_training_points": 5,
                   "max_training_points": 7, "deadline_start": "2026-11-24",
                   "deadline_end": date(2026, 11, 25)}
        before = deepcopy(filters)
        for query in ("", " \t\n", "từ 5 điểm"):
            with self.subTest(query=query):
                result = search_records(records, query, filters=filters)
                self.assertEqual(keys(result.hits), [key(1), key(2)])
                self.assertEqual(result.sort, "soonest_deadline")
                self.assertEqual(result.effective_filters["deadline_start"], date(2026, 11, 24))
        self.assertEqual(filters, before)
        self.assertEqual(keys(search_records(records, "5 điểm", filters=filters).hits), [key(1)])
        self.assertEqual(search_records(records, filters={"course": "CSC1000"}).hits, ())

    def test_inclusive_local_dates_single_bounds_and_undated(self):
        records = (
            record(1, deadline="2026-11-23T16:59:59Z"),
            record(2, deadline="2026-11-23T17:00:00Z"),
            record(3, deadline="2026-11-24T16:59:59.999999Z"),
            record(4, deadline="2026-11-24T17:00:00Z"),
            record(5),
        )
        for filters, expected in (
            ({}, [key(1), key(2), key(3), key(4), key(5)]),
            ({"deadline_start": "2026-11-24", "deadline_end": "2026-11-24"}, [key(2), key(3)]),
            ({"deadline_start": "2026-11-24"}, [key(2), key(3), key(4)]),
            ({"deadline_end": "2026-11-24"}, [key(1), key(2), key(3)]),
        ):
            with self.subTest(filters=filters):
                self.assertEqual(keys(search_records(records, filters=filters).hits), expected)

    def test_historical_point_aliases_intersections_and_type_inference(self):
        event = record(1, type="event", title="Thiện nguyện", training_points=5,
                       training_point_category="Articles 3", estimated_hours=2)
        records = (event, record(2, title="Thiện nguyện", training_points=7))
        for query in ("5 điểm rèn luyện", "5 đrl", "000005 điểm",
                      unicodedata.normalize("NFD", "  TỪ 5 ĐIỂM RÈN LUYỆN SỰ KIỆN Thiện nguyện")):
            with self.subTest(query=query):
                result = search_records(records, query, filters={"max_training_points": 6})
                self.assertEqual(keys(result.hits), [key(1)])
        result = search_records(records, "sự kiện 5 điểm", filters={"types": ["event", "class"]})
        self.assertEqual(result.effective_filters["types"], ("event",))
        self.assertEqual(result.topic, "")
        result = search_records(records, "từ 5 điểm", filters={"min_training_points": 7})
        self.assertEqual(keys(result.hits), [key(2)])
        self.assertEqual(result.effective_filters["min_training_points"], 7)

    def test_conflicts_unsupported_grammar_and_invalid_inputs(self):
        for query in (
            "không phải 5 điểm", "không có 5 điểm", "3-5 điểm", "2.5 điểm", "2,5 điểm",
            "-5 điểm", "+5 điểm", "tối đa 5 điểm", "hơn 5 điểm", "ít nhất 5 điểm",
            ">= 5 điểm", "từ 3 đến 5 điểm", "5 điểm trở lên", "5 điểm 5 đrl", "101 điểm",
        ):
            with self.subTest(query=query), self.assertRaises(SearchFilterError):
                search_records((), query)
        for query, filters in (
            ("5 điểm", {"min_training_points": 7}),
            ("từ 5 điểm", {"max_training_points": 3}),
            ("sự kiện 5 điểm", {"types": ["announcement"]}),
            ("", {"deadline_start": "2026-11-25", "deadline_end": "2026-11-24"}),
            ("", {"deadline_end": "2026-02-30"}),
            ("", {"deadline_start": datetime(2026, 11, 23)}),
            ("", {"min_training_points": True}),
            ("", {"types": ["personal"]}),
            ("", {"types": []}),
            ("", {"unknown": True}),
        ):
            with self.subTest(filters=filters), self.assertRaises(SearchFilterError):
                search_records((), query, filters=filters)
        with self.assertRaises(SearchFilterError):
            search_records((), None)
        with self.assertRaises(SearchFilterError):
            search_records((), sort="unknown")


if __name__ == "__main__":
    unittest.main()
