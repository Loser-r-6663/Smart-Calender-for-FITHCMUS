"""Controlled encoders verify pending/final/fallback states and safe account changes."""
import re
import pytest
from playwright.sync_api import expect, sync_playwright
from search_ui_support import APP, PUBLIC, PERSONAL, OFF_MONTH, serve_ui, submit, close_details, open_search

pytestmark = pytest.mark.search_browser

def assert_neutral(page):
    expect(page.locator('.search-phase')).to_have_count(0)
    expect(page.locator('.loaded-search').get_by_text(
        re.compile(r'\b(hybrid|keyword|semantic)\b', re.I))).to_have_count(0)


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



def test_pending_empty_and_failure_feedback_is_neutral(tmp_path):
    width,height=1280,900
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
            row=page.locator(f'[data-search-key="{PERSONAL}"]')
            row.focus();row.press('Enter')
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Beta drive')
            expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href','https://example.invalid/personal/1')
            page.request.post(url+'/search-finish/ok')
            expect(page.locator('.search-count')).to_have_text('4 tasks · Best match')
            expect(page.locator('.search-preliminary')).to_have_count(0)
            close_details(page)
            expect(page.locator(f'[data-search-key="{PERSONAL}"]')).to_be_focused()
            assert_neutral(page)

            page.request.post(url+'/search-arm')
            submit(page,'báo cáo kỳ tới')
            expect(page.locator('.search-result')).to_have_count(0)
            expect(page.get_by_text('Searching…',exact=True)).to_be_visible()
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            previous=page.locator('.search-query input').get_attribute('id')
            page.get_by_role('button',name='Clear',exact=True).click()
            expect(page.locator('.search-query input')).not_to_have_attribute('id',previous)
            page.request.post(url+'/search-finish/ok')
            expect(page.locator('.search-count')).to_have_count(0)
            submit(page,'báo cáo kỳ tới')
            expect(page.locator(f'[data-search-key="{OFF_MONTH}"]')).to_be_visible()
            page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Off-month report')
            expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href','https://example.invalid/public/4')
            close_details(page)

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
            for mode,label in [('loading','Loading tasks…'),('expired','Session expired. Sign in again.')]:
                page.goto(url+'/feedback/'+mode);open_search(page)
                expect(page.get_by_text(label,exact=True)).to_be_visible()
                expect(page.locator('.search-count')).to_have_count(0)
            page.goto(url+'/feedback/failure');open_search(page)
            expect(page.get_by_text('Could not load tasks. Try refreshing.',exact=True)).to_be_visible()
            expect(page.locator('.search-count')).to_have_count(0)
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            assert_neutral(page)
        finally:
            browser.close()


def test_pending_inference_keeps_ui_responsive_and_discards_old_account(tmp_path):
    code = APP.replace('backend = CountingBackend', '''
import threading
from academic_search.semantic import HybridSearch
import client.core.controller as controller_module
release = threading.Event()
class DelayedEncoder:
    def encode(self, texts):
        assert release.wait(20)
        return [[1., 0.] for _ in texts]
controller_module.HybridSearch = lambda: HybridSearch(DelayedEncoder())
@app.post('/release-model')
def release_model():
    release.set()
    return {'ok':True}
backend = CountingBackend''')
    with serve_ui(tmp_path, app_code=code) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+'/start')
            submit(page, 'fictional private paraphrase')
            expect(page.get_by_text('Searching…',exact=True)).to_be_visible()
            assert page.request.post(url+'/session/account', timeout=5000).ok
            expect(page.locator('.search-detail-dialog .source-link')).to_have_count(0)
            expect(page.locator('.compact-search-trigger')).to_have_attribute('data-search-session','1')
            expect(page.locator('.task-search-popover')).not_to_be_visible()
            assert page.request.post(url+'/release-model', timeout=5000).ok
            submit(page, 'different paraphrase')
            expect(page.locator('.search-result')).to_have_count(1)
            expect(page.locator('.search-result-title')).to_have_text('Other account task')
            page.locator('.search-result').click()
            expect(page.locator('.source-link')).to_have_attribute('href','https://example.invalid/other')
        finally:
            browser.close()
