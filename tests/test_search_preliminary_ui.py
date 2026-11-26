"""Actual controls distinguish preliminary keyword rows from completed retrieval."""

import pytest
from playwright.sync_api import expect, sync_playwright
from test_search_ui import APP, PERSONAL, PUBLIC, OFF_MONTH, close_details, serve_ui, submit

APP_CODE=APP.replace('backend = CountingBackend','''
import threading
from academic_search.semantic import HybridSearch
import client.core.controller as controller_module
release_prep, release_final = threading.Event(), threading.Event()
class ControlledEncoder:
    def encode(self,texts):
        if any(t.startswith('query: ') for t in texts):
            assert release_final.wait(20)
        else:
            assert release_prep.wait(20)
        return [[-1.,0.] if t.startswith('query: ') and 'excluded' in t else [1.,0.] if t.startswith('query: ') or 'Off-month report' in t else [0.,1.] for t in texts]
controller_module.HybridSearch=lambda:HybridSearch(ControlledEncoder())
@app.post('/release/{kind}')
def release(kind:str):
    (release_prep if kind=='prep' else release_final).set()
    return {'ok':True}
backend = CountingBackend''')


@pytest.mark.parametrize('selected,title,url',[
    (PERSONAL,'Beta drive','https://example.invalid/personal/1'),
    (PUBLIC,'Zulu drive','https://example.invalid/public/1'),
])
def test_preliminary_details_survive_final_upgrade(tmp_path,selected,title,url):
    with serve_ui(tmp_path,app_code=APP_CODE) as base,sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
            page.goto(base+'/start');submit(page,'drive')
            expect(page.get_by_text('Searching…',exact=True)).to_be_visible()
            expect(page.locator('.search-result')).to_have_count(3)
            expect(page.locator('.search-count')).to_have_count(0)
            expect(page.locator('.search-points')).to_have_count(0)
            row=page.locator(f'[data-search-key="{selected}"]')
            if selected==PERSONAL:
                row.focus();row.press('Enter')
            else:
                row.click()
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text(title)
            expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href',url)
            reads=page.request.get(base+'/test-state').json()['reads']
            page.request.post(base+'/release/prep');page.request.post(base+'/release/final')
            expect(page.locator('.search-count')).to_be_visible()
            expect(page.locator('.search-result')).to_have_count(4)
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text(title)
            close_details(page)
            expect(page.locator(f'[data-search-key="{selected}"]')).to_be_focused()
            assert page.request.get(base+'/test-state').json()['reads']==reads
        finally:browser.close()


def test_zero_keyword_matches_searching_then_final_and_clear_cancels(tmp_path):
    with serve_ui(tmp_path,app_code=APP_CODE) as base,sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page()
            page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
            page.goto(base+'/start');submit(page,'báo cáo kỳ tới')
            expect(page.get_by_text('Searching…',exact=True)).to_be_visible()
            expect(page.get_by_text('No matching tasks',exact=True)).not_to_be_visible()
            expect(page.locator('.search-result')).to_have_count(0)
            old_input=page.get_by_label('Query',exact=True).get_attribute('id')
            page.get_by_role('button',name='Clear',exact=True).click()
            expect(page.get_by_label('Query',exact=True)).not_to_have_attribute('id',old_input)
            expect(page.locator('.search-preliminary')).to_have_count(0)
            expect(page.locator('.search-count')).to_have_count(0)
            submit(page,'báo cáo kỳ tới')
            expect(page.get_by_text('Searching…',exact=True)).to_be_visible()
            page.request.post(base+'/release/prep');page.request.post(base+'/release/final')
            expect(page.locator(f'[data-search-key="{OFF_MONTH}"]')).to_be_visible()
            expect(page.locator('.search-count')).to_be_visible()
            page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
            expect(page.get_by_text('0 training points',exact=True)).to_be_visible()
            close_details(page)
            page.get_by_role('button',name='Clear',exact=True).click()
            expect(page.locator('.search-count')).to_have_count(0)
            expect(page.locator('.search-result')).to_have_count(0)
            submit(page,'excluded unrelated words')
            expect(page.get_by_text('No matching tasks',exact=True)).to_be_visible()
            expect(page.locator('.search-points')).to_have_count(0)
        finally:browser.close()
