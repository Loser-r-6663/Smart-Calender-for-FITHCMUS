"""Compare real prepared retrieval against the captured reference ranker."""

import hashlib
import argparse
import json
import os
import types
from pathlib import Path
from time import perf_counter
import subprocess

from academic_search.semantic import CUTOFF, REVISION, HybridSearch, LocalEncoder
from .run_keyword import ROOT, evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'semantic_prepared_regression.json')
    args=parser.parse_args()
    if (args.output.resolve().parent!=ROOT.resolve() or
            args.output.name not in {'semantic_prepared_regression.json','hybrid_integrated_report.json'}):
        parser.error('Write a separate JSON report inside fixtures/search_semantic')
    archive=json.loads((ROOT/'preparation_reference.json').read_text(encoding='utf-8'))
    item=archive['files']['semantic']
    assert hashlib.sha256(item['source'].encode('utf-8')).hexdigest()==item['sha256']
    reference=types.ModuleType('academic_search._prepared_reference')
    reference.__package__='academic_search'
    exec(compile(item['source'],'<captured P semantic>','exec'),reference.__dict__)
    started=perf_counter()
    encoder=LocalEncoder(os.environ['SEARCH_SEMANTIC_MODEL'])
    startup=perf_counter()-started
    started=perf_counter()
    before_hits,after_hits=[],[]
    baseline=reference.HybridSearch(encoder)
    def before(records,query='',**kwargs):
        result=baseline(records,query,**kwargs)
        before_hits.append([list(r.key) for r in result.hits])
        return result
    prepared=HybridSearch(encoder)
    def after(records,query='',**kwargs):
        epoch=prepared.begin_preparation(records,cache_token=records)
        start=0
        while True:
            status=prepared.prepare_batch(records,cache_token=records,expected_epoch=epoch,start=start)
            if status['state']!='running': break
            start=status['next_index']
        assert status['state']=='complete',status
        result=prepared(records,query,cache_token=records,**kwargs)
        after_hits.append([list(r.key) for r in result.hits])
        return result
    first,second=evaluate(matcher=before),evaluate(matcher=after)
    first['method']='hybrid-reference'
    second['method']='hybrid-prepared'
    assert first['cases']==second['cases']
    assert before_hits==after_hits
    assert not any(second['correctness_violations'].values())
    historical=json.loads((ROOT/'hybrid_performance_report.json').read_text(encoding='utf-8'))
    assert [row['actual_top_three'] for row in second['cases']]==[row['actual_top_three'] for row in historical['cases']]
    report=dict(model_revision=REVISION,cutoff=CUTOFF,reference_sha256=item['sha256'],
                before=first,after=second,ordered_hits_before=before_hits,ordered_hits_after=after_hits,
                tested_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                model_startup_seconds=startup,evaluation_seconds=perf_counter()-started,
                comparison='Regression verification, not a fresh blind evaluation')
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('All 31 complete ordered result sets unchanged after real passage preparation')
    print(second['paraphrase_retrieval'],second['unrelated_queries']['all'],second['correctness_violations'])


if __name__=='__main__':main()
