"""Browser checks of the real NiceGUI Search controls with fictional mock data."""

import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright, expect

PUBLIC = "public:11111111-1111-4111-8111-111111111111"
PERSONAL = "personal:11111111-1111-4111-8111-111111111111"
SEVEN = "public:22222222-2222-4222-8222-222222222222"
NOTICE = "public:33333333-3333-4333-8333-333333333333"
OFF_MONTH = "public:44444444-4444-4444-8444-444444444444"
WEEKLY = "personal:55555555-5555-4555-8555-555555555555"

APP = r"""
import json
import os
from dataclasses import asdict
from pathlib import Path
from nicegui import app, ui
from client.config import AppConfig
from client.core.mock_backend import MockBackend
from client.core.controller import ClientController
from client.core.models import ClientUser
from client.pages.calendar import register_calendar_page
from client.components.filters import SearchPanel
from client.core.backend import task_load
from DataProcessor.Standardization.ExtractedTask import ExtractedTask

class CountingBackend(MockBackend):
    reads = 0
    async def get_tasks(self, user):
        self.reads += 1
        return await super().get_tasks(user)

backend = CountingBackend(Path(os.environ["SEARCH_UI_FIXTURE"]))
baseline = backend.fixture_path.read_text(encoding="utf-8")
ui.add_css(Path("client/static/styles.css"), shared=True)
register_calendar_page(backend, AppConfig(mode="mock"))

@ui.page("/start")
def start():
    app.storage.user["user"] = asdict(ClientUser("demo-user", "student", True, True))
    ui.navigate.to("/calendar")

@app.get("/test-state")
def state():
    controllers = list(getattr(backend, "_controllers", ()))
    keys = [c.state.selected_search_key for c in controllers if c.state.selected_search_key]
    return {"reads": backend.reads, "selected": keys}

@app.post("/fixture/{mode}")
async def change_fixture(mode: str):
    path = backend.fixture_path
    if mode == "reset":
        path.write_text(baseline, encoding="utf-8")
        backend._disabled_sources.clear()
        return {"ok": True}
    tasks = json.loads(path.read_text(encoding="utf-8"))
    if mode == "change":
        for task in tasks:
            if task["title"] == "Off-month report":
                task.update(title="Off-month revised", description="Current facts",
                            source_url="https://example.invalid/revised")
    elif mode == "remove":
        tasks = [task for task in tasks if task["title"] != "Off-month revised"]
    elif mode == "disable":
        await backend.set_source_enabled(ClientUser("demo-user", "student"), "VNUHCMUS", False)
    elif mode == "long":
        for task in tasks:
            task["description"] = "shared topic " + task["description"]
            if task["title"] == "Off-month report":
                task["description"] += " Long fictional task details." * 200
    path.write_text(json.dumps(tasks), encoding="utf-8")
    return {"ok": True}

@app.post("/session/{mode}")
async def change_session(mode: str):
    for controller in list(getattr(backend, "_controllers", ())):
        if mode == "account":
            controller.set_user(ClientUser("other-user", "Other"))
            private = ExtractedTask(id="11111111-1111-4111-8111-111111111111",
                                    title="Other account task", type="announcement", source_platform="Moodle",
                                    source_url="https://example.invalid/other", updated_at="2026-11-23T09:00:00+07:00")
            controller.state.search_snapshot = task_load((("personal", [private]),), set()).snapshot
        else:
            controller.logout()
            controller.state.session_expired = mode == "expiry"
    return {"ok": True}

@app.post("/refresh")
async def refresh():
    for controller in list(getattr(backend, "_controllers", ())):
        await controller.load_month()
    return {"ok": True}

@ui.page("/feedback/{mode}")
def feedback(mode: str):
    controller = ClientController(backend, ClientUser("demo-user", "student"))
    controller.state.loading = mode == "loading"
    controller.state.session_expired = mode == "expired"
    controller.state.error = "Controlled failure" if mode == "failure" else None
    SearchPanel(controller).render(on_filter=lambda kind: None, on_view=lambda view: None)

ui.run(host="127.0.0.1", port=int(os.environ["SEARCH_UI_PORT"]), show=False, reload=False,
       storage_secret="fictional-ui-test-secret")
"""


