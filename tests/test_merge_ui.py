from test_search_ui import close_search
from test_search_ui import open_search
"""Actual mock UI compatibility of Search, task management and weekly scheduling."""

from playwright.sync_api import expect, sync_playwright

from test_search_ui import fictional_tasks, serve_ui, submit, assert_keys, PUBLIC, close_details


def test_search_dialog_and_fe_task_management_schedule_controls(tmp_path):
    tasks = fictional_tasks()
    tasks[1]["id"] = "66666666-6666-4666-8666-666666666666"
    with serve_ui(tmp_path, tasks=tasks) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url + "/start")
            open_search(page)
            page.locator(".search-query input").wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.locator(".search-query input").press("Enter")
            expect(page.locator(".search-result")).to_have_count(6)
            submit(page, "thiện nguyện bé hơn 5 điểm")
            assert_keys(page, [PUBLIC])
            page.locator(f'[data-search-key="{PUBLIC}"]').click()
            expect(page.locator(".search-detail-dialog .detail-title")).to_have_text("Zulu drive")
            close_details(page)
            previous_query_id = page.locator(".search-query input").get_attribute("id")
            page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
            expect(page.locator(".search-query input")).not_to_have_attribute("id", previous_query_id)
            page.locator(".search-query input").wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.locator(".search-query input").press("Enter")
            expect(page.locator(".search-result")).to_have_count(6)
            expect(page.locator(".search-query input")).to_have_value("")
            close_search(page)
            page.get_by_role("button", name="New task", exact=True).click()
            dialog = page.get_by_role("dialog")
            expect(dialog).to_be_visible()
            dialog.get_by_label("Title *", exact=True).fill("Fictional undated assignment")
            dialog.get_by_role("combobox", name="Type", exact=True).locator("xpath=ancestor::label").click()
            page.locator(".q-menu").get_by_text("Assignment", exact=True).click()
            dialog.get_by_role("button", name="Create task", exact=True).click()
            expect(dialog).not_to_be_visible()
            expect(page.locator(".agenda-title").filter(has_text="Fictional undated assignment")).to_be_visible()
            submit(page, "Fictional undated assignment")
            expect(page.locator(".search-result")).to_have_count(1)
            page.locator(".search-result").click()
            expect(page.locator(".search-detail-dialog .detail-title")).to_have_text("Fictional undated assignment")
            close_details(page)
            previous_query_id = page.locator(".search-query input").get_attribute("id")
            page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
            expect(page.locator(".search-query input")).not_to_have_attribute("id", previous_query_id)
            page.locator(".search-query input").wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.locator(".search-query input").press("Enter")
            expect(page.locator(".search-result")).to_have_count(7)
            close_search(page)
            page.get_by_role("button", name="Auto-schedule", exact=True).click()
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.get_by_text("Weekly Optimized Timetable", exact=True)).to_be_visible(timeout=15000)
            expect(page.locator(".week-board")).to_be_visible()
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.get_by_role("button", name="Calendar", exact=True).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".month-grid")).to_be_visible()
        finally:
            browser.close()
