"""Actual popover first-search/preparation measurement, separate from P reports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from time import perf_counter

from uuid import NAMESPACE_URL, uuid5
from .run_keyword import ROOT, load_inputs

INSTRUMENT = r'''
import time, types, threading
import academic_search.semantic as semantic_module
import client.core.controller as controller_module
counts={'foreground_queries':0,'foreground_passages':0,'preparation_passages':0,
        'foreground_encode_ms':0.,'preparation_encode_ms':0.,'model_startup_ms':0.}
role=threading.local()
BaseEncoder=semantic_module.LocalEncoder
class MeasuredEncoder(BaseEncoder):
    def __init__(self,*args,**kwargs):
        started=time.perf_counter()
        super().__init__(*args,**kwargs)
        counts['model_startup_ms']+=(time.perf_counter()-started)*1000
    def encode(self,texts):
        kind=getattr(role,'value','foreground')
        counts[kind+'_passages']+=sum(t.startswith('passage: ') for t in texts)
        if kind=='foreground': counts['foreground_queries']+=sum(t.startswith('query: ') for t in texts)
        started=time.perf_counter()
        try: return super().encode(texts)
        finally: counts[kind+'_encode_ms']+=(time.perf_counter()-started)*1000
semantic_module.LocalEncoder=MeasuredEncoder
BaseRanker=semantic_module.HybridSearch
class MeasuredRanker(BaseRanker):
    def __call__(self,*args,**kwargs):
        role.value='foreground'
        return super().__call__(*args,**kwargs)
    if hasattr(BaseRanker,'prepare_batch'):
        def prepare_batch(self,*args,**kwargs):
            role.value='preparation'
            try: return super().prepare_batch(*args,**kwargs)
            finally: role.value='foreground'
controller_module.HybridSearch=MeasuredRanker
token='idle'
original_results=SearchPanel.results
def measured_results(self):
    original_results(self)
    if self.submitted:
        phase=('preliminary' if getattr(self,'_preliminary_result',None) is not None else 'pending') if self._pending else 'final'
        ui.element('span').props('data-first-search='+token+'-'+phase)
SearchPanel.results=measured_results
@app.post('/first/arm/{value}')
def arm(value:str):
    global token
    token=value
    return counts.copy()
@app.get('/first/state')
def first_state():
    controllers=list(getattr(backend,'_controllers',()))
    c=controllers[-1] if controllers else None
    return {'counts':counts.copy(),'reads':backend.reads,
            'preparation':getattr(c,'preparation_status',{'state':'unsupported'})}
@app.get('/first/prepared')
async def first_prepared():
    import asyncio
    controllers=list(getattr(backend,'_controllers',()))
    c=controllers[-1] if controllers else None
    task=getattr(c,'_preparation_task',None)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task),180)
    return first_state()
'''


def tasks(size):
    """Preserve frozen text/facts; project ownership/UUIDs into one mock view."""
    corpus = json.loads((ROOT / 'corpus.json').read_text(encoding='utf-8'))['records']
    result = []
    for index in range(size):
        item = corpus[index % len(corpus)]
        task = dict(item['task'])
        task['id'] = str(uuid5(NAMESPACE_URL, f'smart-calendar-latency/{index}'))
        task['user_id'] = 'demo-user' if item['scope'] == 'personal' else None
        if size > 14:
            task['title'] += f' · Nhóm thực hành {index + 1}'
        result.append(task)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--sizes',type=int,nargs='+',default=[14,1008])
    parser.add_argument('--warm-queries',action='store_true',help='Measure a different and repeated query after preparation')
    parser.add_argument('--check',action='store_true',help='Compare complete ordered keys with the retained measurement')
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Preserve retained evidence; write observations to TEMP')
    load_inputs()
    sys.path.insert(0,str(ROOT.parents[1]/'tests'))
    from search_ui_support import APP,serve_ui,open_search,close_details
    from playwright.sync_api import sync_playwright,expect
    app_code=APP.replace('backend = CountingBackend',INSTRUMENT+'\nbackend = CountingBackend')
    rows=[]
    for size in args.sizes:
        for scenario in ('immediate_literal','immediate_paraphrase','prepared'):
            folder=Path(tempfile.mkdtemp(prefix='first-search-bench-'))
            with serve_ui(folder,app_code=app_code,tasks=tasks(size)) as url,sync_playwright() as pw:
                browser=pw.chromium.launch(channel='msedge',headless=True)
                try:
                    page=browser.new_page(viewport={'width':1440,'height':1000})
                    page.set_default_timeout(180000)
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url) else route.abort())
                    started=perf_counter();page.goto(url+'/start')
                    page.get_by_role('button',name='Search tasks',exact=True).wait_for()
                    page.wait_for_function('window.did_handshake === true')
                    ready=(perf_counter()-started)*1000
                    state=page.request.get(url+'/first/state').json()
                    if scenario=='prepared' and state['preparation']['state']!='unsupported':
                        page.request.get(url+'/first/prepared',timeout=190000)
                    open_search(page)
                    query='thời điểm' if scenario=='immediate_literal' else 'hạn cuối đóng học phí'
                    page.locator(".search-query input").fill(query)
                    previous=page.request.post(url+'/first/arm/'+scenario).json()
                    at_submit=page.request.get(url+'/first/state').json()
                    started=perf_counter();page.locator(".search-query input").press('Enter')
                    page.locator('[data-first-search]').first.wait_for(state='attached')
                    phase=page.locator('[data-first-search]').first.get_attribute('data-first-search')
                    preliminary_ms=None
                    if phase.endswith('preliminary'):
                        page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
                        preliminary_ms=(perf_counter()-started)*1000
                    page.locator(f'[data-first-search="{scenario}-final"]').wait_for(state='attached')
                    page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
                    final_ms=(perf_counter()-started)*1000
                    after=page.request.get(url+'/first/state').json()
                    if after['preparation']['state'] not in ('unsupported','disabled','unavailable','partial','complete'):
                        after=page.request.get(url+'/first/prepared',timeout=190000).json()
                    detail_reads=after['reads']
                    first=page.locator('.search-result').first
                    task_id=first.get_attribute('data-search-key').split(':',1)[1]
                    expected=next(task for task in tasks(size) if task['id']==task_id)
                    first.click()
                    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text(expected['title'])
                    expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href',expected['source_url'])
                    close_details(page)
                    expect(first).to_be_focused()
                    detail_reads=page.request.get(url+'/first/state').json()['reads']-detail_reads
                    ordered_keys=page.locator('.search-result').evaluate_all("xs=>xs.map(x=>x.getAttribute('data-search-key'))")
                    warm=[]
                    if args.warm_queries and scenario=='prepared':
                        for operation in ('different_query','repeat_query'):
                            marker=scenario+'-'+operation
                            page.locator('.search-query input').fill('tìm chỗ làm lập trình')
                            prior=page.request.post(url+'/first/arm/'+marker).json()
                            read_count=page.request.get(url+'/first/state').json()['reads']
                            warm_started=perf_counter()
                            page.locator('.search-query input').press('Enter')
                            page.locator(f'[data-first-search="{marker}-final"]').wait_for(state='attached')
                            page.evaluate('() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))')
                            visible_ms=(perf_counter()-warm_started)*1000
                            latest=page.request.get(url+'/first/state').json()
                            warm.append(dict(operation=operation,visible_ms=visible_ms,
                                queries=latest['counts']['foreground_queries']-prior['foreground_queries'],
                                passages=latest['counts']['foreground_passages']-prior['foreground_passages'],
                                encode_ms=latest['counts']['foreground_encode_ms']-prior['foreground_encode_ms'],
                                task_reads=latest['reads']-read_count,
                                preparation_state=latest['preparation']['state'],
                                ordered_keys=page.locator('.search-result').evaluate_all("xs=>xs.map(x=>x.getAttribute('data-search-key'))")))
                            assert warm[-1]['passages']==warm[-1]['task_reads']==0
                            assert warm[-1]['queries']==1
                        assert warm[0]['ordered_keys']==warm[1]['ordered_keys']
                    rows.append(dict(size=size,scenario=scenario,calendar_ready_ms=ready,
                        preparation_at_submit=at_submit['preparation'],preparation_final=after['preparation'],
                        preliminary_ms=preliminary_ms,hybrid_visible_ms=final_ms,
                        foreground_passages=after['counts']['foreground_passages']-previous['foreground_passages'],
                        foreground_queries=after['counts']['foreground_queries']-previous['foreground_queries'],
                        background_passages=after['counts']['preparation_passages'],task_reads_during_search=after['reads']-at_submit['reads'],
                        foreground_encode_ms=after['counts']['foreground_encode_ms']-previous['foreground_encode_ms'],
                        background_encode_ms=after['counts']['preparation_encode_ms'],
                        model_startup_ms=after['counts']['model_startup_ms'],
                        detail_task_reads=detail_reads,
                        warm_queries=warm,ordered_keys=ordered_keys))
                    print({k:v for k,v in rows[-1].items() if k not in ('ordered_keys','warm_queries')},flush=True)
                finally: browser.close()
            args.output.write_text(json.dumps({'rows':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.check:
        expected=json.loads((ROOT/'preparation_integrated.json').read_text(encoding='utf8'))
        from academic_search.semantic import REVISION, CUTOFF
        assert expected['model_revision']==REVISION and expected['cutoff']==CUTOFF
        for row in rows:
            old=next(r for r in expected['rows'] if (r['size'],r['scenario'])==(row['size'],row['scenario']))
            assert row['ordered_keys']==old['ordered_keys']
            assert row['task_reads_during_search']==row['detail_task_reads']==0
            assert row['foreground_passages']+row['background_passages']==row['size']
            if row['scenario']=='prepared':assert row['foreground_passages']==0
            if args.warm_queries:
                assert [q['ordered_keys'] for q in row['warm_queries']]==[q['ordered_keys'] for q in old['warm_queries']]
        print('Retained ordered outcomes and read/cache invariants match',flush=True)
    sources={name:hashlib.sha256(Path(path).read_bytes()).hexdigest()
             for name,path in [('semantic','academic_search/semantic.py'),('controller','client/core/controller.py'),('filters','client/components/filters.py'),('details','client/components/search_details.py')]}
    from academic_search.semantic import REVISION,CUTOFF
    args.output.write_text(json.dumps(dict(source_sha256=sources,
        model_revision=REVISION,cutoff=CUTOFF,device='CPU / '+platform.processor(),python=sys.version,
        tested_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        trial_count=1,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
