from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect
from test_search_ui import serve_ui, submit, close_details

@pytest.mark.parametrize("width,height",[(1440,1000),(390,844)])
def test_compact_closed_open_details_and_keyboard(tmp_path,width,height):
    with serve_ui(tmp_path) as url, sync_playwright() as pw:
        browser=pw.chromium.launch(channel="msedge",headless=True)
        try:
            page=browser.new_page(viewport={"width":width,"height":height})
            page.route("**/*",lambda route:route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+"/start")
            trigger=page.get_by_role("button",name="Search tasks",exact=True)
            expect(trigger).to_be_visible(timeout=15000)
            page.wait_for_function("window.did_handshake === true")
            expect(page.locator(".search-query input")).not_to_be_visible()
            grid=page.locator(".month-grid").bounding_box()
            if width>1000:
                boxes=[page.locator(selector).bounding_box() for selector in (".filter-group",".compact-search-trigger",".view-switch")]
                assert max(b["y"] for b in boxes)-min(b["y"] for b in boxes)<15
                assert grid["y"]-max(b["y"]+b["height"] for b in boxes)<20
            page.screenshot(path=str(tmp_path/f"closed-{width}.png"),full_page=True)
            trigger.click()
            expect(page.locator(".search-query input")).to_be_focused()
            assert page.locator(".month-grid").bounding_box()==grid
            expect(page.locator(".search-count")).to_have_count(0)
            submit(page,"drive")
            expect(page.locator(".search-result")).to_have_count(3)
            page.screenshot(path=str(tmp_path/f"open-{width}.png"),full_page=True)
            bounds=page.locator(".task-search-popover").bounding_box()
            assert bounds["x"]>=0 and bounds["x"]+bounds["width"]<=width+1
            assert bounds["y"]>=0 and bounds["y"]+bounds["height"]<=height+1
            page.locator(".search-result").first.click()
            expect(page.locator(".search-detail-dialog")).to_be_visible()
            close_details(page)
            expect(page.locator(".search-result").first).to_be_focused()
            page.locator(".search-query input").focus()
            page.keyboard.press("Escape")
            expect(page.locator(".task-search-popover")).not_to_be_visible()
            expect(trigger).to_be_focused()
            trigger.click()
            expect(page.locator(".search-result")).to_have_count(3)
            page.get_by_role("button",name="Clear",exact=True).click()
            expect(page.locator(".search-result")).to_have_count(0)
            expect(page.locator(".search-count")).to_have_count(0)
            print("SCREENSHOTS",tmp_path)
        finally: browser.close()