def fictional_tasks():
    result = []
    for number, title, points, deadline, personal in (
        (1, "Zulu drive", 4, "2026-11-26T09:00:00+07:00", False),
        (1, "Beta drive", 5, "2026-11-25T09:00:00+07:00", True),
        (2, "Alpha drive", 7, "2026-11-27T09:00:00+07:00", False),
        (3, "Campus notice", None, None, False),
        (4, "Off-month report", None, "2027-01-15T09:00:00+07:00", False),
        (5, "Weekly class", None, None, True),
    ):
        digit = str(number)
        record = {
            "id": f"{digit * 8}-{digit * 4}-4{digit * 3}-8{digit * 3}-{digit * 12}",
            "title": title, "description": "thiện nguyện" if number < 4 else "Other material",
            "course": "CSC10004" if number < 4 else "OTHER",
            "training_points": points, "deadline": deadline,
            "type": "event" if points else "announcement",
            "source_platform": "Moodle" if personal else "VNUHCMUS",
            "source_url": f"https://example.invalid/{'personal' if personal else 'public'}/{number}",
            "updated_at": "2026-11-23T09:00:00+07:00",
        }
        if points:
            record.update(estimated_hours=2, training_point_category="Articles 3")
        if personal:
            record["user_id"] = "demo-user"
        if number == 5:
            record.update(type="class", start_time={"day": "T2", "time": "08:00:00"},
                          end_time={"day": "T2", "time": "10:00:00"})
        if number == 4:
            record.update(type="event", training_points=0, estimated_hours=2,
                          registration_start="2027-01-10T08:00:00+07:00",
                          registration_end="2027-01-11T18:00:00+07:00",
                          start_time={"date": "2027-01-16", "time": "09:00:00"},
                          end_time={"date": "2027-01-16", "time": "11:00:00"})
        result.append(record)
    return result


def test_result_dates_use_known_endpoints_without_inventing_occurrences():
    from academic_search import map_task
    from client.components.filters import record_date
    from test_search_records import task

    ended = map_task(task(end_time={"date": "2026-11-25", "time": "10:30:00"}), scope="public")
    weekly = map_task(task(start_time={"day": "T2", "time": "08:00:00"}), scope="personal")
    undated = map_task(task(), scope="public")
    assert record_date(ended) == "Ends 25 Nov 2026, 10:30"
    assert record_date(weekly) == "Date not provided · Every Monday, 08:00"
    assert weekly.start_time.date is None
    assert record_date(undated) == "Date not provided"


@pytest.mark.parametrize("url", ["", "javascript:example", "https://["])
def test_missing_or_unusable_source_does_not_hide_task_facts(monkeypatch, url):
    from unittest.mock import MagicMock
    from academic_search import map_task
    from client.components.task_panel import render_record_details
    from test_search_records import task

    ui = MagicMock()
    monkeypatch.setattr("client.components.task_panel.ui", ui)
    render_record_details(map_task(task(source_url=url), scope="public"))
    ui.label.assert_any_call("Sinh hoạt sinh viên")
    ui.link.assert_not_called()


