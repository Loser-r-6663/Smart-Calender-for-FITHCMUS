"""Browser checks of the real NiceGUI Search controls with fictional mock data."""

import json
import os
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
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

class CountingBackend(MockBackend):
    reads = 0
    async def get_tasks(self, user):
        self.reads += 1
        return await super().get_tasks(user)

backend = CountingBackend(Path(os.environ["SEARCH_UI_FIXTURE"]))
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
            "source_url": "https://example.invalid/fixture",
            "updated_at": "2026-11-23T09:00:00+07:00",
        }
        if points:
            record.update(estimated_hours=2, training_point_category="Articles 3")
        if personal:
            record["user_id"] = "demo-user"
        if number == 5:
            record.update(type="class", start_time={"day": "T2", "time": "08:00:00"})
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


@pytest.fixture(scope="module")
def ui_server(tmp_path_factory):
    directory = tmp_path_factory.mktemp("search-ui")
    fixture = directory / "tasks.json"
    fixture.write_text(json.dumps(fictional_tasks(), ensure_ascii=False), encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "SEARCH_UI_FIXTURE": str(fixture), "SEARCH_UI_PORT": str(port),
           "PYTHON_DOTENV_DISABLED": "1"}
    env.pop("PYTEST_CURRENT_TEST", None)
    log = (directory / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-B", "-X", "utf8", "-c", APP],
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


@pytest.fixture
def page(ui_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(ui_server)
                   else route.abort())
        page.goto(ui_server + "/start")
        expect(page.get_by_label("Query")).to_be_visible()
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
    box = page.get_by_role("combobox", name=label, exact=True)
    box.locator("xpath=ancestor::label").click()
    page.locator(".q-menu").get_by_text(option, exact=True).click(timeout=5000)


def submit(page, text):
    page.get_by_label("Query", exact=True).fill(text)
    page.get_by_label("Query", exact=True).press("Enter")


def test_real_search_controls_and_ordering(page, ui_server, tmp_path):
    before = page.request.get(ui_server + "/test-state").json()["reads"]
    submit(page, "thiện nguyện")
    assert_keys(page, [PERSONAL, PUBLIC, SEVEN, NOTICE])
    submit(page, "thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    expect(page.get_by_text("Exactly 5 points", exact=True)).to_be_visible()
    submit(page, "thiện nguyện từ 5 điểm")
    assert_keys(page, [PERSONAL, SEVEN])
    expect(page.get_by_text("At least 5 points", exact=True)).to_be_visible()
    page.get_by_role("button", name="Notices", exact=True).click()
    expect(page.get_by_label("Query")).to_have_value("thiện nguyện từ 5 điểm")
    expect(page.get_by_text("No matching tasks", exact=True)).to_be_visible()
    submit(page, "thiện nguyện")
    assert_keys(page, [NOTICE])
    page.get_by_role("button", name="All", exact=True).click()
    assert_keys(page, [PERSONAL, PUBLIC, SEVEN, NOTICE])
    page.get_by_role("combobox", name="Course", exact=True).locator("xpath=ancestor::label").click()
    expect(page.locator(".q-menu").get_by_text("OTHER", exact=True)).to_be_visible()
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
    page.locator(f'[data-search-key="{PERSONAL}"]').click()
    expect(page.locator(f'[data-search-key="{PERSONAL}"]')).to_have_attribute("aria-pressed", "true")
    state = page.request.get(ui_server + "/test-state").json()
    assert ["personal", PERSONAL.split(":")[1]] in state["selected"]
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
    page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
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


def test_narrow_layout_navigation_and_feedback(page, ui_server, tmp_path):
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("button", name="Search", exact=True)).to_be_visible()
    submit(page, "thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    page.locator(".loaded-search").scroll_into_view_if_needed()
    page.screenshot(path=str(tmp_path / "search-narrow.png"), full_page=True)
    page.get_by_role("button", name="Agenda", exact=True).click()
    expect(page.get_by_role("button", name="Agenda", exact=True)).to_have_class(re.compile(r"\bactive\b"))
    expect(page.get_by_label("Query")).to_have_value("thiện nguyện 5 điểm")
    assert_keys(page, [PERSONAL])
    page.get_by_role("button", name="Calendar", exact=True).click()
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
        expect(page.get_by_text(label, exact=True)).to_be_visible()
        expect(page.locator(".search-result")).to_have_count(0)
