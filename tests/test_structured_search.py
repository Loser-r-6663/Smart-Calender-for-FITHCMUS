"""Exercise the SQL service against curated fixtures and explicit edge cases."""
import copy
import json
import sqlite3
import unittest
from pathlib import Path

from academic_search import SearchService, SearchValidationError
from academic_search.fixture_adapter import create_demo_database, store_task

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "search"
CLOCK = "2026-10-30T12:00:00+07:00"
DAY = ["2026-10-30T00:00:00+07:00", "2026-10-31T00:00:00+07:00"]


def read(name):
    return json.loads((ROOT / f"{name}.json").read_text(encoding="utf-8"))


class StructuredSearchTests(unittest.TestCase):
    def setUp(self):
        self.tasks = read("tasks")
        self.connection = create_demo_database(self.tasks)
        self.addCleanup(self.connection.close)
        self.service = SearchService(self.connection)

    def ids(self, filters=None, **options):
        request = {"filters": filters or {}, "limit": 100, **options}
        return [task["id"] for task in self.service.search_tasks(request)]

    def store_variant(self, original="evt-green", id="test-edge", **changes):
        task = copy.deepcopy(next(t for t in self.tasks if t["id"] == original))
        task.update(id=id, **changes)
        store_task(self.connection, task)
        return task

    def test_existing_structured_expectations(self):
        scenarios = {s["id"]: s for s in read("scenarios")}
        exercised = []
        for query in read("queries"):
            if query["mode"] != "structured":
                continue
            with self.subTest(query=query["id"]):
                connection = create_demo_database(self.tasks)
                try:
                    if query["state"] != "base":
                        scenario = scenarios[query["state"]]
                        task = next(copy.deepcopy(t) for t in self.tasks if t["id"] == scenario["task_id"])
                        task.update(scenario["changes"])
                        store_task(connection, task)
                    request = copy.deepcopy(query["request"])
                    request["limit"] = 100
                    results = SearchService(connection).search_tasks(request)
                    self.assertEqual({t["id"] for t in results}, set(query["expected_ids"]))
                    self.assertFalse({t["id"] for t in results}.intersection(query["excluded_ids"]))
                    exercised.append(query["id"])
                finally:
                    connection.close()
        self.assertEqual(exercised, ["q01", "q05", "q09", "q10", "q19", "q20", "q23", "q24", "q27"])

    def test_exact_id_found_not_found_and_all_statuses(self):
        self.assertEqual(self.service.get_task_by_id("asg-csc10004-lab"), self.tasks[0])
        self.assertIsNone(self.service.get_task_by_id("does-not-exist"))
        self.assertEqual(self.service.get_task_by_id("evt-cancelled")["status"], "cancelled")

    def test_course_isolation_both_directions(self):
        self.assertEqual(set(self.ids({"course_code": "CSC10004"})),
                         {"asg-csc10004-lab", "asg-csc10004-project", "asg-overdue", "class-csc10004"})
        self.assertEqual(set(self.ids({"course_code": "CSC10005"})),
                         {"asg-csc10005-lab", "asg-csc10005-project", "exam-csc10005"})

    def test_type_or_and_source_or(self):
        self.assertEqual(set(self.ids({"types": ["class", "exam"], "source_platforms": ["portal", "custom"]})),
                         {"class-csc10004", "exam-csc10005"})
        self.assertEqual(self.ids({"source_platform": "custom"}), ["personal-study"])
        self.assertEqual(set(self.ids({"course_code": "CSC10004", "source_platform": "moodle"})),
                         {"asg-csc10004-lab", "asg-csc10004-project", "asg-overdue"})

    def test_multiple_sources_do_not_duplicate_tasks(self):
        ids = self.ids({"source_platforms": ["moodle", "portal", "facebook", "custom"]})
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 34)
        self.assertEqual(self.ids({"source_platform": "moodle", "source_platforms": ["custom"]}), [])

    def test_default_and_explicit_statuses(self):
        self.assertEqual(set(self.ids({"statuses": ["done"]})), {"asg-done", "fee-done", "evt-done"})
        self.assertEqual(set(self.ids({"statuses": ["cancelled"]})), {"asg-cancelled", "evt-cancelled"})
        self.assertEqual(set(self.ids({"statuses": ["done", "archived"], "types": ["assignment"]})),
                         {"asg-done", "asg-archived"})
        self.assertEqual({t["status"] for t in self.service.search_tasks({"limit": 100})}, {"active"})
        self.assertIn("asg-overdue", self.ids())

    def test_points_inclusive_bounds_and_unknown(self):
        self.store_variant(id="test-unknown", training_points=None, drl_category=None)
        self.store_variant(id="test-zero", training_points=0, drl_category=None)
        self.store_variant(id="test-hundred", training_points=100)
        self.assertEqual(set(self.ids({"min_training_points": 7, "max_training_points": 10})), {"evt-green", "evt-beach"})
        self.assertEqual(self.ids({"min_training_points": 100, "max_training_points": 100}), ["test-hundred"])
        self.assertIn("test-unknown", self.ids())
        self.assertIsNone(self.service.get_task_by_id("test-unknown")["training_points"])
        self.assertNotIn("test-unknown", self.ids({"min_training_points": 0}))
        self.assertNotIn("test-unknown", self.ids({"max_training_points": 0}))
        self.assertIn("test-zero", self.ids({"min_training_points": 0, "max_training_points": 0}))

    def test_due_registration_event_and_updated_are_separate(self):
        self.assertEqual(set(self.ids({"deadline_within": DAY})), {"asg-csc10004-lab", "asg-csc10005-lab", "asg-update"})
        self.assertEqual(set(self.ids({"registration_end_within": DAY})), {"evt-reg-before", "evt-reg-exact", "evt-reg-after"})
        self.assertEqual(set(self.ids({"types": ["event"], "start_time_within": DAY})), {"evt-today"})
        self.assertEqual(self.ids({"updated_at_within": DAY}), [])
        self.store_variant(id="test-updated", updated_at=CLOCK)
        self.assertEqual(self.ids({"updated_at_within": DAY}), ["test-updated"])
        self.assertEqual(set(self.ids({"updated_at_within": [CLOCK, "2026-10-30T12:00:00.000001+07:00"]})), {"test-updated"})
        self.assertEqual(self.ids({"updated_at_within": [DAY[0], CLOCK]}), [])

    def test_registration_closing_before_exact_after(self):
        base = {"types": ["event"], "registration_end_within": DAY}
        cases = [("2026-10-30T10:59:59+07:00", {"evt-reg-before", "evt-reg-exact", "evt-reg-after"}),
                 ("2026-10-30T11:00:00+07:00", {"evt-reg-before", "evt-reg-exact", "evt-reg-after"}),
                 ("2026-10-30T11:00:01+07:00", {"evt-reg-exact", "evt-reg-after"}),
                 (CLOCK, {"evt-reg-exact", "evt-reg-after"}),
                 ("2026-10-30T12:00:01+07:00", {"evt-reg-after"}),
                 ("2026-10-30T13:00:01+07:00", set())]
        for at, expected in cases:
            with self.subTest(at=at):
                self.assertEqual(set(self.ids({**base, "registration_open_at": at})), expected)

    def test_registration_start_inclusive_and_missing_unknown(self):
        self.store_variant(id="test-opens", registration_start=CLOCK)
        ids = self.ids({"registration_open_at": CLOCK})
        self.assertIn("test-opens", ids)
        for id in ("evt-missing-start", "evt-missing-end", "evt-missing-both", "evt-future-reg"):
            self.assertNotIn(id, ids)

    def test_event_overlap_touching_boundaries_and_starts_within(self):
        self.assertEqual(set(self.ids({"types": ["event"], "event_overlaps": DAY})), {"evt-overlap", "evt-today"})
        self.assertEqual(self.ids({"types": ["event"], "start_time_within": DAY}), ["evt-today"])

    def test_missing_event_endpoints(self):
        self.store_variant(id="test-no-start", start_time=None, end_time=DAY[1])
        self.store_variant(id="test-no-end", start_time=CLOCK, end_time=None)
        self.store_variant(id="test-no-dates", start_time=None, end_time=None)
        ids = self.ids({"event_overlaps": DAY})
        for id in ("test-no-start", "test-no-end", "test-no-dates"):
            self.assertNotIn(id, ids)
        self.assertIn("test-no-end", self.ids({"start_time_within": DAY}))

    def test_equal_or_reversed_stored_event_interval_rejected(self):
        for end in (CLOCK, DAY[0]):
            with self.subTest(end=end), self.assertRaises(SearchValidationError):
                self.store_variant(start_time=CLOCK, end_time=end)

    def test_equivalent_offsets_normalized_before_sql_comparison(self):
        self.store_variant(id="test-utc", start_time="2026-10-30T05:00:00Z", end_time="2026-10-30T06:00:00Z")
        self.assertIn("test-utc", self.ids({"start_time_within": [CLOCK, "2026-10-30T13:00:00+07:00"]}))
        self.assertEqual(self.ids({"registration_open_at": "2026-10-30T05:00:00Z"}), self.ids({"registration_open_at": CLOCK}))
        self.assertEqual(self.service.get_task_by_id("test-utc")["start_time"], "2026-10-30T05:00:00Z")

    def test_microsecond_boundaries(self):
        self.store_variant(id="test-micro", start_time="2026-10-30T12:00:00.000001+07:00", end_time="2026-10-30T12:00:00.000002+07:00")
        self.assertNotIn("test-micro", self.ids({"start_time_within": [CLOCK, "2026-10-30T12:00:00.000001+07:00"]}))
        self.assertIn("test-micro", self.ids({"event_overlaps": [CLOCK, "2026-10-30T12:00:00.000002+07:00"]}))

    def test_literal_location_prefix_and_audience(self):
        self.assertEqual(set(self.ids({"target_audience": "K26", "location_prefix": "CS1"})), {"evt-speaking", "evt-debate"})
        self.assertEqual(self.ids({"location_prefix": "cs1"}), [])
        self.store_variant(id="test-literal", location="CS2_%' room")
        self.assertEqual(self.ids({"location_prefix": "CS2_%'"}), ["test-literal"])

    def test_empty_results_have_no_fallback(self):
        self.assertEqual(self.ids({"course_code": "CSC99999"}), [])
        self.assertEqual(self.ids({"types": ["tuition"], "course_code": "CSC10004"}), [])

    def test_default_sort_due_undated_last_and_stable_ties(self):
        tasks = self.service.search_tasks({"limit": 100})
        dated = [task for task in tasks if task["deadline"] is not None]
        undated = [task for task in tasks if task["deadline"] is None]
        self.assertEqual(tasks, dated + undated)
        self.assertEqual([t["id"] for t in tasks[:5]], ["asg-overdue", "asg-csc10004-lab", "asg-csc10005-lab", "asg-update", "asg-network"])
        self.assertEqual([t["id"] for t in undated], sorted(t["id"] for t in undated))
        self.assertEqual([t["id"] for t in dated[-2:]], ["fee-hk1", "fee-installment"])
        desc = self.service.search_tasks({"sort": "deadline", "direction": "desc", "limit": 100})
        self.assertEqual(desc[0]["id"], "fee-installment")
        self.assertEqual(desc[-len(undated):], undated)

    def test_all_sorts_have_stable_ties(self):
        for sort, first, last in (("id", "asg-csc10004-lab", "personal-study"),
                                  ("updated_at", "asg-csc10004-lab", "personal-study")):
            with self.subTest(sort=sort):
                ids = self.ids(sort=sort)
                self.assertEqual((ids[0], ids[-1]), (first, last))
        self.assertEqual(self.ids(sort="id", direction="desc"), sorted(self.ids(), reverse=True))
        self.assertEqual(self.ids({"types": ["event"]}, sort="start_time")[:3],
                         ["evt-end-midnight", "evt-overlap", "evt-today"])
        self.assertEqual(self.ids({"min_training_points": 7}, sort="training_points", direction="desc"), ["evt-beach", "evt-green"])
        self.store_variant(id="test-unknown", training_points=None)
        self.assertEqual(self.ids(sort="training_points", direction="desc")[-1], "test-unknown")
        ties = self.ids({"min_training_points": 5, "max_training_points": 5}, sort="training_points", direction="desc")
        self.assertEqual(ties, sorted(ties))

    def test_bounded_pagination_after_filters_and_sort(self):
        all_ids = self.ids(sort="id")
        pages = [self.ids(sort="id", limit=7, offset=offset) for offset in range(0, len(all_ids), 7)]
        self.assertEqual([id for page in pages for id in page], all_ids)
        self.assertEqual(len(self.service.search_tasks({})), 20)
        self.assertEqual(self.ids(offset=100_000), [])
        self.assertEqual(self.ids({"course_code": "CSC10004"}, sort="id", offset=1, limit=2),
                         ["asg-csc10004-project", "asg-overdue"])

    def test_invalid_requests(self):
        requests = [None, [], {"keyword": "tuition"}, {"semantic_text": "activities"},
                    {"filters": None}, {"filters": {"typo": 1}},
                    {"filters": {"types": []}}, {"filters": {"statuses": []}},
                    {"filters": {"source_platforms": []}}, {"filters": {"types": ["deadline"]}},
                    {"filters": {"types": ["event", "event"]}}, {"filters": {"types": [["event"]]}},
                    {"filters": {"statuses": ["completed"]}}, {"filters": {"source_platform": "web"}},
                    {"filters": {"source_platforms": ["bad"]}}, {"filters": {"course_code": "csc10004"}},
                    {"filters": {"min_training_points": -1}}, {"filters": {"max_training_points": 101}},
                    {"filters": {"min_training_points": True}}, {"filters": {"max_training_points": 3.5}},
                    {"filters": {"min_training_points": 8, "max_training_points": 7}},
                    {"sort": "title"}, {"sort": []}, {"direction": "ASC"},
                    {"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": "10"},
                    {"offset": -1}, {"offset": 100001}, {"offset": False}]
        for request in requests:
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                self.service.search_tasks(request)

    def test_invalid_dates_ranges_and_ids(self):
        for value in ("2026-10-30", "2026-10-30T12:00:00", "2026-02-30T12:00:00+07:00", "2026-10-30T12:00:00+00:60", "bad", 12):
            with self.subTest(value=value), self.assertRaises(SearchValidationError):
                self.ids({"registration_open_at": value})
        for key in ("deadline_within", "registration_end_within", "start_time_within", "event_overlaps", "updated_at_within"):
            for bounds in ([CLOCK, CLOCK], list(reversed(DAY)), [], [CLOCK], "today"):
                with self.subTest(key=key, bounds=bounds), self.assertRaises(SearchValidationError):
                    self.ids({key: bounds})
        for id in (None, "", "A", "a" * 41, "id' OR 1=1 --"):
            with self.subTest(id=id), self.assertRaises(SearchValidationError):
                self.service.get_task_by_id(id)

    def test_sql_metacharacters_remain_data(self):
        text = "' OR 1=1 --"
        self.assertEqual(self.ids({"target_audience": text}), [])
        self.assertEqual(self.ids({"location_prefix": text}), [])
        self.store_variant(id="test-quotes", target_audience=text)
        self.assertEqual(self.ids({"target_audience": text}), ["test-quotes"])
        for request in ({"sort": "id; DROP TABLE search_tasks; --"}, {"direction": "asc; DELETE FROM search_tasks"},
                        {"filters": {"course_code": text}}, {"filters": {"source_platform": text}}):
            with self.subTest(request=request), self.assertRaises(SearchValidationError):
                self.service.search_tasks(request)
        self.assertIsNotNone(self.service.get_task_by_id("asg-csc10004-lab"))

    def test_existing_update_cancel_delete_scenarios_visible(self):
        for scenario in read("scenarios"):
            with self.subTest(scenario=scenario["id"]):
                id = scenario["task_id"]
                task = self.service.get_task_by_id(id)
                self.assertIsNotNone(task)
                if scenario["operation"] == "delete":
                    self.connection.execute("DELETE FROM search_tasks WHERE id = ?", (id,))
                    self.assertIsNone(self.service.get_task_by_id(id))
                    self.assertNotIn(id, self.ids({"statuses": ["active", "done", "archived", "cancelled"]}))
                else:
                    task.update(scenario["changes"])
                    store_task(self.connection, task)
                    self.assertEqual(self.service.get_task_by_id(id), task)
                    if scenario["id"] == "edited":
                        self.assertNotIn(id, self.ids({"deadline_within": DAY}))
                        self.assertIn(id, self.ids({"deadline_within": ["2026-11-02T00:00:00+07:00", "2026-11-03T00:00:00+07:00"]}))
                        self.assertIn(id, self.ids({"updated_at_within": DAY}))
                    else:
                        self.assertNotIn(id, self.ids())
                        self.assertIn(id, self.ids({"statuses": ["cancelled"]}))

    def test_database_failures_are_not_empty_results(self):
        self.connection.execute("DROP TABLE search_tasks")
        with self.assertRaises(sqlite3.Error):
            self.service.search_tasks({})
        with self.assertRaises(sqlite3.Error):
            self.service.get_task_by_id("asg-csc10004-lab")

    def test_service_does_not_commit_caller_transaction(self):
        self.connection.execute("DELETE FROM search_tasks WHERE id = ?", ("evt-delete",))
        self.assertIsNone(self.service.get_task_by_id("evt-delete"))
        self.service.search_tasks({})
        self.connection.rollback()
        self.assertIsNotNone(self.service.get_task_by_id("evt-delete"))


if __name__ == "__main__":
    unittest.main()
