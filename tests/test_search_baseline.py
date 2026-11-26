"""Regression checks for frozen labels, account views and baseline measurement."""

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from academic_search import search_records
from fixtures.search_semantic.run_keyword import ROOT, evaluate, load_inputs, visible_records


def test_frozen_labels_and_saved_keyword_measurement():
    accounts, owned, cases, manifest = load_inputs()
    assert manifest == {
        "corpus.json": "d3ad4f8a19046e4f6e66ee4322061b44f099a33203f0e159558d6d9276c05e97",
        "cases.json": "3012ee824e8576005b86934df0e2606d796ed00ef448286d01f40dc4f02cf0a7",
    }
    assert len(owned) == 14 and len(cases) == 31
    report = evaluate()
    assert report == json.loads((ROOT / "keyword_baseline.json").read_text(encoding="utf-8"))
    assert report["paraphrase_retrieval"] == {
        "tuning": {"hits_at_three": 1, "total": 3},
        "held-out": {"hits_at_three": 0, "total": 4},
    }
    assert report["unrelated_queries"] == {
        "tuning": {"false_hit_case_ids": [], "false_hits": 0, "total": 2},
        "held-out": {"false_hit_case_ids": [], "false_hits": 0, "total": 2},
        "all": {"false_hit_case_ids": [], "false_hits": 0, "total": 4},
    }
    assert not any(report["correctness_violations"].values())
    assert report["case_counts"] == {"paraphrase": 7, "exact_control": 3, "visibility": 8,
                                     "point_filter": 8, "structured_filter": 1, "unrelated": 4}


def test_guest_accounts_collisions_and_disabled_source_projection():
    accounts, owned, cases, _ = load_inputs()
    template = cases[0]
    guest = visible_records(owned, accounts, template)
    assert all(record.scope == "public" for record in guest)
    a = visible_records(owned, accounts, {**template, "viewer": "account_a"})
    b = visible_records(owned, accounts, {**template, "viewer": "account_b"})
    shared_id = "33333333-3333-4333-8333-333333333333"
    assert {(r.scope, r.title) for r in a if r.id == shared_id} == {
        ("public", "Quỹ tài trợ sinh viên xuất sắc"), ("personal", "Báo cáo thực hành cơ sở dữ liệu")}
    assert {(r.scope, r.title) for r in b if r.id == shared_id} == {
        ("public", "Quỹ tài trợ sinh viên xuất sắc"), ("personal", "Bài tập phân tích dữ liệu cá nhân")}
    disabled = visible_records(owned, accounts, {
        **template, "viewer": "account_a", "source_preferences": {"disabled_sources": ["Moodle"]}})
    assert disabled == guest
    with pytest.raises(ValueError, match="Unknown fictional viewer"):
        visible_records(owned, accounts, {**template, "viewer": "unknown"})


def test_zero_overlap_annotations_and_course_only_control_are_facts():
    accounts, owned, cases, _ = load_inputs()
    zero_cases = [case for case in cases if case["zero_literal_overlap"]]
    assert {case["split"] for case in zero_cases} == {"tuning", "held-out"}
    for case in zero_cases:
        for record in visible_records(owned, accounts, case):
            if list(record.key) in case["expected_relevant_keys"]:
                assert all(term not in (record.title + " " + record.description).casefold()
                           for term in case["query"].casefold().split())
    target = next(item.record for item in owned if item.record.course == "CSC10006")
    assert "CSC10006" not in target.title + target.description
    tuition = next(item.record for item in owned if item.record.title == "Thời điểm hoàn tất nghĩa vụ tài chính")
    assert "chương trình đào tạo" in tuition.description
    assert "tiền phòng" not in tuition.title + tuition.description


@pytest.mark.parametrize("name", ["corpus.json", "cases.json"])
def test_changed_frozen_input_fails_before_matcher_execution(tmp_path, name):
    for original in ("corpus.json", "cases.json", "frozen_inputs.json"):
        shutil.copyfile(ROOT / original, tmp_path / original)
    path = tmp_path / name
    path.write_bytes(path.read_bytes() + b" ")

    def forbidden(*args, **kwargs):
        raise AssertionError("Matcher ran against changed labels")

    with pytest.raises(ValueError, match="Frozen input changed"):
        evaluate(tmp_path, matcher=forbidden)


