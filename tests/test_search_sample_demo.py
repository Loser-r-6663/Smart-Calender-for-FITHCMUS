"""Offline orchestration checks using mocked service results, not live retrieval."""
import contextlib
from copy import deepcopy
import io
import unittest
from unittest.mock import Mock, patch

from academic_search import (Interpretation, InterpretedSearch, SearchDatabaseError,
                             SearchInterpretationError, SearchValidationError)
from search_sample.__main__ import SampleSetupError, demo
from search_sample.data import sample_tasks
from search_sample.examples import CONFLICT_REQUEST, EXAMPLES, INTERPRETED_EXAMPLES
import test_search_sample_cli as cli_helpers


class ScriptedDemoTests(unittest.TestCase):
    def service(self):
        tasks = {task["id"]: task for task in sample_tasks()}
        service = Mock()
        service.get_task_by_id.side_effect = [tasks["asg-csc10004-lab"], None]
        service.search_tasks.side_effect = [[tasks[task_id] for task_id in expected]
                                            for _, _, expected in EXAMPLES]
        interpreted = []
        for _, request, expected, remaining, inferred, effective in INTERPRETED_EXAMPLES:
            metadata = Interpretation(request["keyword"], remaining, deepcopy(inferred), deepcopy(effective))
            interpreted.append(InterpretedSearch(metadata, [tasks[task_id] for task_id in expected]))
        service.interpret_and_search.side_effect = [*interpreted, SearchInterpretationError("Conflicting training-point constraints")]
        return service, interpreted

    def execute(self, service):
        output = io.StringIO()
        with patch("search_sample.__main__.sample_service", return_value=service), \
             patch("search_sample.__main__.seed") as seed, patch("search_sample.__main__.reset") as reset, \
             patch("search_sample.support.read_fixture", side_effect=AssertionError("fixture loading during demo")), \
             contextlib.redirect_stdout(output):
            try:
                demo(Mock(), Mock())
            finally:
                seed.assert_not_called()
                reset.assert_not_called()
                self.output = output.getvalue()

    def test_complete_demo_dispatches_checks_and_formats_every_case(self):
        service, _ = self.service()
        before = deepcopy((EXAMPLES, INTERPRETED_EXAMPLES, CONFLICT_REQUEST))
        self.execute(service)
        self.assertEqual([call.args[0] for call in service.get_task_by_id.call_args_list],
                         ["asg-csc10004-lab", "sample-missing"])
        self.assertEqual([call.args[0] for call in service.search_tasks.call_args_list],
                         [request for _, request, _ in EXAMPLES])
        self.assertEqual([call.args[0] for call in service.interpret_and_search.call_args_list],
                         [request for _, request, *_ in INTERPRETED_EXAMPLES] + [CONFLICT_REQUEST])
        for text in ("Original query: tình nguyện 5 điểm", "Remaining keyword: tình nguyện", "Effective filters:",
                     "Training points: exactly 5", "Training points: at least 5", "Type: event", "No matching tasks",
                     "Task ID: sample-description-only", "Expected validation error:", "Demonstration deadline window:"):
            self.assertIn(text, self.output)
        self.assertTrue(self.output.rstrip().endswith("All demo expectations passed against PostgreSQL."))
        self.assertNotIn("{'", self.output)
        self.assertNotIn("SELECT ", self.output)
        self.assertEqual((EXAMPLES, INTERPRETED_EXAMPLES, CONFLICT_REQUEST), before)

    def test_result_mismatches_fail_without_final_success(self):
        for mismatch in ("lookup", "structured", "interpreted"):
            service, responses = self.service()
            if mismatch == "lookup":
                service.get_task_by_id.side_effect = [None]
            elif mismatch == "structured":
                service.search_tasks.side_effect = [[]]
            else:
                responses[0].results.clear()
                service.interpret_and_search.side_effect = responses
            with self.subTest(mismatch=mismatch), self.assertRaises(SampleSetupError):
                self.execute(service)
            self.assertNotIn("All demo expectations passed", self.output)

    def test_every_metadata_field_is_checked(self):
        for field, wrong in (("original_query", "wrong"), ("remaining_keyword", "wrong"),
                             ("inferred_filters", {}), ("effective_filters", {})):
            service, responses = self.service()
            values = vars(responses[0].interpretation).copy()
            values[field] = wrong
            responses[0] = InterpretedSearch(Interpretation(**values), responses[0].results)
            service.interpret_and_search.side_effect = responses
            with self.subTest(field=field), self.assertRaises(SampleSetupError):
                self.execute(service)
            self.assertNotIn("All demo expectations passed", self.output)

    def test_expected_error_must_have_the_correct_type_and_meaning(self):
        for final in (None, SearchInterpretationError("Unsupported expression"), SearchValidationError("Conflicting")):
            service, responses = self.service()
            service.interpret_and_search.side_effect = [*responses, final]
            with self.subTest(final=final), self.assertRaises((SampleSetupError, SearchValidationError)):
                self.execute(service)
            self.assertNotIn("All demo expectations passed", self.output)

    def test_unexpected_query_failure_does_not_print_success(self):
        service, _ = self.service()
        service.search_tasks.side_effect = SearchDatabaseError("PostgreSQL task search failed")
        with self.assertRaises(SearchDatabaseError):
            self.execute(service)
        self.assertNotIn("All demo expectations passed", self.output)

    def test_command_owner_fails_mismatches_and_finishes_successful_reads(self):
        for failure in (None, "rows", "missing conflict"):
            service, responses = self.service()
            if failure == "rows":
                service.search_tasks.side_effect = [[]]
            elif failure == "missing conflict":
                service.interpret_and_search.side_effect = [*responses, None]
            result = cli_helpers.SearchSampleCliTests().run_cli(["demo"], use_service=service)
            self.assertEqual(result.code, 0 if failure is None else 1)
            result.connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ")
            result.connection.rollback.assert_called_once_with()
            result.connection.close.assert_called_once_with()
            result.connection.commit.assert_not_called()
            if failure is None:
                self.assertIn("All demo expectations passed", result.out)
            else:
                self.assertEqual(result.out, "")
                self.assertNotIn("All demo expectations passed", result.err)


if __name__ == "__main__":
    unittest.main()
