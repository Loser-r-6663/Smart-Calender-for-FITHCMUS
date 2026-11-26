"""Check ordered outcomes and summarize the paired first-search observations."""

import json

from .run_keyword import ROOT


def main():
    before=json.loads((ROOT/'preparation_before.json').read_text(encoding='utf-8'))
    after=json.loads((ROOT/'preparation_after.json').read_text(encoding='utf-8'))
    assert before['model_revision']==after['model_revision']
    assert before['cutoff']==after['cutoff']==0.86
    assert len(before['rows'])==len(after['rows'])==6
    rows=[]
    for old,new in zip(before['rows'],after['rows'],strict=True):
        assert (old['size'],old['scenario'])==(new['size'],new['scenario'])
        assert old['ordered_keys']==new['ordered_keys']
        assert old['task_reads_during_search']==new['task_reads_during_search']==0
        assert old['detail_task_reads']==new['detail_task_reads']==0
        assert old['foreground_passages']==old['size']
        assert new['foreground_passages']+new['background_passages']==new['size']
        assert new['foreground_queries']==1
        if new['scenario']=='prepared':
            assert new['preparation_at_submit']['state']=='complete'
            assert new['foreground_passages']==0
        else:
            assert new['preparation_at_submit']['state'] in ('pending','running')
            assert new['preliminary_ms'] is not None
        rows.append(dict(size=new['size'],scenario=new['scenario'],
            calendar_before_ms=old['calendar_ready_ms'],calendar_after_ms=new['calendar_ready_ms'],
            before_final_ms=old['hybrid_visible_ms'],after_preliminary_ms=new['preliminary_ms'],
            after_final_ms=new['hybrid_visible_ms'],
            preparation_ms=new['preparation_final']['duration_ms'],
            foreground_encode_ms=new['foreground_encode_ms'],
            background_encode_ms=new['background_encode_ms'],model_startup_ms=new['model_startup_ms']))
    report=dict(trial_count=1,comparison='Descriptive paired observations, not medians',
                all_ordered_results_unchanged=True,no_search_or_detail_task_reads=True,rows=rows)
    (ROOT/'preparation_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in rows:
        print({k:round(v,1) if isinstance(v,float) else v for k,v in row.items()})


if __name__=='__main__':main()