def test_crlf_checkout_preserves_frozen_text_fingerprints(tmp_path, monkeypatch):
    from fixtures.search_semantic import run_keyword

    for name in ("corpus.json", "cases.json", "frozen_inputs.json", "keyword_baseline.json"):
        (tmp_path / name).write_bytes((ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert evaluate(tmp_path) == evaluate()
    monkeypatch.setattr(run_keyword, "ROOT", tmp_path)
    monkeypatch.setattr(run_keyword, "evaluate", lambda: evaluate(tmp_path))
    monkeypatch.setattr(sys, "argv", ["run_keyword", "--check"])
    assert run_keyword.main() == 0


def test_evaluation_needs_no_database_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Evaluation accessed a database or network")

    monkeypatch.setattr("sqlite3.connect", forbidden)
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    assert not any(evaluate()["correctness_violations"].values())


def test_strict_boundary_violation_is_separate_from_a_paraphrase_miss():
    def broken(records, query, **kwargs):
        result = search_records(records, query, **kwargs)
        if query == "nhiều hơn 5 điểm":
            five = next(record for record in records if record.training_points == 5)
            return replace(result, hits=(five,), eligible_records=(*result.eligible_records, five))
        return result

    report = evaluate(matcher=broken)
    assert {item["case_id"] for item in report["correctness_violations"]["strict_boundary"]} == {"H-F01"}
    assert report["correctness_violations"]["point_filter"]
    assert report["paraphrase_retrieval"]["held-out"] == {"hits_at_three": 0, "total": 4}


def test_owner_leak_with_the_same_scoped_key_is_detected():
    _, owned, _, _ = load_inputs()
    foreign = next(item.record for item in owned if item.record.title == "Báo cáo thực hành cơ sở dữ liệu")

    def broken(records, query, **kwargs):
        result = search_records(records, query, **kwargs)
        if query == "khảo sát riêng" and any(record.title == "Bài tập phân tích dữ liệu cá nhân" for record in records):
            assert foreign.key in [record.key for record in records]
            return replace(result, hits=(foreign,))
        return result

    report = evaluate(matcher=broken)
    assert {item["case_id"] for item in report["correctness_violations"]["visibility"]} == {"H-V02"}


def test_unrelated_false_hits_are_reported_outside_the_paraphrase_denominator():
    def broken(records, query, **kwargs):
        result = search_records(records, query, **kwargs)
        return replace(result, hits=(records[0],)) if query == "động cơ tên lửa sao Hỏa" else result

    report = evaluate(matcher=broken)
    assert report["unrelated_queries"]["tuning"] == {
        "false_hit_case_ids": ["T-U01"], "false_hits": 1, "total": 2}
    assert report["unrelated_queries"]["all"] == {
        "false_hit_case_ids": ["T-U01"], "false_hits": 1, "total": 4}
    assert report["paraphrase_retrieval"]["tuning"] == {"hits_at_three": 1, "total": 3}
    assert not any(report["correctness_violations"].values())


def test_cli_two_processes_produce_identical_reports(tmp_path):
    command = [sys.executable, "-B", "-X", "utf8", "-m", "fixtures.search_semantic.run_keyword"]
    outputs = [tmp_path / "first.json", tmp_path / "second.json"]
    for output in outputs:
        result = subprocess.run([*command, "--output", str(output)], check=True, capture_output=True,
                                text=True, encoding="utf-8", cwd=ROOT.parents[1],
                                env={**os.environ, "PYTHON_DOTENV_DISABLED": "1"})
        assert "held-out: paraphrase top-three 0/4" in result.stdout
    assert outputs[0].read_bytes() == outputs[1].read_bytes() == (ROOT / "keyword_baseline.json").read_bytes().replace(b"\r\n", b"\n")
