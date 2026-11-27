"""Actual Search journeys: independent controls, original details, sessions and narrow focus."""
import re
import pytest
from playwright.sync_api import expect, sync_playwright
from search_ui_support import (
    APP, PUBLIC, PERSONAL, SEVEN, NOTICE, OFF_MONTH, WEEKLY,
    fictional_tasks, serve_ui, page, ui_server, ordered_keys, assert_keys,
    choose, close_search, open_search, submit, close_details, badge_style,
)

pytestmark = pytest.mark.search_browser


def test_documented_demo_exact_points_course_week_and_source(tmp_path, monkeypatch):
    monkeypatch.delenv('SEARCH_SEMANTIC_MODEL', raising=False)
    with serve_ui(tmp_path, module='fixtures.search_demo.app') as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 900})
            context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page = context.new_page()
            page.goto(url + '/login')
            page.get_by_label('Username', exact=True).fill('student')
            page.get_by_label('Password', exact=True).fill('demo')
            page.get_by_role('button', name='Sign in', exact=True).click()
            tuition = 'public:11111111-1111-4111-8111-111111111111'
            submit(page, 'Thời điểm hoàn tất nghĩa vụ tài chính')
            assert_keys(page, [tuition])
            row = page.locator(f'[data-search-key="{tuition}"]')
            row.focus(); row.press('Enter')
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Thời điểm hoàn tất nghĩa vụ tài chính')
            with context.expect_page() as opened:
                page.locator('.search-detail-dialog .source-link').click()
            expect(opened.value.get_by_text('Nguồn giả lập — không phải dữ liệu thật', exact=True)).to_be_visible()
            assert opened.value.url == url + '/demo-source/public/' + tuition.split(':')[1]
            opened.value.close(); close_details(page)
            expect(row).to_be_focused()
            for query, keys in (
                ('5 điểm', ['personal:88888888-8888-4888-8888-888888888888']),
                ('từ 5 điểm', ['personal:88888888-8888-4888-8888-888888888888', 'public:66666666-6666-4666-8666-666666666666']),
                ('nhiều hơn 5 điểm', ['public:66666666-6666-4666-8666-666666666666']),
            ):
                submit(page, query); assert_keys(page, keys)
                expect(page.locator('.search-points')).to_have_count(0)
            previous = page.locator('.search-query input').get_attribute('id')
            page.get_by_role('button', name='Clear', exact=True).click()
            expect(page.locator('.search-query input')).not_to_have_attribute('id', previous)
            expect(page.locator('.search-count')).to_have_count(0)
            choose(page, 'Type', 'Assignments'); choose(page, 'Course', 'CSC10006')
            page.get_by_label('Deadline from').fill('2026-11-30')
            page.get_by_label('Deadline through').fill('2026-12-06')
            submit(page, '')
            c = 'personal:a7100000-0000-4000-8000-000000000001'
            b = 'personal:33333333-3333-4333-8333-333333333333'
            g = 'personal:a7100000-0000-4000-8000-000000000002'
            for order, keys in (('Soonest deadline', [c,b,g]), ('Latest deadline', [g,b,c]), ('Title A–Z', [b,c,g])):
                choose(page, 'Sort', order); assert_keys(page, keys)
                expect(page.locator('.search-count')).to_have_text('3 tasks · ' + order)
                expect(page.get_by_label('Deadline from')).to_have_value('2026-11-30')
                expect(page.get_by_label('Deadline through')).to_have_value('2026-12-06')
            page.locator(f'[data-search-key="{c}"]').click()
            expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Chuẩn bị truy vấn dữ liệu')
            expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href', url + '/demo-source/personal/' + c.split(':')[1])
            page.keyboard.press('Escape')
            expect(page.locator('.search-detail-dialog')).not_to_be_visible()
            expect(page.locator(f'[data-search-key="{c}"]')).to_be_focused()
            page.screenshot(path=str(tmp_path / 'documented-demo.png'), animations='disabled')
        finally:
            browser.close()

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
            trigger=page.get_by_role('button',name='Search tasks',exact=True)
            if not page.locator('.search-query input').is_visible():
                expect(trigger).to_be_visible()
            page.wait_for_function('window.did_handshake === true')
            grid=page.locator('.month-grid').bounding_box()
            boxes=[page.locator(selector).bounding_box() for selector in
                   ('.filter-group','.compact-search-trigger','.view-switch')]
            assert max(b['y'] for b in boxes)-min(b['y'] for b in boxes)<15
            assert grid['y']-max(b['y']+b['height'] for b in boxes)<20
            open_search(page)
            expect(page.locator('.search-query input')).to_be_focused()
            assert page.locator('.month-grid').bounding_box()==grid
            expect(page.locator(".search-query input")).to_be_visible()
            expect(page.locator(".search-result")).to_have_count(0)
            expect(page.locator(".search-count")).to_have_count(0)
            initial_reads = page.request.get(url+"/test-state").json()["reads"]
            page.locator(".search-query input").fill("drive")
            choose(page,"Type","Events")
            expect(page.locator(".search-result")).to_have_count(0)
            previous = page.locator(".search-query input").get_attribute("id")
            close_search(page)
            expect(page.get_by_role('button', name='Search tasks', exact=True)).to_be_focused()
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.get_by_role("button",name="Classes",exact=True).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".search-query input")).to_be_visible()
            expect(page.locator(".search-query input")).to_have_value("drive")
            page.locator(".search-query input").press("Enter")
            expect(page.locator(".search-result")).to_have_count(3)
            assert set(page.locator(".search-result-points").all_text_contents()) == {"1 training point","5 training points","7 training points"}
            page.locator(".search-query input").fill("unsubmitted draft")
            choose(page,"Sort","Title A–Z")
            assert_keys(page, [SEVEN, PERSONAL, PUBLIC])
            choose(page, 'Sort', 'Best match')
            assert_keys(page, [PERSONAL, PUBLIC, SEVEN])
            expect(page.locator('.search-count')).to_have_text('3 tasks · Best match')
            expect(page.locator(".search-result")).to_have_count(3)
            expect(page.locator(".search-query input")).to_have_value("unsubmitted draft")
            page.get_by_role('combobox', name='Course', exact=True).locator('xpath=ancestor::label').click()
            expect(page.locator('.q-menu:not(.task-search-popover)').get_by_text('OTHER', exact=True)).to_be_visible()
            page.keyboard.press('Escape')
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
            expect(page.locator(".search-query input")).to_have_value("")
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
              {**base,"id":"88888888-8888-4888-8888-888888888888","type":"assignment","title":"Dated worksheet","training_points":5,"deadline":"2026-11-26T09:00:00+07:00"}]
    with serve_ui(tmp_path,tasks=tasks) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge",headless=True)
        try:
            context = browser.new_context(viewport={"width":390,"height":844})
            context.route("**/*",lambda route:route.continue_() if route.request.url.startswith(url) else route.fulfill(body="Controlled source"))
            page = context.new_page()
            page.goto(url+"/start")
            open_search(page)
            expect(page.locator(".search-query input")).to_be_visible()
            reads = page.request.get(url+"/test-state").json()["reads"]
            submit(page,'')
            for key in (OFF_MONTH, NOTICE):
                expect(page.locator(f'[data-search-key="{key}"] .search-result-points')).to_have_count(0)
            for key,kind,label,color in (
                (WEEKLY,'class','Class','rgb(106, 102, 163)'),
                ('personal:88888888-8888-4888-8888-888888888888','assignment','Assignment','rgb(183, 131, 57)'),
                (PUBLIC,'event','Event','rgb(62, 121, 108)'),
                (NOTICE,'announcement','Notice','rgb(102, 113, 123)'),
                ('personal:77777777-7777-4777-8777-777777777777','personal','Personal','rgb(74, 102, 140)'),
            ):
                badge=page.locator(f'[data-search-key="{key}"] .type-badge')
                expect(badge).to_have_text(label)
                expect(badge).to_have_class(re.compile(r'\bsolid-kind-'+kind+r'\b'))
                style=badge_style(badge)
                assert style['backgroundColor']==color
                assert style['color']=='rgb(255, 255, 255)'
            submit(page, "5 điểm")
            assert_keys(page, [PERSONAL])
            choose(page, "Type", "Assignments")
            expect(page.get_by_text("No matching tasks", exact=True)).to_be_visible()
            expect(page.locator(".search-result")).to_have_count(0)
            expect(page.locator(".search-error")).to_have_count(0)
            expect(page.get_by_role("combobox", name="Type", exact=True)
                   .locator("xpath=ancestor::label")).to_contain_text("Assignments")
            expect(page.locator(".search-query input")).to_have_value("5 điểm")
            previous = page.locator(".search-query input").get_attribute("id")
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.get_by_role("button",name="Assignments",exact=True).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".search-query input")).to_be_visible()
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
            old_query = page.locator(".search-query input").get_attribute("id")
            close_search(page)
            old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
            page.locator(".month-controls button").nth(1).click()
            expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
            page.wait_for_timeout(200)
            open_search(page)
            expect(page.locator(".search-query input")).to_be_visible()
            expect(page.locator(".search-query input")).to_have_value("planning")
            expect(page.locator(".search-result")).to_have_count(1)
            assert page.request.get(url+"/test-state").json()["reads"] == reads
        finally:
            browser.close()


