"""Exercise Search with the real transaction provider and fake PostgreSQL connections."""
import unittest
from contextlib import ExitStack
from importlib.util import find_spec
from unittest.mock import Mock, call, patch

from academic_search import (
    InterpretedSearch,
    SearchDatabaseError,
    SearchInterpretationError,
    SearchService,
    SearchValidationError,
    TransactionalSearch,
)
from academic_search.postgres import USER_SCOPE
from test_postgres_search import Cursor, record


@unittest.skipUnless(all(find_spec(name) for name in ("psycopg2", "dotenv", "pydantic")),
                     "Requires the database manager's Python dependencies")
class TransactionalSearchTests(unittest.TestCase):
    def setUp(self):
        from Database.database_manager import DatabaseManager
        from Database.db_connection import DatabaseConnection

        # Use the production transaction method without loading local credentials.
        with patch("Database.db_connection.load_dotenv"):
            database = DatabaseConnection()
        self.manager = DatabaseManager(database=database)
        self.connection, self.cursor, self.events = self.make_connection()
        patches = ExitStack()
        self.addCleanup(patches.close)
        self.connect = patches.enter_context(patch.object(database, "connect", return_value=self.connection))
        self.transaction = patches.enter_context(patch.object(database, "transaction", wraps=database.transaction))
        self.search = TransactionalSearch(self.manager, user_id=7)

    def make_connection(self):
        connection = Mock(spec=["cursor", "commit", "rollback", "close"])
        cursor = Cursor()
        connection.cursor.return_value = cursor
        events = Mock()
        events.attach_mock(connection, "connection")
        for method in ("execute", "fetchone", "fetchall", "close"):
            events.attach_mock(getattr(cursor, method), f"cursor_{method}")
        return connection, cursor, events

    def assert_transaction(self, fetch_method="fetchall", *, rollback=False):
        self.transaction.assert_called_once_with()
        self.connect.assert_called_once_with()
        sql, params = self.cursor.execute.call_args.args
        outcome = call.connection.rollback() if rollback else call.connection.commit()
        self.assertEqual(self.events.mock_calls, [
            call.connection.cursor(),
            call.cursor_execute(sql, params),
            getattr(call, f"cursor_{fetch_method}")(),
            call.cursor_close(),
            outcome,
            call.connection.close(),
        ])
        self.assertIn(USER_SCOPE, sql)
        return sql, params

    def test_lookup_keeps_exact_id_and_all_statuses(self):
        self.cursor.fetchone.return_value = record(status="cancelled")
        result = self.search.get_task_by_id("  Task_é 1  ")
        sql, params = self.assert_transaction("fetchone")
        self.assertEqual(params, ["Task_é 1", 7])
        self.assertNotIn("t.status IN", sql)
        self.assertEqual(result["status"], "cancelled")

    def test_search_preserves_literal_keyword_filters_sorting_and_pagination(self):
        self.cursor.fetchall.return_value = [record(id="first"), record(id="second")]
        result = self.search.search_tasks({
            "keyword": "50%_!",
            "filters": {"course": "CSC10004"},
            "sort": "training_points",
            "direction": "desc",
            "limit": 2,
            "offset": 4,
        })
        sql, params = self.assert_transaction()
        self.assertEqual(params, [7, "active", "%50!%!_!!%", "%50!%!_!!%", "CSC10004", 2, 4])
        self.assertIn('ORDER BY t.training_points DESC NULLS LAST, t.id COLLATE "C" ASC', sql)
        self.assertEqual([task["id"] for task in result], ["first", "second"])

    def test_interpreted_search_preserves_metadata_in_one_transaction(self):
        self.cursor.fetchall.return_value = [record(type="event", training_points=5)]
        result = self.search.interpret_and_search({"keyword": "sự kiện thiện nguyện 5 điểm"})
        _, params = self.assert_transaction()
        self.assertIsInstance(result, InterpretedSearch)
        self.assertEqual(params, [7, "active", "%thiện%", "%thiện%", "%nguyện%", "%nguyện%",
                                  "event", 5, 5, 20, 0])
        self.assertEqual(result.interpretation.original_query, "sự kiện thiện nguyện 5 điểm")
        self.assertEqual(result.interpretation.remaining_keyword, "thiện nguyện")
        self.assertEqual(result.interpretation.inferred_filters, {
            "types": ["event"], "min_training_points": 5, "max_training_points": 5,
        })
        self.assertEqual(result.interpretation.effective_filters, {
            **result.interpretation.inferred_filters, "statuses": ["active"],
        })
        self.assertEqual(result.results[0]["training_points"], 5)

    def test_missing_lookup_is_none(self):
        self.assertIsNone(self.search.get_task_by_id("missing"))
        self.assert_transaction("fetchone")

    def test_empty_search_is_a_list(self):
        self.assertEqual(self.search.search_tasks({}), [])
        self.assert_transaction()

    def test_invalid_inputs_never_enter_a_transaction(self):
        for user_id in (None, True, 0, -1, "7", 2_147_483_648):
            with self.subTest(user_id=user_id), self.assertRaises(SearchValidationError):
                TransactionalSearch(self.manager, user_id=user_id)
        for operation, request, error in (
            (self.search.get_task_by_id, "  ", SearchValidationError),
            (self.search.search_tasks, {"limit": True}, SearchValidationError),
            (self.search.search_tasks, {"filters": {"registration_open_at": "2026-10-30"}}, SearchValidationError),
            (self.search.interpret_and_search, {"offset": -1}, SearchValidationError),
            (self.search.interpret_and_search, {"keyword": "hơn 5 điểm"}, SearchInterpretationError),
            (self.search.interpret_and_search, {
                "keyword": "sự kiện 5 điểm", "filters": {"types": ["exam"]},
            }, SearchInterpretationError),
        ):
            with self.subTest(request=request), self.assertRaises(error) as caught:
                operation(request)
            self.assertIs(type(caught.exception), error)
        self.transaction.assert_not_called()
        self.connect.assert_not_called()

    def test_acquisition_failure_is_chained(self):
        failure = ValueError("missing connection configuration")
        self.connect.side_effect = failure
        with self.assertRaises(SearchDatabaseError) as caught:
            self.search.search_tasks({})
        self.assertIs(caught.exception.__cause__, failure)
        self.transaction.assert_called_once_with()
        self.connect.assert_called_once_with()
        self.assertEqual(self.events.mock_calls, [])

    def test_query_failure_closes_cursor_and_rolls_back_before_next_call(self):
        next_connection, next_cursor, next_events = self.make_connection()
        self.connect.side_effect = [self.connection, next_connection]
        failure = RuntimeError("query failed")
        self.cursor.execute.side_effect = failure
        with self.assertRaises(SearchDatabaseError) as caught:
            self.search.search_tasks({})
        self.assertIs(caught.exception.__cause__, failure)
        sql, params = self.cursor.execute.call_args.args
        self.assertEqual(self.events.mock_calls, [
            call.connection.cursor(), call.cursor_execute(sql, params), call.cursor_close(),
            call.connection.rollback(), call.connection.close(),
        ])
        next_cursor.fetchone.return_value = record(id="fresh")
        self.assertEqual(self.search.get_task_by_id("fresh")["id"], "fresh")
        self.assertEqual(self.connect.call_args_list, [call(), call()])
        self.assertEqual(self.transaction.call_args_list, [call(), call()])
        self.assertEqual(next_events.mock_calls[-3:], [
            call.cursor_close(), call.connection.commit(), call.connection.close(),
        ])

    def test_row_conversion_failure_closes_cursor_and_rolls_back(self):
        self.cursor.fetchall.return_value = [record(), record(updated_at=None)]
        with self.assertRaises(SearchDatabaseError) as caught:
            self.search.search_tasks({})
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertIn("updated_at", str(caught.exception.__cause__))
        self.assert_transaction(rollback=True)

    def test_commit_failure_prevents_result_and_rolls_back(self):
        self.assert_completion_failure("commit", [
            call.connection.commit(), call.connection.rollback(), call.connection.close(),
        ])

    def test_close_failure_prevents_result_after_commit(self):
        self.assert_completion_failure("close", [call.connection.commit(), call.connection.close()])

    def assert_completion_failure(self, method, completion_calls):
        self.cursor.fetchall.return_value = [record()]
        failure = RuntimeError(f"{method} failed")
        getattr(self.connection, method).side_effect = failure
        with self.assertRaises(SearchDatabaseError) as caught:
            self.search.search_tasks({})
        self.assertIs(caught.exception.__cause__, failure)
        self.transaction.assert_called_once_with()
        self.connect.assert_called_once_with()
        sql, params = self.cursor.execute.call_args.args
        self.assertEqual(self.events.mock_calls, [
            call.connection.cursor(), call.cursor_execute(sql, params), call.cursor_fetchall(),
            call.cursor_close(), *completion_calls,
        ])

    def test_rollback_failure_preserves_failure_chain_and_closes_connection(self):
        query_error = RuntimeError("query failed")
        rollback_error = RuntimeError("rollback failed")
        self.cursor.execute.side_effect = query_error
        self.connection.rollback.side_effect = rollback_error
        with self.assertRaises(SearchDatabaseError) as caught:
            self.search.get_task_by_id("task")
        self.assertIs(caught.exception.__cause__, rollback_error)
        self.assertIs(rollback_error.__context__.__cause__, query_error)
        self.assertEqual(self.events.mock_calls[-3:], [
            call.cursor_close(), call.connection.rollback(), call.connection.close(),
        ])
        self.connection.commit.assert_not_called()

    def test_explicitly_borrowed_connection_remains_caller_owned(self):
        self.cursor.fetchall.return_value = [record()]
        search = SearchService.from_connection(self.connection, user_id=7)
        self.assertEqual(len(search.interpret_and_search({"keyword": "5 điểm"}).results), 1)
        self.cursor.close.assert_called_once_with()
        self.connection.commit.assert_not_called()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_not_called()
        self.transaction.assert_not_called()
