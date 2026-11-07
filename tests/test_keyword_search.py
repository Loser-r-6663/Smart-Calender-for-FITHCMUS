"""Offline validation, SQL binding and service-boundary checks for keyword search."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from academic_search import SearchDatabaseError, SearchService, SearchValidationError
from academic_search.postgres import compile_request, literal_contains_pattern
from academic_search.sqlite_service import validate_sqlite_request
from academic_search.validation import validate_request
from test_postgres_search import Cursor, record


class KeywordValidationTests(unittest.TestCase):
    def test_whitespace_splitting_preserves_accents_case_and_literals(self):
        request = validate_request({"keyword": " \tTÌNH\n  nguyện\u00a0 50%_! 'OR' "})
        self.assertEqual(request.terms, ("TÌNH", "nguyện", "50%_!", "'OR'"))
        self.assertEqual(validate_request({"keyword": "nguyện tình"}).terms, ("nguyện", "tình"))
        self.assertEqual(validate_request({"keyword": "x x"}).terms, ("x", "x"))

    def test_blank_and_missing_keyword_preserve_structured_request_and_sql(self):
        raw = {"filters": {"types": ["class", "tuition"], "course": "CSC10004"},
               "sort": "deadline", "direction": "desc", "limit": 7, "offset": 2}
        expected = validate_request(raw)
        for text in ("", " ", "\t\n\u00a0 "):
            with self.subTest(text=text):
                normalized = validate_request({**raw, "keyword": text})
                self.assertEqual(normalized, expected)
                self.assertEqual(compile_request(normalized, 7), compile_request(expected, 7))
        self.assertEqual(expected.terms, ())

    def test_invalid_keyword_types_and_unknown_aliases(self):
        for value in (None, True, 1, 1.5, [], {}, ["term"]):
            with self.subTest(value=value), self.assertRaisesRegex(SearchValidationError, "keyword must be a string"):
                validate_request({"keyword": value})
        with self.assertRaisesRegex(SearchValidationError, "NUL"):
            validate_request({"keyword": "bad\x00text"})
        for request in ({"query": "term"}, {"semantic_text": "term"}, {"filters": {"keyword": "term"}}):
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                validate_request(request)

    def test_sqlite_explicitly_rejects_keyword_instead_of_ignoring_it(self):
        for value in ("", "tuition", None):
            with self.subTest(value=value), self.assertRaises(SearchValidationError):
                validate_sqlite_request({"keyword": value})


class KeywordCompilationTests(unittest.TestCase):
    def test_literal_patterns_escape_marker_wildcards_and_keep_backslashes(self):
        for term, expected in [("%", "%!%%"), ("_", "%!_%"), ("!", "%!!%"),
                               ("!%_", "%!!!%!_%"), ("\\", "%\\%"),
                               ("O'Reilly", "%O'Reilly%"), ('"term"', '%"term"%')]:
            with self.subTest(term=term):
                self.assertEqual(literal_contains_pattern(term), expected)

    def test_terms_have_grouped_or_fields_and_are_anded_with_all_filters(self):
        request = validate_request({"keyword": "tình nguyện", "filters": {
            "types": ["class", "event"], "course": "Tên môn", "min_training_points": 5},
            "sort": "deadline", "direction": "desc", "limit": 3, "offset": 2})
        sql, params = compile_request(request, 7)
        term_sql = "(t.title ILIKE %s ESCAPE '!' OR t.description ILIKE %s ESCAPE '!')"
        self.assertIn(term_sql + " AND " + term_sql + " AND t.type IN", sql)
        self.assertEqual(params, [7, "active", "%tình%", "%tình%", "%nguyện%", "%nguyện%",
                                  "class", "event", "Tên môn", 5, 3, 2])
        self.assertEqual(sql.count("%s"), len(params))
        self.assertIn("ut.task_id = t.id AND ut.user_id = %s", sql)
        self.assertIn('ORDER BY t.deadline DESC NULLS LAST, t.id COLLATE "C" ASC LIMIT %s OFFSET %s', sql)
        self.assertNotIn("tình", sql)
        self.assertNotIn("COALESCE", sql)
        self.assertNotIn("rank", sql.lower())

    def test_sql_looking_terms_are_bound_and_do_not_change_query_structure(self):
        sql, params = compile_request(validate_request({"keyword": "O'Reilly %_! \\ ' OR 1=1 --"}), 7)
        self.assertEqual(params[2:-2], ["%O'Reilly%", "%O'Reilly%", "%!%!_!!%", "%!%!_!!%",
                                        "%\\%", "%\\%", "%'%", "%'%", "%OR%", "%OR%",
                                        "%1=1%", "%1=1%", "%--%", "%--%"])
        self.assertNotIn("O'Reilly", sql)
        self.assertNotIn("1=1", sql)
        self.assertNotIn("--", sql)
        self.assertEqual(sql.count("%s"), len(params))
        self.assertNotIn("t.type IN", sql)

    def test_service_errors_results_lookup_and_connection_ownership(self):
        cursor = Cursor()
        connection = Mock()
        connection.cursor.return_value = cursor
        search = SearchService(SimpleNamespace(connection=connection), user_id=7)
        with self.assertRaises(SearchValidationError):
            search.search_tasks({"keyword": None})
        self.assertEqual(connection.mock_calls, [])
        self.assertEqual(search.search_tasks({"keyword": "missing"}), [])
        cursor.fetchall.return_value = [record(description=None)]
        result = search.search_tasks({"keyword": "Search"})
        self.assertEqual([task["id"] for task in result], ["Task_é 1"])
        self.assertIsNone(result[0]["description"])
        cursor.fetchone.return_value = record(status="cancelled")
        self.assertEqual(search.get_task_by_id("Task_é 1")["status"], "cancelled")
        self.assertNotIn("ILIKE", cursor.execute.call_args.args[0])
        failure = RuntimeError("database unavailable")
        cursor.execute.side_effect = failure
        with self.assertRaises(SearchDatabaseError) as caught:
            search.search_tasks({"keyword": "Search"})
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(cursor.close.call_count, 4)
        self.assertEqual([call[0] for call in connection.mock_calls], ["cursor"] * 4)


if __name__ == "__main__":
    unittest.main()
