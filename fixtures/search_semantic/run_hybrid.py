"""Verify current local retrieval and preparation against the retained frozen outcomes."""

import argparse
import json
import os
from pathlib import Path
from time import perf_counter

from academic_search.semantic import CUTOFF, MODEL_ID, REVISION, HybridSearch, LocalEncoder
from .run_keyword import ROOT, evaluate, render_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--output', type=Path, help='Optional observed report outside the fixture directory')
    args = parser.parse_args()
    if not args.check and args.output is None:
        parser.error('Use --check or --output')
    if args.output and args.output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Keep frozen evidence intact; write observations to TEMP')
    expected = json.loads((ROOT / 'hybrid_integrated_report.json').read_text(encoding='utf8'))
    assert expected['model_revision'] == REVISION and expected['cutoff'] == CUTOFF
    started = perf_counter()
    encoder = LocalEncoder(os.environ['SEARCH_SEMANTIC_MODEL'])
    startup = perf_counter() - started
    ordered, prepared_ordered = [], []
    hybrid, prepared = HybridSearch(encoder), HybridSearch(encoder)

    def retrieve(records, query='', **kwargs):
        result = hybrid(records, query, **kwargs)
        ordered.append([list(row.key) for row in result.hits])
        return result

    def retrieve_prepared(records, query='', **kwargs):
        epoch = prepared.begin_preparation(records, cache_token=records)
        start = 0
        while True:
            status = prepared.prepare_batch(records, cache_token=records, expected_epoch=epoch, start=start)
            if status['state'] != 'running':
                break
            start = status['next_index']
        assert status['state'] == 'complete'
        result = prepared(records, query, cache_token=records, **kwargs)
        prepared_ordered.append([list(row.key) for row in result.hits])
        return result

    started = perf_counter()
    report, warmed = evaluate(matcher=retrieve), evaluate(matcher=retrieve_prepared)
    assert report['cases'] == warmed['cases'] and ordered == prepared_ordered
    assert not any(report['correctness_violations'].values())
    if args.check:
        assert ordered == expected['ordered_hits_after']
        assert report['cases'] == expected['after']['cases']
        assert report['paraphrase_retrieval'] == expected['after']['paraphrase_retrieval']
    assert report['paraphrase_retrieval']['held-out']['hits_at_three'] > 0
    report.update(method='hybrid', model=MODEL_ID, revision=REVISION, cutoff=CUTOFF,
                  verification_kind='Regression on previously inspected frozen cases; no new tuning',
                  model_startup_seconds=startup, evaluation_seconds=perf_counter()-started,
                  ordered_hits=ordered, prepared_ordered_hits=prepared_ordered)
    if args.output:
        args.output.write_bytes(render_report(report))
    print('All 31 complete ordered result sets match before/after preparation')
    print(report['paraphrase_retrieval'], report['unrelated_queries']['all'], report['correctness_violations'])
    if args.check:
        print('Retained quality evidence matches; corpus, judgments, splits and cutoff unchanged')


if __name__ == '__main__':
    main()
