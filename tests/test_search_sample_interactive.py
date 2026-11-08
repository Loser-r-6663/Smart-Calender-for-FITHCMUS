"""Offline prompt and dispatch tests; database execution is mocked."""
import unittest
from unittest.mock import MagicMock, patch

from academic_search import InterpretedSearch, SearchDatabaseError, SearchService, interpret_request
from test_postgres_search import record
import test_search_sample_cli as cli_helpers


class InteractiveSearchTests(unittest.TestCase):
    def run_cli(self, argv, inputs, **options):
        with patch("builtins.input", side_effect=inputs):
            return cli_helpers.SearchSampleCliTests().run_cli(argv, **options)

    def test_multiple_literal_queries_and_blank_input_preserve_existing_requests(self):
        result = self.run_cli(["interactive"], ["tình nguyện", "5 điểm", "", ":quit"])
        self.assertEqual(result.code, 0, result.err)
        self.assertEqual([call.args[0] for call in result.service.search_tasks.call_args_list],
                         [{"keyword": "tình nguyện"}, {"keyword": "5 điểm"}, {"keyword": ""}])
        result.service.interpret_and_search.assert_not_called()
        self.assertIn("Original query: tình nguyện", result.out)
        self.assertIn("No keyword constraint.", result.out)
        self.assertIn("No matching tasks", result.out)
        self.assertEqual(result.connection.rollback.call_count, 4)
        result.connection.commit.assert_not_called()
        result.connection.close.assert_called_once_with()
        result.connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ")

    def test_interpreted_prompt_uses_existing_metadata(self):
        metadata = interpret_request({"keyword": "tình nguyện 5 điểm"})
        result = self.run_cli(["interactive", "--interpret"], [metadata.original_query, ":quit"],
                              response=InterpretedSearch(metadata, []))
        self.assertEqual(result.code, 0, result.err)
        result.service.interpret_and_search.assert_called_once_with({"keyword": metadata.original_query})
        result.service.search_tasks.assert_not_called()
        self.assertIn("Remaining keyword: tình nguyện", result.out)
        self.assertIn("Training points: exactly 5", result.out)

    def test_invalid_expression_can_be_corrected_without_opening_another_connection(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [record(training_points=5)]
        result = self.run_cli(["interactive", "--interpret"], ["hơn 5 điểm", "5 điểm", ":quit"],
                              connection=connection, use_service=SearchService.from_connection(connection, user_id=47))
        self.assertEqual(result.code, 0)
        self.assertIn("Interpretation error", result.err)
        self.assertIn("Training points: exactly 5", result.out)
        self.assertIn("Task ID: Task_é 1", result.out)
        connection.cursor.assert_called_once_with()
        self.assertTrue(cursor.execute.call_args.args[0].startswith("SELECT "))
        self.assertEqual(connection.rollback.call_count, 3)
        result.driver.connect.assert_called_once()
        connection.close.assert_called_once_with()

    def test_end_of_input_and_interrupt_finish_the_session_cleanly(self):
        for end in (EOFError(), KeyboardInterrupt()):
            with self.subTest(end=type(end).__name__):
                result = self.run_cli(["interactive"], [end])
                self.assertEqual(result.code, 0)
                result.service.search_tasks.assert_not_called()
                result.connection.rollback.assert_called_once_with()
                result.connection.close.assert_called_once_with()
                self.assertIn("Search session ended.", result.out)

    def test_database_failure_ends_session_and_cleans_up(self):
        result = self.run_cli(["interactive"], ["tình nguyện"], error=SearchDatabaseError("private detail"))
        self.assertEqual(result.code, 1)
        self.assertIn("Database query failure", result.err)
        self.assertNotIn("private detail", result.err)
        self.assertNotIn("No matching tasks", result.out)
        result.connection.rollback.assert_called_once_with()
        result.connection.close.assert_called_once_with()
        result.connection.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
