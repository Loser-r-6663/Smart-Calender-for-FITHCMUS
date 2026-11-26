"""Check ordered results and measured warm-query improvement."""

import json
from pathlib import Path

from .run_keyword import ROOT


def main():
    before=json.loads((ROOT/'latency_before.json').read_text(encoding='utf-8'))
    after=json.loads((ROOT/'latency_after.json').read_text(encoding='utf-8'))
    for key in ('model_revision','cutoff','corpus_sha256','reconnect_timeout_seconds'):
        assert before[key]==after[key], key
    differences=[]
    for old,new in zip(before['rows'],after['rows'],strict=True):
        identity=old['size'],old['trial'],old['operation']
        assert identity==(new['size'],new['trial'],new['operation'])
        if old.get('keys')!=new.get('keys'):
            differences.append(identity)
        if new['operation'] not in ('app_open','snapshot_refresh'):
            assert new.get('task_reads',0)==0, identity
        if new['operation'] in ('different_query','repeat_query','sort_title','narrow_type','widen_type'):
            assert new.get('passages',0)==0, identity
            assert new.get('queries',0)==1 and new.get('encoder_calls',0)==1, identity
    assert not differences, differences
    replay=json.loads((ROOT/'latency_baseline_replay.json').read_text(encoding='utf-8'))
    for old,new in zip(before['rows'][:10],replay['rows'],strict=True):
        assert old['operation']==new['operation'] and old.get('keys')==new.get('keys')
        assert old.get('passages',0)==new.get('passages',0)
    comparisons=[]
    for old,new in zip(before['summary'],after['summary'],strict=True):
        assert (old['size'],old['operation'])==(new['size'],new['operation'])
        saving=old['median_ms']-new['median_ms']
        comparisons.append(dict(size=old['size'],operation=old['operation'],
            before_median_ms=old['median_ms'],after_median_ms=new['median_ms'],
            before_slowest_ms=old['slowest_ms'],after_slowest_ms=new['slowest_ms'],
            savings_ms=saving,reduction_percent=100*saving/old['median_ms'],
            before_inference_ms=old['median_inference_ms'],after_inference_ms=new['median_inference_ms']))
        if old['operation']=='different_query':
            assert saving>0, comparisons[-1]
    result=dict(ordered_key_differences=differences,baseline_replay_verified=True,
                before_harness_sha256=before['harness_sha256'],after_harness_sha256=after['harness_sha256'],
                harness_note='After initial baseline, baseline imports were pinned to Git sources; timing and counting hooks unchanged.',
                comparisons=comparisons)
    (ROOT/'latency_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in comparisons:
        print(row['size'],row['operation'],f"{row['before_median_ms']:.1f} -> {row['after_median_ms']:.1f} ms; "
              f"{row['reduction_percent']:.1f}% reduction")
    print('PASS: ordered keys unchanged; warmed operations encode only queries and perform zero task reads')


if __name__=='__main__':
    main()