@contextmanager
def serve_ui(directory, app_code=APP, tasks=None):
    fixture = directory / "tasks.json"
    fixture.write_text(json.dumps(fictional_tasks() if tasks is None else tasks, ensure_ascii=False), encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "SEARCH_UI_FIXTURE": str(fixture), "SEARCH_UI_PORT": str(port),
           "PYTHON_DOTENV_DISABLED": "1", "LOCAL_TASK_DB_DIR": str(directory / "owner-stores")}
    env.pop("PYTEST_CURRENT_TEST", None)
    log = (directory / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", app_code],
                               cwd=Path(__file__).resolve().parents[1], env=env,
                               stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if process.poll() is not None:
                raise RuntimeError((directory / "server.log").read_text(encoding="utf-8"))
            try:
                with urlopen(url + "/test-state", timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Mock NiceGUI server did not become ready")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=15)
        log.close()


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory):
    with serve_ui(tmp_path_factory.mktemp("search-ui")) as url:
        yield url


@pytest.fixture
def page(ui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(ui_server)
                      else route.fulfill(body="<html><body>Controlled fictional source</body></html>")
                      if route.request.url.startswith("https://example.invalid/") else route.abort())
        page.request.post(ui_server + "/fixture/reset")
        page.goto(ui_server + "/start")
        open_search(page)
        page.get_by_label("Query", exact=True).wait_for(state="visible")
        page.wait_for_function("window.did_handshake === true")
        page.get_by_label("Query", exact=True).press("Enter")
        expect(page.get_by_label("Query")).to_be_visible()
        submit(page, "")
        expect(page.locator(".search-result")).to_have_count(6)
        yield page
        browser.close()


def ordered_keys(page):
    return page.locator(".search-result").evaluate_all(
        "elements => elements.map(element => element.getAttribute('data-search-key'))")


def assert_keys(page, expected):
    expect(page.locator(".search-result")).to_have_count(len(expected))
    deadline = time.monotonic() + 5
    while ordered_keys(page) != expected and time.monotonic() < deadline:
        page.wait_for_timeout(50)
    assert ordered_keys(page) == expected


def choose(page, label, option):
    open_search(page)
    box = page.get_by_role("combobox", name=label, exact=True)
    box.locator("xpath=ancestor::label").click()
    page.locator(".q-menu:not(.task-search-popover)").get_by_text(option, exact=True).click(timeout=5000)


def close_search(page):
    if page.get_by_label("Query", exact=True).is_visible():
        page.get_by_label("Query", exact=True).focus()
        page.keyboard.press("Escape")
        expect(page.locator(".task-search-popover")).not_to_be_visible()


def open_search(page):
    page.get_by_role("button", name="Search tasks", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    if not page.get_by_label("Query", exact=True).is_visible():
        page.get_by_role("button", name="Search tasks", exact=True).click()
    expect(page.get_by_label("Query", exact=True)).to_be_visible()


def submit(page, text):
    open_search(page)
    page.get_by_label("Query", exact=True).fill(text)
    page.get_by_label("Query", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.get_by_label("Query", exact=True).press("Enter")


def close_details(page):
    page.locator(".search-detail-dialog").get_by_role("button", name="Close", exact=True).click()
    expect(page.locator(".search-detail-dialog")).not_to_be_visible()


def test_real_search_controls_and_ordering(page, ui_server, tmp_path):
    before = page.request.get(ui_server + "/test-state").json()["reads"]
    submit(page, "thiện nguyện")
    assert_keys(page, [PERSONAL, PUBLIC, SEVEN, NOTICE])
    submit(page, "thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    expect(page.get_by_text("Exactly 5 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện từ 5 điểm")
    assert_keys(page, [PERSONAL, SEVEN])
    expect(page.get_by_text("At least 5 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện ít hơn 5 điểm")
    assert_keys(page, [PUBLIC])
    expect(page.get_by_text("At most 4 points", exact=True)).not_to_be_visible()
    submit(page, "bé hơn 5 điểm")
    assert_keys(page, [PUBLIC, OFF_MONTH])
    expect(page.get_by_text("At most 4 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện bé hơn 5 điểm")
    assert_keys(page, [PUBLIC])
    expect(page.get_by_text("At most 4 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện 5 điểm trở xuống")
    assert_keys(page, [PERSONAL, PUBLIC])
    expect(page.get_by_text("At most 5 points", exact=True)).not_to_be_visible()
    submit(page, "nhiều hơn 5 điểm")
    assert_keys(page, [SEVEN])
    expect(page.get_by_text("At least 6 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện nhiều hơn 5 điểm")
    assert_keys(page, [SEVEN])
    expect(page.get_by_text("At least 6 points", exact=True)).not_to_be_visible()
    submit(page, "thiện nguyện từ 5 điểm")
    assert_keys(page, [PERSONAL, SEVEN])
    choose(page, "Type", "Notices")
    expect(page.get_by_label("Query")).to_have_value("thiện nguyện từ 5 điểm")
    expect(page.get_by_text("No matching tasks", exact=True)).to_be_visible()
    submit(page, "thiện nguyện")
    assert_keys(page, [NOTICE])
    choose(page, "Type", "All types")
    assert_keys(page, [PERSONAL, PUBLIC, SEVEN, NOTICE])
    page.get_by_role("combobox", name="Course", exact=True).locator("xpath=ancestor::label").click()
    expect(page.locator(".q-menu:not(.task-search-popover)").get_by_text("OTHER", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    for sort, expected in (
        ("Best match", [PERSONAL, PUBLIC, SEVEN, NOTICE]),
        ("Soonest deadline", [PERSONAL, PUBLIC, SEVEN, NOTICE]),
        ("Latest deadline", [SEVEN, PUBLIC, PERSONAL, NOTICE]),
        ("Title A–Z", [SEVEN, PERSONAL, NOTICE, PUBLIC]),
    ):
        choose(page, "Sort", sort)
        assert_keys(page, expected)
        expect(page.get_by_label("Query")).to_have_value("thiện nguyện")
    page.locator(f'[data-search-key="{PUBLIC}"]').click()
    expect(page.locator(f'[data-search-key="{PUBLIC}"]')).to_have_attribute("aria-pressed", "true")
    state = page.request.get(ui_server + "/test-state").json()
    assert ["public", PUBLIC.split(":")[1]] in state["selected"]
    close_details(page)
    page.locator(f'[data-search-key="{PERSONAL}"]').click()
    expect(page.locator(f'[data-search-key="{PERSONAL}"]')).to_have_attribute("aria-pressed", "true")
    state = page.request.get(ui_server + "/test-state").json()
    assert ["personal", PERSONAL.split(":")[1]] in state["selected"]
    close_details(page)
    choose(page, "Course", "CSC10004")
    page.get_by_label("Deadline from").fill("2026-11-28")
    page.get_by_label("Deadline through").fill("2026-11-25")
    expect(page.get_by_role("alert")).to_have_text("Reversed deadline range")
    expect(page.get_by_label("Query")).to_have_value("thiện nguyện")
    page.get_by_label("Deadline from").fill("2026-11-25")
    page.get_by_label("Deadline through").fill("2026-11-27")
    assert_keys(page, [SEVEN, PERSONAL, PUBLIC])
    for sort, expected in (
        ("Best match", [PERSONAL, PUBLIC, SEVEN]),
        ("Soonest deadline", [PERSONAL, PUBLIC, SEVEN]),
        ("Latest deadline", [SEVEN, PUBLIC, PERSONAL]),
        ("Title A–Z", [SEVEN, PERSONAL, PUBLIC]),
    ):
        choose(page, "Sort", sort)
        assert_keys(page, expected)
        expect(page.get_by_label("Query")).to_have_value("thiện nguyện")
        expect(page.get_by_role("combobox", name="Course", exact=True)).to_have_value("CSC10004")
        expect(page.get_by_label("Deadline from")).to_have_value("2026-11-25")
        expect(page.get_by_label("Deadline through")).to_have_value("2026-11-27")
    page.get_by_label("Query", exact=True).fill("unrelated words")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_text("No matching tasks", exact=True)).to_be_visible()
    previous_query_id = page.get_by_label("Query", exact=True).get_attribute("id")
    page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
    expect(page.get_by_label("Query", exact=True)).not_to_have_attribute("id", previous_query_id)
    page.get_by_label("Query", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.get_by_label("Query", exact=True).press("Enter")
    assert_keys(page, [PERSONAL, PUBLIC, SEVEN, OFF_MONTH, WEEKLY, NOTICE])
    expect(page.get_by_label("Query")).to_have_value("")
    expect(page.get_by_label("Deadline from")).to_have_value("")
    expect(page.get_by_label("Deadline through")).to_have_value("")
    expect(page.get_by_role("combobox", name="Course", exact=True)).to_have_value("")
    expect(page.get_by_role("combobox", name="Sort", exact=True)).to_have_value("Default")
    expect(page.get_by_text("6 tasks · Soonest deadline", exact=True)).to_be_visible()
    expect(page.get_by_text("Date not provided · Every Monday, 08:00", exact=False)).to_be_visible()
    for button in page.locator(".search-result").all():
        bounds = button.bounding_box()
        meta = button.locator(".search-result-meta").bounding_box()
        assert meta["y"] + meta["height"] <= bounds["y"] + bounds["height"]
    page.screenshot(path=str(tmp_path / "search-desktop.png"), full_page=True)
    assert page.request.get(ui_server + "/test-state").json()["reads"] == before


@pytest.mark.parametrize("query,selected,bounds", [
    ("ít hơn 5 điểm", {}, (None,4)),
    ("tối đa 5 ĐRL", {}, (None,5)),
    ("hơn 5 điểm", {}, (6,None)),
    ("ít hơn 5 điểm", {"min_training_points":4}, (4,4)),
    ("5 điểm trở xuống", {"max_training_points":4}, (None,4)),
    ("hơn 4 điểm", {"max_training_points":6}, (5,6)),
    ("ít nhất 5 điểm", {"min_training_points":7}, (7,None)),
])
def test_effective_point_bounds_remain_available(query, selected, bounds):
    from academic_search import search_records
    result = search_records((), query, filters=selected)
    assert (result.effective_filters.get('min_training_points'),
            result.effective_filters.get('max_training_points')) == bounds


def test_narrow_layout_navigation_and_feedback(page, ui_server, tmp_path):
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("button", name="Search", exact=True)).to_be_visible()
    submit(page, "thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    page.locator(".loaded-search").scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / "search-narrow.png"), full_page=True)
    close_search(page)
    old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
    page.get_by_role("button", name="Agenda", exact=True).click()
    expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
    page.wait_for_timeout(200)
    open_search(page)
    expect(page.get_by_role("button", name="Agenda", exact=True)).to_have_class(re.compile(r"\bactive\b"))
    expect(page.get_by_label("Query")).to_have_value("thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    close_search(page)
    old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
    page.get_by_role("button", name="Calendar", exact=True).click()
    expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
    page.wait_for_timeout(200)
    open_search(page)
    expect(page.get_by_role("button", name="Calendar", exact=True)).to_have_class(re.compile(r"\bactive\b"))
    assert_keys(page, [PERSONAL])
    panel = page.locator(".loaded-search").bounding_box()
    assert panel["width"] <= 390
    for mode, label in (
        ("loading", "Loading tasks…"),
        ("expired", "Session expired. Sign in again."),
        ("failure", "Could not load tasks. Try refreshing."),
    ):
        page.goto(ui_server + "/feedback/" + mode)
        open_search(page)
        expect(page.get_by_text(label, exact=True)).to_be_visible()
        expect(page.locator(".search-result")).to_have_count(0)


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
    expect(page.get_by_label("Query")).to_have_value("report")
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
    previous_query_id = page.get_by_label("Query", exact=True).get_attribute("id")
    page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
    expect(page.get_by_label("Query", exact=True)).not_to_have_attribute("id", previous_query_id)
    page.get_by_label("Query", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.get_by_label("Query", exact=True).press("Enter")
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


@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844)])
def test_dialog_visibility_keyboard_focus_and_scroll_preservation(page, ui_server, tmp_path, width, height):
    page.set_viewport_size({"width": width, "height": height})
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
        expect(page.get_by_label("Query")).to_have_value("shared topic")
        expect(page.get_by_role("combobox", name="Sort", exact=True)).to_have_value("Title A–Z")
        expect(page.get_by_role("combobox", name="Course", exact=True)).to_have_value("")
        expect(page.get_by_label("Deadline from")).to_have_value("")
        expect(page.get_by_label("Deadline through")).to_have_value("")
        expect(page.locator(".filter-button.active")).to_have_text("All")
        expect(page.locator(".month-label")).to_have_text(month)
        expect(page.locator(".selected-date")).to_have_text(selected_date)
        assert_keys(page, [SEVEN, PERSONAL, NOTICE, OFF_MONTH, WEEKLY, PUBLIC])
        assert page.request.get(ui_server + "/test-state").json()["reads"] == reads


def test_personal_and_assignments_controls_open_original_scoped_details(tmp_path):
    tasks = fictional_tasks()
    tasks[1].update(type="assignment", training_points=None, training_point_category=None)
    custom = {**tasks[3], "id":"77777777-7777-4777-8777-777777777777", "user_id":"demo-user",
        "title":"Owner custom appointment", "description":"Private planning", "type":"personal",
        "source_platform":"Custom", "source_url":"https://example.invalid/custom"}
    tasks.append(custom)
    custom_key = "personal:" + custom["id"]
    with serve_ui(tmp_path, tasks=tasks) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width":1280,"height":900})
            page.route("**/*",lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page.goto(url+"/start")
            open_search(page)
            page.get_by_label("Query", exact=True).wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.get_by_label("Query", exact=True).press("Enter")
            expect(page.locator(".search-result")).to_have_count(7)
            before = page.request.get(url+"/test-state").json()["reads"]
            choose(page,"Type","Personal")
            submit(page,"Owner custom")
            assert_keys(page,[custom_key])
            page.locator(f'[data-search-key="{custom_key}"]').click()
            expect(page.locator(".search-detail-dialog .detail-title")).to_have_text(custom["title"])
            expect(page.locator(".search-detail-dialog .type-badge")).to_have_text("Personal")
            expect(page.locator(".search-detail-dialog .detail-scope")).to_have_text("Personal")
            expect(page.locator(".search-detail-dialog .source-link")).to_have_attribute("href",custom["source_url"])
            close_details(page)
            previous_query_id = page.get_by_label("Query", exact=True).get_attribute("id")
            page.locator(".search-query-row").get_by_role("button",name="Clear",exact=True).click()
            expect(page.get_by_label("Query", exact=True)).not_to_have_attribute("id", previous_query_id)
            page.get_by_label("Query", exact=True).wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.get_by_label("Query", exact=True).press("Enter")
            expect(page.locator(".search-result")).to_have_count(7)
            choose(page,"Type","Assignments")
            submit(page,"Beta")
            assert_keys(page,[PERSONAL])
            page.locator(f'[data-search-key="{PERSONAL}"]').click()
            expect(page.locator(".search-detail-dialog .type-badge")).to_have_text("Assignment")
            expect(page.locator(".search-detail-dialog .detail-scope")).to_have_text("Personal")
            close_details(page)
            previous_query_id = page.get_by_label("Query", exact=True).get_attribute("id")
            page.locator(".search-query-row").get_by_role("button",name="Clear",exact=True).click()
            expect(page.get_by_label("Query", exact=True)).not_to_have_attribute("id", previous_query_id)
            page.get_by_label("Query", exact=True).wait_for(state="visible")
            page.wait_for_function("window.did_handshake === true")
            page.get_by_label("Query", exact=True).press("Enter")
            expect(page.locator(".search-result")).to_have_count(7)
            choose(page,"Type","Personal")
            assert_keys(page,[custom_key])
            page.locator(f'[data-search-key="{custom_key}"]').click()
            expect(page.locator(".search-detail-dialog")).to_be_visible()
            stale_custom = page.locator(f'[data-search-key="{custom_key}"]').element_handle()
            page.request.post(url+"/session/account")
            expect(page.locator(".search-detail-dialog")).not_to_be_visible()
            assert page.locator('.search-detail-dialog .source-link').count() == 0
            stale_custom.evaluate('element => element.click()')
            expect(page.locator(".search-detail-dialog")).not_to_be_visible()
            assert page.request.get(url+"/test-state").json()["reads"] == before
        finally:
            browser.close()