def test_open_scoped_details_sources_occurrences_and_refresh(page, ui_server, tmp_path):
    before = page.request.get(ui_server + "/test-state").json()["reads"]
    month = page.locator(".month-label").inner_text()
    selected_date = page.locator(".selected-date").inner_text()
    submit(page, "report")
    choose(page, "Course", "OTHER")
    choose(page, "Sort", "Title A–Z")
    page.get_by_label("Deadline from").fill("2027-01-01")
    page.get_by_label("Deadline through").fill("2027-01-31")
    assert_keys(page, [OFF_MONTH])
    page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
    panel = page.locator(".search-detail-dialog .task-detail")
    calendar_panel = page.locator(".task-panel .task-detail")
    expect(panel.locator(".detail-title")).to_have_text("Off-month report")
    expect(calendar_panel).to_have_count(1)
    for text in ("0 training points", "Course: OTHER", "Publisher: VNUHCMUS",
                 "Deadline: 15 Jan 2027, 09:00 (Vietnam)",
                 "Registration opens: 10 Jan 2027, 08:00 (Vietnam)",
                 "Registration closes: 11 Jan 2027, 18:00 (Vietnam)",
                 "Scheduled start: 16 Jan 2027, 09:00", "Scheduled end: 16 Jan 2027, 11:00"):
        expect(panel.get_by_text(text, exact=True)).to_be_visible()
    expect(page.locator(".month-label")).to_have_text(month)
    expect(page.locator(".selected-date")).to_have_text(selected_date)
    expect(page.locator(".search-query input")).to_have_value("report")
    expect(page.get_by_role("combobox", name="Course", exact=True)).to_have_value("OTHER")
    expect(page.get_by_role("combobox", name="Sort", exact=True)).to_have_value("Title A–Z")
    expect(page.get_by_label("Deadline from")).to_have_value("2027-01-01")
    expect(page.get_by_label("Deadline through")).to_have_value("2027-01-31")

    def check_source(url):
        expect(panel.get_by_role("link", name="Open official source")).to_have_attribute("href", url)
        with page.expect_popup() as opened:
            panel.get_by_role("link", name="Open official source").click()
        destination = opened.value
        destination.wait_for_load_state()
        assert destination.url == url
        expect(destination.get_by_text("Controlled fictional source")).to_be_visible()
        destination.close()

    check_source("https://example.invalid/public/4")
    page.screenshot(path=str(tmp_path / "off-month-details.png"), full_page=True)
    close_details(page)
    previous_query_id = page.locator(".search-query input").get_attribute("id")
    page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
    expect(page.locator(".search-query input")).not_to_have_attribute("id", previous_query_id)
    page.locator(".search-query input").wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.locator(".search-query input").press("Enter")
    page.locator(f'[data-search-key="{NOTICE}"]').click()
    expect(panel.locator(".detail-title")).to_have_text("Campus notice")
    expect(calendar_panel).to_have_count(1)
    expect(panel.get_by_text("Training points not provided", exact=True)).to_be_visible()
    expect(panel.get_by_text("Date not provided", exact=True)).to_be_visible()
    assert "Scheduled" not in panel.inner_text()
    assert "Deadline:" not in panel.inner_text()
    check_source("https://example.invalid/public/3")
    close_details(page)
    for key, title, points, url in (
        (PUBLIC, "Zulu drive", 4, "https://example.invalid/public/1"),
        (PERSONAL, "Beta drive", 5, "https://example.invalid/personal/1"),
    ):
        page.locator(f'[data-search-key="{key}"]').click()
        expect(panel.locator(".detail-title")).to_have_text(title)
        expect(panel.get_by_text(f"{points} training points", exact=True)).to_be_visible()
        check_source(url)
        close_details(page)
    submit(page, "weekly")
    page.locator(f'[data-search-key="{WEEKLY}"]').click()
    badge=panel.locator('.type-badge')
    row_badge=page.locator(f'[data-search-key="{WEEKLY}"] .type-badge')
    expect(badge).to_have_text('Class')
    assert badge_style(badge)==badge_style(row_badge)
    expect(panel.get_by_text("Scheduled start: Every Monday, 08:00", exact=True)).to_be_visible()
    expect(panel.get_by_text("Scheduled end: Every Monday, 10:00", exact=True)).to_be_visible()
    expect(panel.get_by_text("Date not provided", exact=True)).to_be_visible()
    close_details(page)
    close_search(page)
    old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
    page.get_by_role("button", name="Agenda", exact=True).click()
    expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
    page.wait_for_timeout(200)
    open_search(page)
    close_search(page)
    page.locator(".agenda-item").filter(has_text="Weekly class").filter(has_text="08:00–10:00").first.click()
    page.wait_for_timeout(200)
    open_search(page)
    expect(calendar_panel.get_by_text("Scheduled start: 26 Oct 2026, 08:00 (Vietnam)", exact=True)).to_be_visible()
    assert "Every Monday" not in calendar_panel.inner_text()
    close_search(page)
    old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
    page.get_by_role("button", name="Calendar", exact=True).click()
    expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
    page.wait_for_timeout(200)
    open_search(page)
    expect(page.locator(".month-grid")).to_be_visible()
    page.locator(f'[data-search-key="{WEEKLY}"]').click()
    close_details(page)
    close_search(page)
    page.locator(".event-pill").filter(has_text="Weekly class").first.click()
    page.wait_for_timeout(200)
    open_search(page)
    expect(calendar_panel.get_by_text("Scheduled start: 26 Oct 2026, 08:00 (Vietnam)", exact=True)).to_be_visible()
    assert page.request.get(ui_server + "/test-state").json()["reads"] == before

    submit(page, "off-month")
    page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
    page.request.post(ui_server + "/fixture/change")
    page.request.post(ui_server + "/refresh")
    expect(panel.locator(".detail-title")).to_have_text("Off-month revised")
    expect(panel.get_by_text("Current facts", exact=True)).to_be_visible()
    check_source("https://example.invalid/revised")
    page.request.post(ui_server + "/fixture/remove")
    page.request.post(ui_server + "/refresh")
    expect(page.locator(".search-detail-dialog .task-detail")).to_have_count(0)
    expect(page.locator(".search-detail-dialog .source-link")).to_have_count(0)
    expect(page.locator(".search-detail-dialog")).not_to_be_visible()
    submit(page, "")
    page.locator(f'[data-search-key="{NOTICE}"]').click()
    page.request.post(ui_server + "/fixture/disable")
    page.request.post(ui_server + "/refresh")
    expect(page.locator(".search-detail-dialog .task-detail")).to_have_count(0)
    expect(page.locator(".search-detail-dialog .source-link")).to_have_count(0)
    submit(page, "")
    assert_keys(page, [PERSONAL, WEEKLY])
    page.screenshot(path=str(tmp_path / "details-cleared.png"), full_page=True)


