"""The popover's normal controller path with a deterministic local encoder."""

from playwright.sync_api import expect, sync_playwright
from test_search_ui import APP, OFF_MONTH, close_details, serve_ui, submit


def test_semantic_popover_details_and_no_additional_task_reads(tmp_path):
    code = APP.replace('backend = CountingBackend', '''
from academic_search.semantic import HybridSearch
import client.core.controller as controller_module
class FictionalEncoder:
    def encode(self, texts):
        return [[1., 0.]] + [[1., 0.] if 'Off-month report' in t else [0., 1.] for t in texts[1:]]
controller_module.HybridSearch = lambda: HybridSearch(FictionalEncoder())
backend = CountingBackend''')
    with serve_ui(tmp_path, app_code=code) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url + '/start')
            page.get_by_role('button', name='Search tasks', exact=True).wait_for()
            before = page.request.get(url + '/test-state').json()['reads']
            submit(page, 'báo cáo kỳ tới')
            expect(page.locator('.search-result')).to_have_count(1)
            result = page.locator(f'[data-search-key="{OFF_MONTH}"]')
            result.click()
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Off-month report')
            expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href', 'https://example.invalid/public/4')
            close_details(page)
            expect(result).to_be_focused()
            assert page.request.get(url + '/test-state').json()['reads'] == before
            page.request.post(url + '/session/account')
            expect(page.locator('.search-result')).to_have_count(0)
            expect(page.locator('.search-detail-dialog')).not_to_be_visible()
        finally:
            browser.close()
