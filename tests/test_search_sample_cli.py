"""Mocked terminal argument, dispatch, output and transaction ownership checks."""
import contextlib
import io
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from academic_search import (InterpretedSearch, SearchDatabaseError, SearchInterpretationError,
                             interpret_request)
from search_sample.__main__ import main, sample_service


class SearchSampleCliTests(unittest.TestCase):
    def run_cli(self, argv, *, rows=(), response=None, error=None):
        connection = MagicMock()
        driver = Mock()
        driver.connect.return_value = connection
        service = Mock()
        service.search_tasks.return_value = list(rows)
        service.interpret_and_search.return_value = response
        service.search_tasks.side_effect = error
        service.interpret_and_search.side_effect = error
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {"psycopg2": driver}), \
             patch("search_sample.__main__.sample_target") as target, \
             patch("search_sample.__main__.sample_service", return_value=service), \
             patch("search_sample.__main__.seed") as seed, patch("search_sample.__main__.reset") as reset, \
             patch("search_sample.support.read_fixture", side_effect=AssertionError("fixture load")), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = 0
            try:
                main(argv)
            except SystemExit as caught:
                code = caught.code
            seed.assert_not_called()
            reset.assert_not_called()
        return SimpleNamespace(code=code, out=out.getvalue(), err=err.getvalue(), connection=connection,
                               service=service, driver=driver, target=target)

    def test_required_commands_generate_requests_and_choose_only_one_method(self):
        examples = (
            (["--query", "tình nguyện"], {"keyword": "tình nguyện"}, False),
            (["--query", "sự kiện 5 điểm", "--interpret"], {"keyword": "sự kiện 5 điểm"}, True),
            (["--course", "CSC10004", "--type", "assignment"],
             {"filters": {"course": "CSC10004", "types": ["assignment"]}}, False),
            (["--query", "từ 5 điểm", "--interpret", "--limit", "10"],
             {"keyword": "từ 5 điểm", "limit": 10}, True),
        )
        for argv, expected, interpret in examples:
            with self.subTest(argv=argv):
                response = InterpretedSearch(interpret_request(expected), []) if interpret else None
                result = self.run_cli(["search", *argv], response=response)
                self.assertEqual(result.code, 0, result.err)
                chosen = result.service.interpret_and_search if interpret else result.service.search_tasks
                unused = result.service.search_tasks if interpret else result.service.interpret_and_search
                chosen.assert_called_once_with(expected)
                unused.assert_not_called()
                result.connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ")
                result.connection.rollback.assert_called_once_with()
                result.connection.close.assert_called_once_with()
                result.connection.commit.assert_not_called()

    def test_omitted_blank_and_literal_queries_preserve_request_values(self):
        for argv, request in (([], {}), (["--query", ""], {"keyword": ""}),
                              (["--query", " \t "], {"keyword": " \t "}),
                              (["--query", "5 điểm"], {"keyword": "5 điểm"}),
                              (["--course", "Tên môn / CSC10004"], {"filters": {"course": "Tên môn / CSC10004"}})):
            with self.subTest(argv=argv):
                result = self.run_cli(["search", *argv])
                self.assertEqual(result.code, 0)
                result.service.search_tasks.assert_called_once_with(request)
        for query in (None, ""):
            argv = ["search", "--interpret"] + ([] if query is None else ["--query", query])
            request = {} if query is None else {"keyword": query}
            result = self.run_cli(argv, response=InterpretedSearch(interpret_request(request), []))
            self.assertEqual(result.code, 0)
            result.service.interpret_and_search.assert_called_once_with(request)

    def test_validation_errors_fail_before_connection_or_configuration(self):
        for argv, message in ((["--type", "unknown"], "invalid types"),
                              (["--limit", "many"], "invalid int value"),
                              (["--limit", "0"], "limit must be"),
                              (["--limit", "101"], "limit must be"),
                              (["--course", ""], "invalid course")):
            with self.subTest(argv=argv):
                result = self.run_cli(["search", *argv])
                self.assertNotEqual(result.code, 0)
                self.assertIn(message, result.err)
                result.driver.connect.assert_not_called()
                result.target.assert_not_called()
        for limit in (1, 100):
            result = self.run_cli(["search", "--limit", str(limit)])
            self.assertEqual(result.code, 0)
            result.service.search_tasks.assert_called_once_with({"limit": limit})

    def test_search_options_are_scoped_to_search(self):
        for command in ("seed", "demo", "reset"):
            for option in (["--query", "text"], ["--interpret"], ["--course", "CSC10004"],
                           ["--type", "event"], ["--limit", "3"]):
                with self.subTest(command=command, option=option):
                    result = self.run_cli([command, *option])
                    self.assertNotEqual(result.code, 0)
                    result.driver.connect.assert_not_called()

    def test_output_preserves_titles_and_existing_interpretation_metadata(self):
        rows = [{"id": "sample-description-only", "title": "Tình nguyện mùa hè"}]
        result = self.run_cli(["search", "--query", "tình nguyện"], rows=rows)
        self.assertEqual(result.out, "sample-description-only | Tình nguyện mùa hè\n")
        metadata = interpret_request({"keyword": "tình nguyện 5 điểm"})
        result = self.run_cli(["search", "--query", metadata.original_query, "--interpret"],
                              response=InterpretedSearch(metadata, rows))
        self.assertEqual(result.code, 0)
        self.assertIn("Remaining keyword: tình nguyện", result.out)
        self.assertIn("Effective filters: " + str(metadata.effective_filters), result.out)
        self.assertIn("sample-description-only | Tình nguyện mùa hè", result.out)

    def test_no_matches_are_successful_in_both_modes(self):
        for argv, response in ((["search"], None), (["search", "--interpret"],
                               InterpretedSearch(interpret_request({}), []))):
            result = self.run_cli(argv, response=response)
            self.assertEqual(result.code, 0)
            self.assertIn("No tasks match.", result.out)
            self.assertEqual(result.err, "")

    def test_errors_are_nonzero_with_rollback_and_close(self):
        for error, interpreted in ((SearchInterpretationError("Conflicting task types"), True),
                                   (SearchDatabaseError("PostgreSQL task search failed"), False),
                                   (SearchDatabaseError("PostgreSQL task search failed"), True)):
            result = self.run_cli(["search"] + (["--interpret"] if interpreted else []), error=error)
            self.assertEqual(result.code, 1)
            self.assertIn(str(error), result.err)
            self.assertNotIn("No tasks match", result.out)
            result.connection.rollback.assert_called_once_with()
            result.connection.close.assert_called_once_with()
            result.connection.commit.assert_not_called()

    def test_shared_owner_lookup_is_guarded_and_uses_database_id_without_fixtures(self):
        connection = MagicMock()
        target = Mock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (47,)
        with patch("search_sample.__main__.validate_transaction") as validate, \
             patch("search_sample.__main__.owned_schema", return_value=True), \
             patch("search_sample.__main__.SearchService.from_connection") as factory, \
             patch("search_sample.support.read_fixture", side_effect=AssertionError("fixture load")):
            self.assertIs(sample_service(connection, target), factory.return_value)
            validate.assert_called_once_with(connection, target)
            factory.assert_called_once_with(connection, user_id=47)
        self.assertEqual(cursor.execute.call_args_list[0].args,
                         ("SET LOCAL search_path TO search_sample, pg_catalog",))
        self.assertEqual(cursor.execute.call_args_list[1].args,
                         ("SELECT id FROM users WHERE username = %s", ("sample_owner",)))
        connection.commit.assert_not_called()
        connection.rollback.assert_not_called()
        connection.close.assert_not_called()

    def test_missing_initialization_and_owner_fail_clearly_and_close(self):
        for initialized in (False, True):
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = None
            driver = Mock()
            driver.connect.return_value = connection
            err = io.StringIO()
            with patch.dict(sys.modules, {"psycopg2": driver}), \
                 patch("search_sample.__main__.sample_target"), \
                 patch("search_sample.__main__.validate_transaction"), \
                 patch("search_sample.__main__.owned_schema", return_value=initialized), \
                 patch("search_sample.__main__.seed") as seed, \
                 patch("search_sample.__main__.reset") as reset, \
                 contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                main(["search"])
            self.assertEqual(caught.exception.code, 1)
            self.assertIn("owner is absent" if initialized else "not initialized", err.getvalue())
            self.assertIn("python -m search_sample seed", err.getvalue())
            seed.assert_not_called()
            reset.assert_not_called()
            connection.commit.assert_not_called()
            connection.rollback.assert_called_once_with()
            connection.close.assert_called_once_with()

    def test_existing_commands_and_reset_flag_positions_keep_ownership(self):
        for argv, operation in ((["seed"], "seed"), (["demo"], "demo"),
                                (["reset", "--confirm-reset"], "reset"),
                                (["--confirm-reset", "reset"], "reset")):
            connection, driver = MagicMock(), Mock()
            driver.connect.return_value = connection
            with patch.dict(sys.modules, {"psycopg2": driver}), \
                 patch("search_sample.__main__.sample_target") as target, \
                 patch("search_sample.__main__." + operation, return_value=45) as execute, \
                 contextlib.redirect_stdout(io.StringIO()):
                main(argv)
            execute.assert_called_once_with(connection, target.return_value)
            connection.close.assert_called_once_with()
            if operation == "demo":
                connection.rollback.assert_called_once_with()
                connection.commit.assert_not_called()
            else:
                connection.commit.assert_called_once_with()
                connection.rollback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
