"""Driver-independent checks of PostgreSQL SQL and the shared-manager boundary."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from academic_search import SearchDatabaseError, SearchService, SearchValidationError
from academic_search.postgres import TASK_FIELDS, compile_request, task_record
from academic_search.validation import TYPES, validate_request

NOW = datetime(2026, 10, 30, 5, tzinfo=timezone.utc)
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]


def record(**changes):
    task = dict.fromkeys(TASK_FIELDS)
    task.update(id="Task_é 1", title="Search example", type="personal", course="Tên môn",
                training_points=0, status="active", is_manual=False,
                source_platform="custom", updated_at=NOW)
    task.update(changes)
    return tuple(task[field] for field in TASK_FIELDS)


class Cursor:
    def __init__(self):
        self.execute = Mock()
        self.fetchone = Mock(return_value=None)
        self.fetchall = Mock(return_value=[])
        self.close = Mock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PostgreSQLSearchTests(unittest.TestCase):
    def setUp(self):
        self.cursor = Cursor()
        self.connection = Mock()
        self.connection.cursor.return_value = self.cursor
        self.manager = SimpleNamespace(connection=self.connection)
        self.search = SearchService(self.manager, user_id=7)

    def sql(self):
        return self.cursor.execute.call_args.args

    def test_lookup_uses_schema_ids_and_user_scope_across_all_statuses(self):
        self.cursor.fetchone.return_value = record(status="cancelled")
        task = self.search.get_task_by_id("  Task_é 1  ")
        sql, params = self.sql()
        self.assertEqual(params, ["Task_é 1", 7])
        self.assertIn('t.id COLLATE "C" = %s', sql)
        self.assertIn("ut.task_id = t.id AND ut.user_id = %s", sql)
        self.assertNotIn("t.status IN", sql)
        self.assertNotIn("daily_tasks", sql)
        self.assertEqual(task["status"], "cancelled")
        self.assertEqual(set(task), set(TASK_FIELDS))

    def test_absent_or_unassigned_lookup_is_none_and_empty_search_is_list(self):
        self.assertIsNone(self.search.get_task_by_id("missing"))
        self.assertEqual(self.search.search_tasks({}), [])
        sql, params = self.sql()
        self.assertIn("EXISTS (SELECT 1 FROM user_tasks", sql)
        self.assertNotIn("t.type IN", sql)
        self.assertEqual(params, [7, "active", 20, 0])

    def test_all_six_types_are_returned_without_type_filter(self):
        self.cursor.fetchall.return_value = [record(type=value) for value in sorted(TYPES)]
        tasks = self.search.search_tasks({"limit": 100})
        self.assertEqual({task["type"] for task in tasks}, set(TYPES))
        self.assertNotIn("t.type IN", self.sql()[0])

    def test_combined_filters_are_parameterized_and_prefix_is_literal(self):
        text = "CS2_%'\\ OR 1=1 --"
        request = {"filters": {"course": "Cấu trúc dữ liệu", "types": ["class", "exam"],
                               "statuses": ["done", "cancelled"], "source_platform": "portal",
                               "source_platforms": ["portal", "custom"], "target_audience": "K26",
                               "location_prefix": text, "min_training_points": 0,
                               "max_training_points": 10},
                   "sort": "training_points", "direction": "desc", "limit": 9, "offset": 3}
        self.search.search_tasks(request)
        sql, params = self.sql()
        self.assertEqual(params, [7, "done", "cancelled", "class", "exam", "portal", "custom",
                                  "Cấu trúc dữ liệu", "portal", "K26", text, text, 0, 10, 9, 3])
        self.assertEqual(sql.count("%s"), len(params))
        self.assertNotIn(text, sql)
        self.assertNotIn("Cấu trúc dữ liệu", sql)
        self.assertNotIn("course_code", sql)
        self.assertNotIn(" LIKE ", sql)
        self.assertIn('left(t.location, char_length(%s)) COLLATE "C" = %s', sql)
        self.assertIn('ORDER BY t.training_points DESC NULLS LAST, t.id COLLATE "C" ASC', sql)
        self.assertTrue(sql.endswith("LIMIT %s OFFSET %s"))

    def test_time_predicates_bind_aware_datetimes_and_keep_distinct_boundaries(self):
        for key, field in (("deadline_within", "deadline"), ("registration_end_within", "registration_end"),
                           ("start_time_within", "start_time"), ("updated_at_within", "updated_at")):
            with self.subTest(key=key):
                self.search.search_tasks({"filters": {key: DAY}})
                sql, params = self.sql()
                self.assertIn(f"(t.{field} >= %s AND t.{field} < %s)", sql)
                self.assertEqual(params[2:4], [NOW - timedelta(hours=12), NOW + timedelta(hours=12)])
                self.assertTrue(all(value.tzinfo is timezone.utc for value in params[2:4]))
        self.search.search_tasks({"filters": {"event_overlaps": DAY, "registration_open_at": NOW.isoformat()}})
        sql, params = self.sql()
        self.assertIn("t.start_time < t.end_time AND t.start_time < %s AND t.end_time > %s", sql)
        self.assertIn("t.registration_start <= %s AND t.registration_end >= %s", sql)
        self.assertEqual(params[2:6], [NOW + timedelta(hours=12), NOW - timedelta(hours=12), NOW, NOW])
        self.assertNotIn("COALESCE", sql)

    def test_sort_allowlists_nulls_and_id_ties(self):
        for sort in ("id", "deadline", "start_time", "updated_at", "training_points"):
            for direction in ("asc", "desc"):
                with self.subTest(sort=sort, direction=direction):
                    self.search.search_tasks({"sort": sort, "direction": direction})
                    order = self.sql()[0].split("ORDER BY ")[1]
                    if sort == "id":
                        self.assertEqual(order, f't.id COLLATE "C" {direction.upper()} LIMIT %s OFFSET %s')
                    else:
                        self.assertEqual(order, f't.{sort} {direction.upper()} NULLS LAST, t.id COLLATE "C" ASC LIMIT %s OFFSET %s')

    def test_rows_keep_nulls_zero_unicode_and_aware_timestamp_objects(self):
        row = record(deadline=NOW.astimezone(timezone(timedelta(hours=7))))
        task = task_record(row)
        self.assertEqual(task["training_points"], 0)
        self.assertIsNone(task["registration_end"])
        self.assertEqual(task["course"], "Tên môn")
        self.assertEqual(task["deadline"], NOW)
        self.assertIs(task["updated_at"], NOW)
        self.assertNotIn("embedding", task)
        self.assertNotIn("course_code", task)
        mapping = {**task, "work_date": "extra"}
        self.assertEqual(task_record(mapping), task)
        self.assertIsNot(task_record(mapping), mapping)
        self.cursor.fetchall.return_value = [row]
        self.assertEqual(self.search.search_tasks({}), [task])

    def test_invalid_input_does_not_access_database(self):
        for request in ({"filters": {"course_code": "CSC10004"}}, {"filters": {"course": None}},
                        {"sort": "id; DROP TABLE tasks"}, {"direction": "DESC"},
                        {"limit": True}, {"filters": {"event_overlaps": DAY[::-1]}},
                        {"filters": {"types": []}}):
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                self.search.search_tasks(request)
        for task_id in (None, "", "a" * 65, "bad\x00id"):
            with self.subTest(task_id=task_id), self.assertRaises(SearchValidationError):
                self.search.get_task_by_id(task_id)
        self.assertEqual(self.connection.mock_calls, [])
        for user_id in (None, True, 0, -1, "7", 2_147_483_648):
            with self.subTest(user_id=user_id), self.assertRaises(SearchValidationError):
                SearchService(self.manager, user_id=user_id)

    def test_compilation_does_not_revalidate(self):
        request = validate_request({"filters": {"deadline_within": DAY}})
        with patch("academic_search.validation.parse_instant", side_effect=AssertionError("reparsed")):
            _, params = compile_request(request, 7)
        self.assertIsInstance(params[2], datetime)

    def test_database_errors_retain_cause_and_never_become_empty_results(self):
        for lookup in (False, True):
            for method_name in ("cursor", "execute", "fetchone" if lookup else "fetchall"):
                target = self.connection if method_name == "cursor" else self.cursor
                method = getattr(target, method_name)
                error = RuntimeError("database unavailable")
                method.side_effect = error
                with self.subTest(lookup=lookup, method=method_name), self.assertRaises(SearchDatabaseError) as caught:
                    if lookup:
                        self.search.get_task_by_id("Task_1")
                    else:
                        self.search.search_tasks({})
                self.assertIs(caught.exception.__cause__, error)
                method.side_effect = None
                self.connection.commit.assert_not_called()
                self.connection.rollback.assert_not_called()
                self.connection.close.assert_not_called()

    def test_cursors_close_on_success_and_failure_but_connection_is_borrowed(self):
        self.search.search_tasks({})
        self.cursor.close.assert_called_once_with()
        self.cursor.close.reset_mock()
        self.cursor.execute.side_effect = RuntimeError("query failed")
        with self.assertRaises(SearchDatabaseError):
            self.search.get_task_by_id("Task_1")
        self.cursor.close.assert_called_once_with()
        self.assertEqual([call[0] for call in self.connection.mock_calls], ["cursor", "cursor"])
        replacement = Mock()
        replacement.cursor.return_value = Cursor()
        self.manager.connection = replacement
        self.search.search_tasks({})
        replacement.cursor.assert_called_once_with()

    def test_bad_database_records_are_errors(self):
        for row in ((1,), record(updated_at=NOW.replace(tzinfo=None)), record(updated_at=None)):
            self.cursor.fetchall.return_value = [row]
            with self.subTest(row=row), self.assertRaises(SearchDatabaseError) as caught:
                self.search.search_tasks({})
            self.assertIsInstance(caught.exception.__cause__, ValueError)


if __name__ == "__main__":
    unittest.main()
