"""Neutral search feedback and shared task badges through actual controls."""

import re

import pytest
from playwright.sync_api import expect, sync_playwright

from test_search_ui import (
    APP, NOTICE, PUBLIC, WEEKLY, choose, close_details, fictional_tasks,
    open_search, serve_ui, submit,
)


def assert_neutral(page):
    expect(page.locator('.search-phase')).to_have_count(0)
    expect(page.locator('.loaded-search').get_by_text(
        re.compile(r'\b(hybrid|keyword|semantic)\b', re.I))).to_have_count(0)


def badge_style(badge):
    return badge.evaluate('''element => {
        const style = getComputedStyle(element);
        return Object.fromEntries(['backgroundColor', 'color', 'fontSize',
            'fontWeight', 'lineHeight', 'padding', 'borderRadius'].map(key => [key, style[key]]));
    }''')


@pytest.mark.parametrize('width,height', [(1280,900),(390,844)])
def test_result_badges_match_details_and_completed_feedback(tmp_path,monkeypatch,width,height):
    monkeypatch.delenv('SEARCH_SEMANTIC_MODEL',raising=False)
    tasks=fictional_tasks()
    for digit,kind,title in [('6','assignment','Dated assignment'),('7','personal','Owner planning')]:
        tasks.append({**tasks[3], 'id':f'{digit*8}-{digit*4}-4{digit*3}-8{digit*3}-{digit*12}',
                      'type':kind,'title':title,'user_id':'demo-user','source_platform':'Moodle'})
    expected=[
        (WEEKLY,'class','Class','rgb(106, 102, 163)'),
        ('personal:66666666-6666-4666-8666-666666666666','assignment','Assignment','rgb(183, 131, 57)'),
        (PUBLIC,'event','Event','rgb(62, 121, 108)'),
        (NOTICE,'announcement','Notice','rgb(102, 113, 123)'),
        ('personal:77777777-7777-4777-8777-777777777777','personal','Personal','rgb(74, 102, 140)'),
    ]
    with serve_ui(tmp_path,tasks=tasks) as url,sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport={'width':width,'height':height})
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+'/start');submit(page,'')
            expect(page.locator('.search-count')).to_have_text('8 tasks · Soonest deadline')
            reads=page.request.get(url+'/test-state').json()['reads']
            assert_neutral(page)
            choose(page,'Sort','Title A–Z')
            expect(page.locator('.search-count')).to_have_text('8 tasks · Title A–Z')
            expect(page.locator('.search-result-title')).to_have_text([
                'Alpha drive','Beta drive','Campus notice','Dated assignment',
                'Off-month report','Owner planning','Weekly class','Zulu drive'])
            for key,kind,label,color in expected:
                row=page.locator(f'[data-search-key="{key}"]')
                badge=row.locator('.type-badge')
                expect(badge).to_have_text(label)
                expect(badge).to_have_class(re.compile(r'\bsolid-kind-'+kind+r'\b'))
                style=badge_style(badge)
                assert style['backgroundColor']==color
                assert style['color']=='rgb(255, 255, 255)'
                row.click()
                detail=page.locator('.search-detail-dialog .type-badge')
                expect(detail).to_have_text(label)
                assert badge_style(detail)==style
                if kind=='class':
                    page.screenshot(path=str(tmp_path/f'class-dialog-{width}.png'))
                close_details(page)
                expect(row).to_be_focused()
            expect(page.locator(f'[data-search-key="{WEEKLY}"] .search-result-meta')).to_contain_text('Every Monday, 08:00')
            expect(page.locator(f'[data-search-key="{NOTICE}"] .search-result-meta')).to_contain_text('Date not provided')
            expect(page.locator(f'[data-search-key="{PUBLIC}"] .search-result-points')).to_have_text('4 training points')
            expect(page.locator(f'[data-search-key="{NOTICE}"] .search-result-points')).to_have_count(0)
            page.locator(f'[data-search-key="{WEEKLY}"]').scroll_into_view_if_needed()
            page.screenshot(path=str(tmp_path/f'result-badges-{width}.png'))
            assert_neutral(page)
            assert page.request.get(url+'/test-state').json()['reads']==reads
        finally:
            browser.close()


