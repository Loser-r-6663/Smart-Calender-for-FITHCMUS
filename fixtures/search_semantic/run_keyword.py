"""Measure the keyword matcher against frozen, fictional, account-scoped cases."""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import operator
from pathlib import Path

from academic_search import SearchRecord, map_task, search_records
import academic_search.matcher as keyword_matcher
from DataProcessor.Standardization.ExtractedTask import ExtractedTask

ROOT = Path(__file__).resolve().parent
KINDS = {"paraphrase", "exact_control", "visibility", "point_filter", "structured_filter", "unrelated"}
POINT_RULES = {"eq": operator.eq, "ge": operator.ge, "gt": operator.gt,
               "le": operator.le, "lt": operator.lt}


@dataclass(frozen=True)
class OwnedRecord:
    owner_id: str | None
    record: SearchRecord


def text_sha256(content):
    """Fingerprint UTF-8 content independently of Git's LF/CRLF checkout setting."""
    return hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()


def load_inputs(directory=ROOT):
    directory = Path(directory)
    manifest = json.loads((directory / "frozen_inputs.json").read_text(encoding="utf-8"))
    if set(manifest) != {"corpus.json", "cases.json"}:
        raise ValueError("Frozen manifest must identify corpus.json and cases.json")
    inputs = {}
    for name, digest in manifest.items():
        content = (directory / name).read_bytes()
        if text_sha256(content) != digest:
            raise ValueError(f"Frozen input changed: {name}")
        inputs[name] = json.loads(content)
    corpus, suite = inputs["corpus.json"], inputs["cases.json"]
    if corpus["version"] != 1 or suite["version"] != 1:
        raise ValueError("Unsupported evaluation version")
    accounts = corpus["accounts"]
    if set(accounts) != {"guest", "account_a", "account_b"} or accounts["guest"] is not None:
        raise ValueError("Expected fictional guest/A/B views")
    if not accounts["account_a"] or not accounts["account_b"] or accounts["account_a"] == accounts["account_b"]:
        raise ValueError("Accounts A and B must have different owners")
    owned, identities = [], set()
    for item in corpus["records"]:
        task = ExtractedTask.model_validate(item["task"])
        scope, owner = item["scope"], item["owner_id"]
        if (scope == "public" and (owner is not None or task.user_id is not None)
                or scope == "personal" and (owner not in (accounts["account_a"], accounts["account_b"])
                                            or task.user_id != owner)):
            raise ValueError("Invalid fictional task ownership")
        record = map_task(task, scope=scope)
        identity = owner, record.key
        if identity in identities:
            raise ValueError("Duplicate owner/scoped task identity")
        identities.add(identity)
        owned.append(OwnedRecord(owner, record))
    ids = set()
    for case in suite["cases"]:
        if case["id"] in ids or case["split"] not in ("tuning", "held-out") or case["kind"] not in KINDS:
            raise ValueError("Invalid case ID, split, or scoring kind")
        ids.add(case["id"])
        visible = visible_records(owned, accounts, case)
        expected = {tuple(key) for key in case["expected_relevant_keys"]}
        if len(expected) != len(case["expected_relevant_keys"]) or not expected <= {r.key for r in visible}:
            raise ValueError(f"Expected keys must be unique and visible: {case['id']}")
        if case["kind"] == "paraphrase" and not expected:
            raise ValueError("Answerable paraphrases need authored relevant keys")
        if case["kind"] == "unrelated" and expected:
            raise ValueError("Unrelated cases require an explicit empty answer")
        if case["zero_literal_overlap"]:
            for record in visible:
                text = (record.title + " " + (record.description or "")).casefold()
                if record.key in expected and any(term in text for term in case["query"].casefold().split()):
                    raise ValueError(f"Zero-overlap annotation is incorrect: {case['id']}")
        if case["point_rule"] is not None:
            rule = case["point_rule"]
            if rule["operator"] not in POINT_RULES or type(rule["value"]) is not int:
                raise ValueError("Invalid authored point predicate")
            if any(not point_matches(r, rule) for r in visible if r.key in expected):
                raise ValueError(f"Expected key violates authored point predicate: {case['id']}")
    return accounts, tuple(owned), suite["cases"], manifest


def visible_records(owned, accounts, case):
    viewer = case["viewer"]
    if viewer not in accounts:
        raise ValueError(f"Unknown fictional viewer: {viewer}")
    preferences = case["source_preferences"]
    disabled = preferences["disabled_sources"]
    if (set(preferences) != {"disabled_sources"} or not isinstance(disabled, list)
            or not set(disabled) <= {item.record.publisher for item in owned}):
        raise ValueError("Invalid fictional source preferences")
    return tuple(item.record for item in owned
                 if (item.record.scope == "public" or item.owner_id == accounts[viewer])
                 and item.record.publisher not in disabled)


def point_matches(record, rule):
    return record.training_points is not None and POINT_RULES[rule["operator"]](record.training_points, rule["value"])


