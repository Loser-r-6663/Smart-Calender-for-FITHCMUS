"""Calibrate only on tuning cases, then measure the frozen hybrid comparison."""

import argparse
import json
import os
import platform
from pathlib import Path
from time import perf_counter

from academic_search.matcher import search_records
from academic_search.semantic import CUTOFF, MODEL_ID, REVISION, HybridSearch, LocalEncoder
from .run_keyword import ROOT, evaluate, load_inputs, render_report, visible_records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = perf_counter()
    encoder = LocalEncoder(os.environ["SEARCH_SEMANTIC_MODEL"])
    startup = perf_counter() - start
    accounts, owned, cases, _ = load_inputs()
    if args.calibrate:
        prepared = []
        for case in cases:
            if case["split"] != "tuning":
                continue
            records = visible_records(owned, accounts, case)
            literal = search_records(records, case["query"], filters=case["filters"], sort=case["sort"])
            texts = ["query: " + literal.topic] + ["passage: " + r.title + "\n" + (r.description or "")
                                                    for r in literal.eligible_records]
            vectors = encoder.encode(texts) if literal.topic else []
            prepared.append((case, records, vectors))
        trials = []
        for cutoff in [n / 1000 for n in range(750, 951, 5)]:
            hits = false_hits = controls = 0
            for case, records, vectors in prepared:
                class FrozenEncoder:
                    def encode(self, texts):
                        return vectors
                result = HybridSearch(FrozenEncoder(), cutoff=cutoff)(records, case["query"],
                                filters=case["filters"], sort=case["sort"])
                actual = [list(r.key) for r in result.hits]
                expected = case["expected_relevant_keys"]
                if case["kind"] == "paraphrase":
                    hits += any(key in actual[:3] for key in expected)
                elif case["kind"] == "unrelated":
                    false_hits += bool(actual)
                else:
                    controls += sorted(actual) != sorted(expected)
            trials.append(dict(cutoff=cutoff, hits=hits, false_hits=false_hits, controls=controls))
        valid = [row for row in trials if row["false_hits"] == row["controls"] == 0]
        selected = max(valid, key=lambda row: (row["hits"], row["cutoff"])) if valid else None
        report = {"model": MODEL_ID, "revision": REVISION, "split": "tuning only",
                  "selection_rule": "zero false hits and control violations, maximize recall, then higher cutoff",
                  "selected": selected, "trials": trials}
    else:
        hybrid = HybridSearch(encoder)
        start = perf_counter()
        report = evaluate(matcher=hybrid)
        elapsed = perf_counter() - start
        baseline = json.loads((ROOT / "keyword_baseline.json").read_text(encoding="utf-8"))
        for row, keyword in zip(report["cases"], baseline["cases"], strict=True):
            row["keyword_top_three"] = keyword["actual_top_three"]
            row["keyword_expected_positions"] = keyword["expected_positions"]
        start = perf_counter()
        first = cases[0]
        hybrid(visible_records(owned, accounts, first), first["query"])
        warm = perf_counter() - start
        report.update(method="hybrid", model=MODEL_ID, revision=REVISION, cutoff=CUTOFF,
                      device="CPU / " + platform.processor(), model_startup_seconds=startup,
                      all_cases_seconds=elapsed, warm_first_case_seconds=warm)
        if args.output.name == "hybrid_repair_report.json":
            report["verification_kind"] = "Post-repair regression; held-out outcomes previously inspected"
        print(report["paraphrase_retrieval"], report["unrelated_queries"], report["correctness_violations"])
    if args.output.resolve().parent != ROOT.resolve() or args.output.name not in ("hybrid_calibration.json", "hybrid_report.json", "hybrid_repair_report.json"):
        raise ValueError("Output must be a separate hybrid report in fixtures/search_semantic")
    args.output.write_bytes(render_report(report))
    print(json.dumps({k: v for k, v in report.items() if k not in ("cases", "trials")}, ensure_ascii=False))
    if args.calibrate:
        return int(report["selected"] is None)
    return int(any(report["correctness_violations"].values())
               or report["paraphrase_retrieval"]["held-out"]["hits_at_three"] == 0)


if __name__ == "__main__":
    raise SystemExit(main())
