from test_search_ui import close_search
from test_search_ui import open_search
from playwright.sync_api import sync_playwright, expect
from test_search_ui import APP, serve_ui, submit, choose, close_details, fictional_tasks


def test_idle_submission_independent_filters_and_clear(tmp_path):
    code = APP.replace('return {"reads": backend.reads, "selected": keys}',
        'return {"reads": backend.reads, "selected": keys, "calendar": [(str(c.state.visible_month),str(c.state.selected_date),c.state.selected_item_id,c.state.filters.kind) for c in controllers]}')
    tasks = fictional_tasks()
    tasks[0]["training_points"] = 1
    with serve_ui(tmp_path, app_code=code, tasks=tasks) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width":1280,"height":900})
            page.route("**/*",lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+"/start")
            open_search(page)
            expect(page.get_by_label("Query",exact=True)).to_be_visible()
            expect(page.locator(".search-result")).to_have_count(0)
            expect(page.locator(".search-count")).to_have_count(0)
            initial_reads = page.request.get(url+"/test-state").json()["reads"]
            page.get_by_label("Query",exact=True).fill("drive")
            choose(page,"Type","Events")
            expect(page.locator(".search-result")).to_have_count(0)
            previous = page.get_by_label("Query",exact=True).get_attribute("id")
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.get_by_role("button",name="Classes",exact=True).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.get_by_label("Query", exact=True)).to_be_visible()
            expect(page.get_by_label("Query",exact=True)).to_have_value("drive")
            page.get_by_label("Query",exact=True).press("Enter")
            page.wait_for_timeout(500)
            expect(page.locator(".search-result")).to_have_count(3)
            assert set(page.locator(".search-result-points").all_text_contents()) == {"1 training point","5 training points","7 training points"}
            page.get_by_label("Query",exact=True).fill("unsubmitted draft")
            choose(page,"Sort","Title A–Z")
            expect(page.locator(".search-result")).to_have_count(3)
            expect(page.get_by_label("Query",exact=True)).to_have_value("unsubmitted draft")
            expect(page.locator(".event-pill").filter(has_text="Weekly class").first).to_be_visible()
            close_search(page)
            page.locator(".event-pill").filter(has_text="Weekly class").first.click()
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".task-panel .detail-title")).to_have_text("Weekly class")
            saved = page.request.get(url+"/test-state").json()["calendar"]
            page.locator(".search-result").first.click()
            expect(page.locator(".search-detail-dialog")).to_be_visible()
            close_details(page)
            page.locator(".search-query-row").get_by_role("button",name="Clear",exact=True).click()
            expect(page.locator(".search-result")).to_have_count(0)
            expect(page.locator(".search-count")).to_have_count(0)
            expect(page.get_by_label("Query",exact=True)).to_have_value("")
            expect(page.locator(".event-pill").filter(has_text="Weekly class").first).to_be_visible()
            assert page.request.get(url+"/test-state").json()["calendar"] == saved
            assert page.request.get(url+"/test-state").json()["reads"] == initial_reads
            choose(page,"Type","Notices")
            expect(page.locator(".search-result")).to_have_count(0)
            page.get_by_role("button",name="Search",exact=True).click()
            expect(page.locator(".search-result")).to_have_count(1)
            expect(page.locator(".search-result-meta")).to_contain_text("Notice")
            expect(page.locator(".search-result-points")).to_have_count(0)
            page.get_by_label("Deadline from",exact=True).fill("2027-01-20")
            page.get_by_label("Deadline through",exact=True).fill("2027-01-01")
            page.get_by_label("Deadline through",exact=True).press("Tab")
            expect(page.locator(".search-error")).to_be_visible()
            page.get_by_label("Deadline through",exact=True).fill("2027-01-30")
            page.get_by_label("Deadline through",exact=True).press("Tab")
            expect(page.locator(".search-error")).to_have_count(0)
            page.set_viewport_size({"width":390,"height":844})
            submit(page,"does not exist")
            expect(page.get_by_text("No matching tasks",exact=True)).to_be_visible()
            assert page.request.get(url+"/test-state").json()["reads"] == initial_reads
        finally:
            browser.close()


def test_personal_search_while_calendar_shows_assignments(tmp_path):
    tasks = fictional_tasks()
    base = {**tasks[3], "user_id":"demo-user", "source_platform":"Moodle"}
    tasks += [{**base,"id":"77777777-7777-4777-8777-777777777777","type":"personal","title":"Owner planning", "source_url":"https://example.invalid/planning"},
              {**base,"id":"88888888-8888-4888-8888-888888888888","type":"assignment","title":"Dated worksheet","deadline":"2026-11-26T09:00:00+07:00"}]
    with serve_ui(tmp_path,tasks=tasks) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge",headless=True)
        try:
            context = browser.new_context(viewport={"width":390,"height":844})
            context.route("**/*",lambda route:route.continue_() if route.request.url.startswith(url) else route.fulfill(body="Controlled source"))
            page = context.new_page()
            page.goto(url+"/start")
            open_search(page)
            expect(page.get_by_label("Query",exact=True)).to_be_visible()
            reads = page.request.get(url+"/test-state").json()["reads"]
            previous = page.get_by_label("Query",exact=True).get_attribute("id")
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.get_by_role("button",name="Assignments",exact=True).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.get_by_label("Query", exact=True)).to_be_visible()
            choose(page,"Type","Personal")
            submit(page,"planning")
            expect(page.locator(".search-result")).to_have_count(1)
            expect(page.locator(".search-result-meta")).to_contain_text("Personal")
            expect(page.locator(".event-pill")).to_have_count(1)
            expect(page.locator(".event-pill")).to_contain_text("Dated worksheet")
            close_search(page)
            page.locator(".event-pill").click()
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".task-panel .detail-title")).to_have_text("Dated worksheet")
            page.locator(".search-result").click()
            expect(page.locator(".search-detail-dialog .detail-title")).to_have_text("Owner planning")
            with page.expect_popup() as opened:
                page.locator(".search-detail-dialog .source-link").click()
            opened.value.wait_for_load_state()
            assert opened.value.url == "https://example.invalid/planning"
            opened.value.close()
            close_details(page)
            expect(page.locator(".task-panel .detail-title")).to_have_text("Dated worksheet")
            for day, count in (("26",1),("27",0)):
                close_search(page)
                page.locator(".day-cell:not(.outside-month)").get_by_role("button",name=day,exact=True).click()
                page.wait_for_timeout(200)
                open_search(page)
                expect(page.locator(".selected-date")).to_contain_text(day)
                expect(page.locator(".selected-item")).to_have_count(count)
                expect(page.locator(".search-result")).to_have_count(1)
            old_query = page.get_by_label("Query",exact=True).get_attribute("id")
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.locator(".month-controls button").nth(1).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.get_by_label("Query", exact=True)).to_be_visible()
            expect(page.get_by_label("Query",exact=True)).to_have_value("planning")
            expect(page.locator(".search-result")).to_have_count(1)
            assert page.request.get(url+"/test-state").json()["reads"] == reads
        finally:
            browser.close()