def evaluate(directory=ROOT, *, matcher=search_records):
    accounts, owned, cases, manifest = load_inputs(directory)
    violations = {name: [] for name in ("visibility", "point_filter", "strict_boundary", "controls")}
    rows = []
    for case in cases:
        visible = visible_records(owned, accounts, case)
        result = matcher(visible, case["query"], filters=case["filters"], sort=case["sort"])
        actual = [record.key for record in result.hits]
        expected = [tuple(key) for key in case["expected_relevant_keys"]]
        for stage, records in (("hits", result.hits), ("eligible_records", result.eligible_records)):
            for record in records:
                detail = {"case_id": case["id"], "stage": stage, "key": list(record.key)}
                # Reference identity catches another owner's record even when scoped UUIDs collide.
                if not any(record is permitted for permitted in visible):
                    violations["visibility"].append(detail)
                rule = case["point_rule"]
                if rule and not point_matches(record, rule):
                    violations["point_filter"].append({**detail, "points": record.training_points})
                    if rule["operator"] in ("gt", "lt") and record.training_points == rule["value"]:
                        violations["strict_boundary"].append(detail)
        if case["kind"] not in ("paraphrase", "unrelated") and set(actual) != set(expected):
            violations["controls"].append({"case_id": case["id"], "expected": case["expected_relevant_keys"],
                                           "actual": [list(key) for key in actual]})
        if len(actual) != len(set(actual)):
            violations["controls"].append({"case_id": case["id"], "reason": "duplicate scoped key"})
        rows.append({"case_id": case["id"], "split": case["split"], "kind": case["kind"],
                     "query": case["query"], "viewer": case["viewer"],
                     "source_preferences": case["source_preferences"], "filters": case["filters"],
                     "expected_relevant_keys": case["expected_relevant_keys"],
                     "actual_top_three": [list(key) for key in actual[:3]],
                     "hit_count": len(actual), "eligible_count": len(result.eligible_records),
                     "expected_positions": [{"key": list(key), "position": actual.index(key) + 1 if key in actual else None}
                                            for key in expected]})
    retrieval = {}
    unrelated = {}
    for split in ("tuning", "held-out"):
        paraphrases = [row for row in rows if row["split"] == split and row["kind"] == "paraphrase"]
        negatives = [row for row in rows if row["split"] == split and row["kind"] == "unrelated"]
        retrieval[split] = {"hits_at_three": sum(any(key in row["actual_top_three"] for key in row["expected_relevant_keys"])
                                               for row in paraphrases), "total": len(paraphrases)}
        false_hits = [row["case_id"] for row in negatives if row["hit_count"]]
        unrelated[split] = {"false_hit_case_ids": false_hits, "false_hits": len(false_hits), "total": len(negatives)}
    negatives = [row for row in rows if row["kind"] == "unrelated"]
    false_hits = [row["case_id"] for row in negatives if row["hit_count"]]
    unrelated["all"] = {"false_hit_case_ids": false_hits, "false_hits": len(false_hits), "total": len(negatives)}
    return {"version": 1, "method": "keyword", "inputs_sha256": manifest,
            "matcher_sha256_lf": text_sha256(Path(keyword_matcher.__file__).read_bytes()),
            "corpus_records": len(owned), "case_counts": dict(sorted(Counter(row["kind"] for row in rows).items())),
            "paraphrase_retrieval": retrieval, "unrelated_queries": unrelated,
            "correctness_violations": violations, "cases": rows}


def render_report(report):
    return (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--output", type=Path, help="Write a measured report (never rewrites inputs)")
    action.add_argument("--check", action="store_true", help="Compare with the saved keyword baseline")
    args = parser.parse_args()
    try:
        report = evaluate()
        content = render_report(report)
        if args.output:
            if args.output.resolve() in {(ROOT / name).resolve() for name in ("corpus.json", "cases.json", "frozen_inputs.json")}:
                raise ValueError("Cannot overwrite frozen inputs with a report")
            args.output.write_bytes(content)
        elif args.check and content != (ROOT / "keyword_baseline.json").read_bytes().replace(b"\r\n", b"\n"):
            raise ValueError("Stored keyword baseline differs; it was not overwritten")
        for split in ("tuning", "held-out"):
            score, negatives = report["paraphrase_retrieval"][split], report["unrelated_queries"][split]
            print(f"{split}: paraphrase top-three {score['hits_at_three']}/{score['total']}; "
                  f"unrelated false hits {negatives['false_hits']}/{negatives['total']} {negatives['false_hit_case_ids']}")
        negatives = report["unrelated_queries"]["all"]
        print(f"All unrelated queries: false hits {negatives['false_hits']}/{negatives['total']} {negatives['false_hit_case_ids']}")
        failures = {name: len(items) for name, items in report["correctness_violations"].items()}
        print("Correctness violations:", failures)
        if args.check:
            print("Saved per-query ordering and aggregates match byte-for-byte")
        return int(any(failures.values()))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Evaluation setup/check failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
