"""Reject dataset corruption and protect the important temporal distinctions."""
import copy
import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / "fixtures" / "search" / "validate.py"
SPEC = importlib.util.spec_from_file_location("fixture_validation", PATH)
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)


class SearchFixtureTests(unittest.TestCase):
    def setUp(self):
        self.tasks, self.queries, self.scenarios = copy.deepcopy(v.load())

    def validate(self):
        return v.validate(self.tasks, self.queries, self.scenarios)

    def test_curated_dataset(self):
        self.validate()

    def test_duplicate_task_id_rejected(self):
        self.tasks[1]["id"] = self.tasks[0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            self.validate()

    def test_duplicate_query_id_rejected(self):
        self.queries[1]["id"] = self.queries[0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            self.validate()

    def test_duplicate_scenario_id_rejected(self):
        self.scenarios[1]["id"] = self.scenarios[0]["id"]
        with self.assertRaisesRegex(ValueError, "Duplicate ID"):
            self.validate()

    def test_unknown_expected_id_rejected(self):
        self.queries[0]["expected_ids"].append("missing-task")
        with self.assertRaisesRegex(ValueError, "Unknown/duplicate expected"):
            self.validate()

    def test_cross_course_leak_rejected(self):
        self.queries[0]["expected_ids"].append("asg-csc10005-lab")
        with self.assertRaisesRegex(ValueError, "Expectation mismatch q01"):
            self.validate()

    def test_missing_expected_match_rejected(self):
        self.queries[0]["expected_ids"].pop()
        with self.assertRaisesRegex(ValueError, "Expectation mismatch q01"):
            self.validate()

    def test_naive_timestamp_rejected(self):
        self.tasks[0]["deadline"] = "2026-10-30T12:00:00"
        with self.assertRaisesRegex(ValueError, "explicit UTC"):
            self.validate()

    def test_missing_deadline_rejected(self):
        self.tasks[0]["deadline"] = None
        with self.assertRaisesRegex(ValueError, "own deadline"):
            self.validate()

    def test_unknown_filter_rejected(self):
        self.queries[0]["request"]["filters"]["course_cod"] = "CSC10004"
        with self.assertRaisesRegex(ValueError, "Unknown filter"):
            self.validate()

    def test_semantic_labels_obey_status(self):
        self.queries[20]["relevance_labels"]["evt-cancelled"] = 2
        with self.assertRaisesRegex(ValueError, "hard filter"):
            self.validate()

    def test_update_cannot_change_identity(self):
        self.scenarios[0]["changes"]["id"] = "new-id"
        with self.assertRaisesRegex(ValueError, "preserve identity"):
            self.validate()

    def test_stale_deadline_after_edit_rejected(self):
        self.scenarios[0]["changes"]["deadline"] = "2026-10-30T23:59:00+07:00"
        with self.assertRaisesRegex(ValueError, "Expectation mismatch q28"):
            self.validate()

    def test_deleted_id_cannot_be_expected(self):
        self.queries[-1]["expected_ids"] = ["evt-delete"]
        with self.assertRaisesRegex(ValueError, "Unknown/duplicate expected"):
            self.validate()

    def test_cancelled_id_cannot_survive_default_results(self):
        self.queries[29]["expected_ids"] = ["evt-cancel"]
        with self.assertRaisesRegex(ValueError, "Expectation mismatch q30"):
            self.validate()

    def test_registration_inclusive_and_missing_unknown(self):
        tasks = {t["id"]: t for t in self.tasks}
        filters = {"registration_open_at": v.CLOCK}
        for id, expected in (("evt-reg-before", False), ("evt-reg-exact", True), ("evt-reg-after", True),
                             ("evt-missing-start", False), ("evt-missing-end", False),
                             ("evt-missing-both", False), ("evt-future-reg", False)):
            with self.subTest(id=id):
                self.assertEqual(v.eligible(tasks[id], filters), expected)

    def test_half_open_day_overlap(self):
        tasks = {t["id"]: t for t in self.tasks}
        day = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]
        for id, expected in (("evt-overlap", True), ("evt-today", True),
                             ("evt-end-midnight", False), ("evt-next-midnight", False)):
            with self.subTest(id=id):
                self.assertEqual(v.eligible(tasks[id], {"event_overlaps": day}), expected)
        self.assertFalse(v.eligible(tasks["evt-overlap"], {"start_time_within": day}))

    def test_vietnamese_normalization_and_whole_tokens(self):
        self.assertEqual(v.normalize("HỌC PHÍ Đăng ký"), ["hoc", "phi", "dang", "ky"])
        self.assertEqual(v.normalize("học phí"), v.normalize("ho\u0323c phi\u0301"))
        self.assertFalse(v.keyword_matches(self.tasks[0], "CSC1000"))


if __name__ == "__main__":
    unittest.main()