@pytest.mark.parametrize("transition", ["account", "logout", "expiry"])
def test_stale_browser_selection_clears_private_panel(page, ui_server, transition):
    old_session = page.locator('.loaded-search').get_attribute('data-search-session')
    old_trigger = page.get_by_role('button', name='Search tasks', exact=True).get_attribute('id')
    page.locator(f'[data-search-key="{PERSONAL}"]').click()
    expect(page.locator(".search-detail-dialog .detail-title")).to_have_text("Beta drive")
    reads = page.request.get(ui_server + "/test-state").json()["reads"]
    stale = page.locator(f'[data-search-key="{PERSONAL}"]').element_handle()
    page.request.post(ui_server + "/session/" + transition)
    expect(page.locator(".search-detail-dialog")).not_to_be_visible()
    expect(page.locator(".search-detail-dialog .source-link")).to_have_count(0)
    stale.evaluate("element => element.click()")
    expect(page.locator(".search-detail-dialog .task-detail")).to_have_count(0)
    expect(page.locator(".search-detail-dialog .source-link")).to_have_count(0)
    assert page.request.get(ui_server + "/test-state").json()["reads"] == reads
    if transition == "account":
        expect(page.get_by_role('button', name='Search tasks', exact=True)).not_to_have_attribute('data-search-session', old_session)
        expect(page.get_by_role('button', name='Search tasks', exact=True)).not_to_have_attribute('id', old_trigger)
        expect(page.locator('.task-search-popover')).not_to_be_visible()
        submit(page, "")
        page.locator(f'[data-search-key="{PERSONAL}"]').click()
        expect(page.locator(".search-detail-dialog .detail-title")).to_have_text("Other account task")
        expect(page.locator(".source-link")).to_have_attribute("href", "https://example.invalid/other")