CONTROLLED_APP=APP.replace('backend = CountingBackend','''
import threading
from academic_search.semantic import HybridSearch
import client.core.controller as controller_module
finish=threading.Event()
mode='ok'
class ControlledEncoder:
    def encode(self,texts):
        queries=[text for text in texts if text.startswith('query: ')]
        if queries:
            assert finish.wait(30)
            if mode=='failure': raise RuntimeError('Controlled local failure')
        return [[-1.,0.] if text.startswith('query: ') and 'excluded' in text else
                [1.,0.] if text.startswith('query: ') or 'Off-month report' in text else [0.,1.]
                for text in texts]
controller_module.HybridSearch=lambda:HybridSearch(ControlledEncoder())
@app.post('/search-arm')
def arm():
    finish.clear()
    return {'ok':True}
@app.post('/search-finish/{value}')
def release(value:str):
    global mode
    mode=value
    finish.set()
    return {'ok':True}
backend = CountingBackend''')


@pytest.mark.parametrize('width,height', [(1280,900),(390,844)])
def test_pending_empty_and_failure_feedback_is_neutral(tmp_path,width,height):
    with serve_ui(tmp_path,app_code=CONTROLLED_APP) as url,sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport={'width':width,'height':height})
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+'/start');submit(page,'drive')
            expect(page.locator('.search-preliminary')).to_have_text('Searching…')
            expect(page.locator('.search-preliminary')).to_be_visible()
            expect(page.locator('.search-result')).to_have_count(3)
            expect(page.locator('.search-count')).to_have_count(0)
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            assert_neutral(page)
            reads=page.request.get(url+'/test-state').json()['reads']
            row=page.locator(f'[data-search-key="{PUBLIC}"]')
            row.click()
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Zulu drive')
            page.request.post(url+'/search-finish/ok')
            expect(page.locator('.search-count')).to_have_text('4 tasks · Best match')
            expect(page.locator('.search-preliminary')).to_have_count(0)
            close_details(page)
            expect(page.locator(f'[data-search-key="{PUBLIC}"]')).to_be_focused()
            assert_neutral(page)

            page.request.post(url+'/search-arm')
            submit(page,'excluded unrelated words')
            expect(page.locator('.search-preliminary')).to_have_text('Searching…')
            expect(page.locator('.search-preliminary')).to_be_visible()
            expect(page.locator('.search-result')).to_have_count(0)
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            page.request.post(url+'/search-finish/ok')
            expect(page.locator('.search-count')).to_have_text('0 tasks · Best match')
            expect(page.get_by_text('No matching tasks',exact=True)).to_be_visible()
            assert_neutral(page)

            for query,count in [('drive',3),('unrelated wording',0)]:
                page.request.post(url+'/search-arm')
                submit(page,query)
                expect(page.locator('.search-preliminary')).to_have_text('Searching…')
                page.request.post(url+'/search-finish/failure')
                expect(page.locator('.search-error')).to_have_text(
                    'Search could not complete. Showing available results.' if count else
                    'Search could not complete. Try again.')
                expect(page.locator('.search-error')).to_be_visible()
                expect(page.locator('.search-result')).to_have_count(count)
                if count:
                    expect(page.locator('.search-count')).to_have_text('3 tasks · Best match')
                else:
                    expect(page.locator('.search-count')).to_have_count(0)
                expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
                assert_neutral(page)
            assert page.request.get(url+'/test-state').json()['reads']==reads
            page.goto(url+'/feedback/failure');open_search(page)
            expect(page.get_by_text('Could not load tasks. Try refreshing.',exact=True)).to_be_visible()
            expect(page.locator('.search-count')).to_have_count(0)
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            assert_neutral(page)
        finally:
            browser.close()
