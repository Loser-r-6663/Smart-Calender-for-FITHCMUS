"""Real-model, actual-popover benchmark; no live accounts or database needed."""

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from .run_keyword import ROOT

INSTRUMENT = r'''
import time, types, subprocess
import academic_search.semantic as semantic
import client.core.controller as controllers
from client.core.models import SyncResult
metrics = {}
token = 'idle'
if os.environ['BENCH_IMPL'] == 'baseline':
    semantic = types.ModuleType('academic_search._benchmark_baseline')
    semantic.__package__ = 'academic_search'
    exec(compile(subprocess.check_output(['git','show','961174a:academic_search/semantic.py']).decode(),
                 '<committed 961174a semantic>', 'exec'), semantic.__dict__)
    baseline_controller = types.ModuleType('client.core._benchmark_controller')
    baseline_controller.__package__ = 'client.core'
    exec(compile(subprocess.check_output(['git','show','961174a:client/core/controller.py']).decode(),
                 '<committed 961174a controller>', 'exec'), baseline_controller.__dict__)
    controllers = baseline_controller
    controllers.ClientController.defer_preparation = lambda self: None
    baseline_filters = types.ModuleType('client.components._benchmark_filters')
    baseline_filters.__package__ = 'client.components'
    exec(compile(subprocess.check_output(['git','show','961174a:client/components/filters.py']).decode(),
                 '<committed 961174a filters>', 'exec'), baseline_filters.__dict__)
    SearchPanel = baseline_filters.SearchPanel
    import client.pages.calendar as calendar_page
    calendar_page.ClientController = controllers.ClientController
    calendar_page.SearchPanel = SearchPanel
OriginalEncoder = semantic.LocalEncoder
class MeasuredEncoder(OriginalEncoder):
    def __init__(self, *args):
        started = time.perf_counter()
        super().__init__(*args)
        metrics['startup_ms'] = metrics.get('startup_ms', 0) + (time.perf_counter()-started)*1000
    def encode(self, texts):
        metrics['encoder_calls'] = metrics.get('encoder_calls',0)+1
        metrics['queries'] = metrics.get('queries',0)+sum(t.startswith('query: ') for t in texts)
        metrics['passages'] = metrics.get('passages',0)+sum(t.startswith('passage: ') for t in texts)
        started=time.perf_counter()
        result=super().encode(texts)
        metrics['inference_ms']=metrics.get('inference_ms',0)+(time.perf_counter()-started)*1000
        return result
semantic.LocalEncoder=MeasuredEncoder
class MeasuredRanker(semantic.HybridSearch):
    def __call__(self, *args, **kwargs):
        if os.environ['BENCH_IMPL'] == 'baseline':
            kwargs.pop('cache_token', None)
        result=super().__call__(*args, **kwargs)
        metrics['keys']=[list(r.key) for r in result.hits]
        return result
    def clear_cache(self, *args, **kwargs):
        if hasattr(super(), 'clear_cache'):
            super().clear_cache(*args, **kwargs)
controllers.HybridSearch=MeasuredRanker
original_results=SearchPanel.results
def measured_results(self):
    original_results(self)
    if not getattr(self, '_pending', False):
        ui.element('span').props('data-bench-token='+token)
SearchPanel.results=measured_results
original_get=CountingBackend.get_tasks
async def measured_get(self,user):
    metrics['task_reads']=metrics.get('task_reads',0)+1
    return await original_get(self,user)
CountingBackend.get_tasks=measured_get
async def fixed_sync(self,user,scope='all'):
    return SyncResult(ok=True,message='Benchmark snapshot refreshed')
CountingBackend.sync=fixed_sync
@app.post('/bench/arm/{value}')
def arm(value: str):
    global token
    token=value
    metrics.clear()
    return {'ok':True}
@app.get('/bench/metrics')
def bench_metrics():
    return metrics
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


def run_trial(size, trial, implementation):
    sys.path.insert(0, str(ROOT.parents[1] / 'tests'))
    from test_search_ui import APP, serve_ui, open_search, close_search, choose, close_details
    from playwright.sync_api import sync_playwright, expect
    app_code = APP.replace('backend = CountingBackend', INSTRUMENT + '\nbackend = CountingBackend')
    app_code = app_code.replace('show=False, reload=False,', 'show=False, reload=False, reconnect_timeout=300,')
    directory = Path(tempfile.mkdtemp(prefix=f'search-bench-{implementation}-{size}-{trial}-'))
    rows = []
    with serve_ui(directory, app_code=app_code, tasks=tasks(size)) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.set_default_timeout(240000)
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            started=perf_counter()
            page.goto(url+'/start', timeout=240000)
            page.get_by_role('button',name='Search tasks',exact=True).wait_for()
            page.wait_for_function('window.did_handshake === true')
            rows.append(dict(operation='app_open', visible_ms=(perf_counter()-started)*1000,
                             **page.request.get(url+'/bench/metrics').json()))
            open_search(page)
            def action(name, callback, *, rendered=True):
                marker=f'{size}-{trial}-{name}'
                page.request.post(url+'/bench/arm/'+marker)
                started=perf_counter()
                callback()
                if rendered:
                    page.locator(f'[data-bench-token="{marker}"]').wait_for(state='attached')
                page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                elapsed=(perf_counter()-started)*1000
                rows.append(dict(operation=name, visible_ms=elapsed, **page.request.get(url+'/bench/metrics').json()))
            def submit(name, query):
                page.get_by_label('Query',exact=True).fill(query)
                action(name, lambda: page.get_by_label('Query',exact=True).press('Enter'))
            submit('cold_search', 'hạn cuối đóng học phí')
            previous=page.get_by_label('Query',exact=True).get_attribute('id')
            page.get_by_role('button',name='Clear',exact=True).click()
            expect(page.get_by_label('Query',exact=True)).not_to_have_attribute('id',previous)
            close_search(page)
            previous=page.get_by_role('button',name='Search tasks',exact=True).get_attribute('id')
            def refresh():
                page.get_by_role('button',name='Run personal crawl',exact=True).click()
                expect(page.get_by_role('button',name='Search tasks',exact=True)).not_to_have_attribute('id',previous)
                expect(page.get_by_text('Benchmark snapshot refreshed',exact=True)).to_be_visible()
            action('snapshot_refresh',refresh,rendered=False)
            open_search(page)
            submit('first_fresh_search', 'hạn cuối đóng học phí')
            submit('different_query', 'tìm chỗ làm lập trình')
            action('repeat_query',lambda: page.get_by_label('Query',exact=True).press('Enter'))
            action('sort_title',lambda: choose(page,'Sort','Title A–Z'))
            action('narrow_type',lambda: choose(page,'Type','Notices'))
            action('widen_type',lambda: choose(page,'Type','All types'))
            def details():
                page.locator('.search-result').first.click()
                expect(page.locator('.search-detail-dialog .detail-title')).to_be_visible()
            action('open_details',details,rendered=False)
            close_details(page)
        finally:
            browser.close()
    return [dict(size=size,trial=trial,**row) for row in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--implementation', choices=['baseline','working'],required=True)
    parser.add_argument('--trials',type=int,default=2)
    parser.add_argument('--sizes',type=int,nargs='+',default=[14,1008])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    os.environ['BENCH_IMPL']=args.implementation
    rows=[]
    for size in args.sizes:
        for trial in range(args.trials):
            measured=run_trial(size,trial,args.implementation)
            rows.extend(measured)
            print(size,trial,[(r['operation'],round(r['visible_ms']),r.get('passages',0)) for r in measured],flush=True)
            args.output.write_text(json.dumps(dict(rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary=[]
    for size in args.sizes:
        for operation in dict.fromkeys(r['operation'] for r in rows):
            selected=[r for r in rows if r['size']==size and r['operation']==operation]
            summary.append(dict(size=size,operation=operation,trials=len(selected),
                median_ms=statistics.median(r['visible_ms'] for r in selected),
                slowest_ms=max(r['visible_ms'] for r in selected),
                median_inference_ms=statistics.median(r.get('inference_ms',0) for r in selected),
                passages=[r.get('passages',0) for r in selected],queries=[r.get('queries',0) for r in selected],
                encoder_calls=[r.get('encoder_calls',0) for r in selected],task_reads=[r.get('task_reads',0) for r in selected]))
    from academic_search.semantic import REVISION,CUTOFF
    report=dict(implementation=args.implementation, baseline_revision=subprocess.check_output(['git','rev-parse','961174a'],text=True).strip(),
                model_revision=REVISION,cutoff=CUTOFF,device=platform.processor(),
                corpus_sha256=hashlib.sha256((ROOT/'corpus.json').read_bytes()).hexdigest(),
                harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                reconnect_timeout_seconds=300,rows=rows,summary=summary)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
