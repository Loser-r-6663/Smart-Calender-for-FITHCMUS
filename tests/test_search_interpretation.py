"""Offline grammar, intersection, and existing service execution checks."""
from copy import deepcopy
import unicodedata
import unittest
from unittest.mock import Mock

from academic_search import (SearchDatabaseError, SearchInterpretationError, SearchService, SearchValidationError,
                             interpret_request)
from academic_search.postgres import compile_request
from academic_search.validation import validate_request
from test_postgres_search import Cursor, record


class InterpretationTests(unittest.TestCase):
    def test_required_expressions_and_exact_metadata(self):
        for query, keyword, inferred in (
            ("5 điểm rèn luyện", "", {"min_training_points": 5, "max_training_points": 5}),
            ("5 đrl", "", {"min_training_points": 5, "max_training_points": 5}),
            ("5 điểm", "", {"min_training_points": 5, "max_training_points": 5}),
            ("từ 5 điểm", "", {"min_training_points": 5}),
            ("từ 5 điểm rèn luyện", "", {"min_training_points": 5}),
            ("từ 5 đrl", "", {"min_training_points": 5}),
            ("sự kiện 5 điểm", "", {"min_training_points": 5, "max_training_points": 5, "types": ["event"]}),
            ("tình nguyện 5 điểm", "tình nguyện", {"min_training_points": 5, "max_training_points": 5}),
        ):
            with self.subTest(query=query):
                result = interpret_request({"keyword": query})
                self.assertEqual(result.original_query, query)
                self.assertEqual(result.remaining_keyword, keyword)
                self.assertEqual(result.inferred_filters, inferred)
                self.assertEqual(result.effective_filters, {"statuses": ["active"], **inferred})

    def test_normalization_longest_match_and_remaining_spans(self):
        query = unicodedata.normalize("NFD", "  TỪ\t5 ĐIỂM\n RÈN LUYỆN  SỰ KIỆN  Tình  nguyện ")
        result = interpret_request({"keyword": query})
        self.assertEqual(result.original_query, query)
        self.assertEqual(result.remaining_keyword, "Tình nguyện")
        self.assertEqual(result.inferred_filters, {"min_training_points": 5, "types": ["event"]})
        result = interpret_request({"keyword": "trước sự kiện 5 điểm rèn luyện sau"})
        self.assertEqual(result.remaining_keyword, "trước sau")
        result = interpret_request({"keyword": "sự 5 điểm kiện"})
        self.assertNotIn("types", result.inferred_filters)
        self.assertEqual(result.remaining_keyword, "sự kiện")
        self.assertEqual(interpret_request({"keyword": "(5 đrl)"}).remaining_keyword, "( )")

    def test_ordinary_and_blank_queries_retain_keyword_behavior(self):
        for query in ("", " \t\n ", "sự kiện tình nguyện", "5 diem", "x5 điểm", "5 điểmX",
                      "50%_! O'Reilly \\", unicodedata.normalize("NFD", "Tình nguyện")):
            with self.subTest(query=query):
                raw = {"keyword": query, "sort": "id"}
                result = interpret_request(raw)
                self.assertEqual(result.inferred_filters, {})
                self.assertEqual(compile_request(validate_request(raw), 7), compile_request(validate_request({
                    **raw, "keyword": result.remaining_keyword, "filters": result.effective_filters}), 7))

    def test_points_use_existing_validation_boundaries(self):
        for number in (0, 100):
            for prefix in ("", "từ "):
                result = interpret_request({"keyword": f"{prefix}{number} đrl"})
                self.assertEqual(result.inferred_filters["min_training_points"], number)
        for number in (101, 9999999999999999999999999999999):
            with self.subTest(number=number), self.assertRaises(SearchValidationError):
                interpret_request({"keyword": f"{number} điểm"})
        self.assertEqual(interpret_request({"keyword": "000005 điểm"}).inferred_filters,
                         {"min_training_points": 5, "max_training_points": 5})

    def test_unsupported_and_multiple_expressions_fail_explicitly(self):
        for query in ("không phải 5 điểm", "không 5 đrl", "không có 5 điểm", "5 điểm nhưng không sự kiện",
                      "không phải sự kiện 5 điểm", "3-5 điểm", "3 – 5 điểm",
                      "2.5 điểm", "2,5 điểm", "-5 điểm", "+5 điểm", "tối đa 5 điểm",
                      "hơn 5 điểm", "ít nhất 5 điểm", "dưới 5 điểm", ">= 5 điểm",
                      "từ 3 đến 5 điểm", "5 điểm trở lên", "5 điểm đến 10 điểm"):
            with self.subTest(query=query), self.assertRaises(SearchInterpretationError):
                interpret_request({"keyword": query})
        for query in ("5 điểm 5 đrl", "từ 5 điểm và 7 điểm", "5 điểm rèn luyện 5 điểm"):
            with self.subTest(query=query), self.assertRaisesRegex(SearchInterpretationError, "Ambiguous"):
                interpret_request({"keyword": query})

    def test_intersections_preserve_unrelated_selections_without_mutation(self):
        for query, selected, expected in (
            ("5 điểm", {"min_training_points": 3}, {"min_training_points": 5, "max_training_points": 5}),
            ("từ 5 điểm", {"max_training_points": 10}, {"min_training_points": 5, "max_training_points": 10}),
            ("từ 5 điểm", {"min_training_points": 7}, {"min_training_points": 7}),
            ("5 điểm", {"max_training_points": 10}, {"min_training_points": 5, "max_training_points": 5}),
            ("sự kiện 5 điểm", {"types": ["event", "personal"]},
             {"types": ["event"], "min_training_points": 5, "max_training_points": 5}),
        ):
            raw = {"keyword": query, "filters": {"statuses": ["done"], "course": "Tên môn", **selected},
                   "sort": "id", "limit": 3, "offset": 2}
            before = deepcopy(raw)
            result = interpret_request(raw)
            self.assertEqual(result.effective_filters, {"statuses": ["done"], "course": "Tên môn", **expected})
            self.assertEqual(raw, before)
            result.effective_filters["statuses"].append("active")
            self.assertEqual(raw, before)
        for query, filters in (("5 điểm", {"max_training_points": 3}),
                               ("5 điểm", {"min_training_points": 7}),
                               ("từ 5 điểm", {"max_training_points": 3}),
                               ("sự kiện 5 điểm", {"types": ["exam"]})):
            with self.subTest(query=query, filters=filters), self.assertRaisesRegex(SearchInterpretationError, "Conflicting"):
                interpret_request({"keyword": query, "filters": filters})

    def test_invalid_existing_inputs_stay_invalid(self):
        for raw in ({"keyword": None}, {"keyword": "5 điểm", "filters": {"types": []}},
                    {"keyword": "5 điểm", "filters": {"min_training_points": True}},
                    {"keyword": "5 điểm", "filters": {"course_code": "CSC10004"}},
                    {"keyword": "5 điểm", "limit": 0}, {"keyword": "5 điểm\x00"}):
            with self.subTest(raw=raw), self.assertRaises(SearchValidationError):
                interpret_request(raw)

    def test_service_reuses_sql_and_preserves_existing_methods_and_ownership(self):
        cursor = Cursor()
        connection = Mock()
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = [record(training_points=5)]
        search = SearchService.from_connection(connection, user_id=7)
        raw = {"keyword": "tình nguyện 5 điểm", "sort": "id", "limit": 4}
        before = deepcopy(raw)
        result = search.interpret_and_search(raw)
        self.assertEqual(result.results[0]["training_points"], 5)
        self.assertEqual(result.interpretation.remaining_keyword, "tình nguyện")
        self.assertEqual(cursor.execute.call_args.args, tuple(compile_request(validate_request({
            **raw, "keyword": "tình nguyện", "filters": {"min_training_points": 5, "max_training_points": 5}}), 7)))
        self.assertEqual(raw, before)
        search.search_tasks(raw)
        self.assertIn("%5%", cursor.execute.call_args.args[1])
        self.assertNotIn("t.training_points >=", cursor.execute.call_args.args[0])
        with self.assertRaises(SearchInterpretationError):
            search.interpret_and_search({"keyword": "hơn 5 điểm"})
        self.assertEqual([call[0] for call in connection.mock_calls], ["cursor", "cursor"])
        cursor.fetchall.return_value = []
        self.assertEqual(search.interpret_and_search({"keyword": "missing 5 điểm"}).results, [])
        cursor.execute.side_effect = RuntimeError("database unavailable")
        with self.assertRaises(SearchDatabaseError):
            search.interpret_and_search({"keyword": "5 điểm"})


if __name__ == "__main__":
    unittest.main()