def test_dialog_visibility_keyboard_focus_and_scroll_preservation(page, ui_server, tmp_path):
    width,height=390,844
    page.set_viewport_size({"width": width, "height": height})
    bounds=page.locator('.task-search-popover').bounding_box()
    assert bounds['x'] >= 0 and bounds['x'] + bounds['width'] <= width + 1
    assert bounds['y'] >= 0 and bounds['y'] + bounds['height'] <= height + 1
    page.request.post(ui_server + "/fixture/long")
    old_list_id = page.locator(".search-results").get_attribute("id")
    close_search(page)
    page.get_by_role("button", name="Run personal crawl", exact=True).click()
    expect(page.get_by_text(re.compile("Mock personal crawl complete"))).to_be_visible()
    page.wait_for_timeout(200)
    open_search(page)
    expect(page.locator(".search-results")).not_to_have_attribute("id", old_list_id)
    expect(page.get_by_text("6 tasks · Soonest deadline", exact=True)).to_be_visible()
    submit(page, "shared topic")
    choose(page, "Sort", "Title A–Z")
    assert_keys(page, [SEVEN, PERSONAL, NOTICE, OFF_MONTH, WEEKLY, PUBLIC])
    month = page.locator(".month-label").inner_text()
    selected_date = page.locator(".selected-date").inner_text()
    reads = page.request.get(ui_server + "/test-state").json()["reads"]
    result = page.locator(f'[data-search-key="{OFF_MONTH}"]')
    dialog = page.locator(".search-detail-dialog")
    list_id = page.locator(".search-results").get_attribute("id")
    result_id = result.get_attribute("id")
    result.evaluate("""element => {
        const capture = event => {
            if (event.type === 'keydown' && event.key !== 'Enter' && event.key !== ' ') return;
            window.activationScroll = {page: scrollY,
                list: element.closest('.search-results').scrollTop,
                menu: element.closest('.task-search-popover').scrollTop};
        };
        element.addEventListener('pointerdown', capture, true);
        element.addEventListener('keydown', capture, true);
    }""")
    for keyboard in (False, True):
        result.evaluate("element => element.scrollIntoView({block: 'center'})")
        result.evaluate("element => element.focus({preventScroll: true})")
        before = page.evaluate("({page: scrollY, list: document.querySelector('.search-results').scrollTop, menu: document.querySelector('.task-search-popover').scrollTop})")
        assert before["page"] >= 0
        assert before["list"] > 0
        if keyboard:
            result.press("Enter")
        else:
            result.click()
        before = page.evaluate("window.activationScroll")
        assert before["list"] > 0
        expect(dialog).to_be_visible()
        expect(dialog.get_by_role("heading", name="Task details")).to_be_visible()
        expect(dialog.locator(".detail-title")).to_have_text("Off-month report")
        expect(dialog.locator(".detail-title")).to_be_in_viewport()
        expect(page.locator(".task-panel .task-detail")).to_have_count(1)
        assert dialog.bounding_box()["width"] <= width
        assert dialog.bounding_box()["height"] <= height
        content = dialog.locator(".search-detail-content")
        assert content.evaluate("element => element.scrollHeight > element.clientHeight")
        content.evaluate("element => element.scrollTop = element.scrollHeight")
        expect(dialog.get_by_role("link", name="Open official source")).to_be_in_viewport()
        expect(dialog.get_by_role("button", name="Close", exact=True)).to_be_in_viewport()
        page.screenshot(path=str(tmp_path / f"search-dialog-{width}.png"), animations="disabled")
        if keyboard:
            page.keyboard.press("Escape")
            expect(dialog).not_to_be_visible()
        else:
            close_details(page)
        expect(result).to_be_focused()
        expect(result).to_have_attribute('data-detail-restored', 'true')
        after = page.evaluate("({page: scrollY, list: document.querySelector('.search-results').scrollTop, menu: document.querySelector('.task-search-popover').scrollTop})")
        assert abs(after["page"] - before["page"]) <= 1
        assert abs(after["list"] - before["list"]) <= 1, (keyboard, before, after)
        assert abs(after["menu"] - before["menu"]) <= 1
        assert page.locator(".search-results").get_attribute("id") == list_id
        assert result.get_attribute("id") == result_id
        expect(page.locator(".search-query input")).to_have_value("shared topic")
        expect(page.get_by_role("combobox", name="Sort", exact=True)).to_have_value("Title A–Z")
        expect(page.get_by_role("combobox", name="Course", exact=True)).to_have_value("")
        expect(page.get_by_label("Deadline from")).to_have_value("")
        expect(page.get_by_label("Deadline through")).to_have_value("")
        expect(page.locator(".filter-button.active")).to_have_text("All")
        expect(page.locator(".month-label")).to_have_text(month)
        expect(page.locator(".selected-date")).to_have_text(selected_date)
        assert_keys(page, [SEVEN, PERSONAL, NOTICE, OFF_MONTH, WEEKLY, PUBLIC])
        assert page.request.get(ui_server + "/test-state").json()["reads"] == reads
