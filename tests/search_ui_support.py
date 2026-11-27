"""Shared offline NiceGUI harness for Search and FE regression journeys."""

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


@contextmanager
def serve_ui(directory, app_code=APP, tasks=None, module=None):
    fixture = directory / "tasks.json"
    fixture.write_text(json.dumps(fictional_tasks() if tasks is None else tasks, ensure_ascii=False), encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {**os.environ, "SEARCH_UI_FIXTURE": str(fixture), "SEARCH_UI_PORT": str(port),
           "PYTHON_DOTENV_DISABLED": "1", "LOCAL_TASK_DB_DIR": str(directory / "owner-stores")}
    env.pop("PYTEST_CURRENT_TEST", None)
    log = (directory / "server.log").open("w", encoding="utf-8")
    if module:
        env["CLIENT_PORT"] = str(port)
    command = [sys.executable, "-B", "-X", "utf8"] + (["-m", module] if module else ["-c", app_code])
    process = subprocess.Popen(command,
                               cwd=Path(__file__).resolve().parents[1], env=env,
                               stdout=log, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(150):
            if process.poll() is not None:
                raise RuntimeError((directory / "server.log").read_text(encoding="utf-8"))
            try:
                with urlopen(url + ("/login" if module else "/test-state"), timeout=1):
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
        page.locator(".search-query input").wait_for(state="visible")
        page.wait_for_function("window.did_handshake === true")
        page.locator(".search-query input").press("Enter")
        expect(page.locator(".search-query input")).to_be_visible()
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
    if page.locator(".search-query input").is_visible():
        page.locator(".search-query input").focus()
        page.keyboard.press("Escape")
        expect(page.locator(".task-search-popover")).not_to_be_visible()


def open_search(page):
    page.get_by_role("button", name="Search tasks", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    if not page.locator(".search-query input").is_visible():
        page.get_by_role("button", name="Search tasks", exact=True).click()
    expect(page.locator(".search-query input")).to_be_visible()


def submit(page, text):
    open_search(page)
    page.locator(".search-query input").fill(text)
    page.locator(".search-query input").wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.locator(".search-query input").press("Enter")


def close_details(page):
    page.locator(".search-detail-dialog").get_by_role("button", name="Close", exact=True).click()
    expect(page.locator(".search-detail-dialog")).not_to_be_visible()


def badge_style(badge):
    return badge.evaluate('''element => {
        const style = getComputedStyle(element);
        return Object.fromEntries(['backgroundColor', 'color', 'fontSize',
            'fontWeight', 'lineHeight', 'padding', 'borderRadius'].map(key => [key, style[key]]));
    }''')


