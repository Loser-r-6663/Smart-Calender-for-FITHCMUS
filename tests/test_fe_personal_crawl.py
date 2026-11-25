from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from types import ModuleType

from DataProcessor.Crawler.MoodleCrawler import MoodleCrawler
from DataProcessor.Crawler.PortalCrawler import PortalCrawler
from DataProcessor.Standardization.User import User
from client.core.personal_crawl import capture_moodle_session, run_personal_crawl


def test_personal_crawl_uses_and_updates_the_current_users_session(
    monkeypatch,
) -> None:
    crawlers_used = []

    class FakeCrawler:
        def __init__(self) -> None:
            self.state = {"cookies": [{"name": "session"}]}
            self.used_own_state_loader = False
            crawlers_used.append(self)

        def fetch_data(self):
            assert self.get_state() == self.state
            return []

        def get_state(self):
            self.used_own_state_loader = True
            return self.state

    class FakeTaskCreator:
        def __init__(self, user) -> None:
            self.portal = FakeCrawler()

        def crawlers(self, user):
            return {"Portal": self.portal, "Moodle": FakeCrawler()}

        def parse_tasks(self, raw_tasks):
            return []

    class FakeUserTaskRepository:
        def __init__(self, **kwargs) -> None:
            assert kwargs["user_id"] == "user-123"
            assert kwargs["access_token"] == "access-token"

        def get_tasks(self, limit=100):
            return []

        def delete_tasks(self, tasks):
            raise AssertionError("No tasks should be deleted")

        def save_tasks(self, tasks):
            raise AssertionError("No tasks should be saved")

    updated_users = []

    class FakeUserRepository:
        def __init__(self, **kwargs) -> None:
            assert kwargs["access_token"] == "access-token"

        def update_user(self, user):
            updated_users.append(user)

    task_creator_module = ModuleType("DataProcessor.TaskCreator")
    task_creator_module.TaskCreator = FakeTaskCreator
    monkeypatch.setitem(sys.modules, "DataProcessor.TaskCreator", task_creator_module)
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository",
        FakeUserTaskRepository,
    )
    monkeypatch.setattr(
        "Database.Repository.user_repository.UserRepository",
        FakeUserRepository,
    )

    user = User(
        id="user-123",
        username="student@example.com",
        portal_username="23123456",
        portal_password="secret",
    )

    result = run_personal_crawl(user, "access-token", {"Portal"})

    assert tuple(result) == (0, 0)
    assert result.failed_sources == ()
    assert user.portal_status is True
    assert user.portal_session == '{"cookies": [{"name": "session"}]}'
    assert crawlers_used[0].used_own_state_loader is True
    assert updated_users == [user]


def test_capture_moodle_session_returns_state_from_interactive_auth(
    monkeypatch,
) -> None:
    class FakeMoodleCrawler:
        def __init__(self, user) -> None:
            assert user.id == "user-123"
            self.state = None
            self.crawler = None

        @contextmanager
        def load_engine(self):
            yield "playwright"

        def authenticate(self):
            assert self.crawler == "playwright"
            self.state = {"cookies": [{"name": "moodle-session"}]}

    monkeypatch.setattr(
        "DataProcessor.Crawler.MoodleCrawler.MoodleCrawler",
        FakeMoodleCrawler,
    )
    user = User(id="user-123", username="student@example.com")

    session = capture_moodle_session(user)

    assert json.loads(session) == {
        "cookies": [{"name": "moodle-session"}],
    }


def test_portal_login_captures_session_when_none_existed() -> None:
    class FakeLocator:
        def fill(self, value) -> None:
            pass

        def click(self) -> None:
            pass

    class FakePage:
        def __init__(self, login_url: str) -> None:
            self.url = login_url + "&extra=1"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator()

        def wait_for_url(self, url: str, timeout: int) -> None:
            assert timeout == 120_000
            self.url = url

    class FakeContext:
        def storage_state(self) -> dict:
            return {"cookies": [{"name": "portal-session"}]}

    class FakeBrowser:
        closed = False

        def close(self) -> None:
            self.closed = True

    user = User(
        id="user-123",
        username="student@example.com",
        portal_username="23123456",
        portal_password="portal-password",
    )
    crawler = PortalCrawler(user)
    page = FakePage(crawler.login_url)
    browser = FakeBrowser()
    crawler.launch_engine = lambda url, settings: (page, FakeContext(), browser)

    crawler.login({"headless": False, "storage_state": None})

    assert crawler.state == {"cookies": [{"name": "portal-session"}]}
    assert browser.closed is True


def test_moodle_login_captures_session_state() -> None:
    class FakePage:
        def __init__(self, home_url: str) -> None:
            self.url = home_url

        def wait_for_url(self, url: str, timeout: int) -> None:
            assert timeout == 300_000
            self.url = url

        def wait_for_load_state(self, state: str) -> None:
            assert state == "networkidle"

    class FakeContext:
        def storage_state(self) -> dict:
            return {"cookies": [{"name": "moodle-session"}]}

    class FakeBrowser:
        closed = False

        def close(self) -> None:
            self.closed = True

    crawler = MoodleCrawler(User(id="user-123", username="student@example.com"))
    browser = FakeBrowser()
    crawler.launch_engine = lambda url, settings: (
        FakePage(crawler.home_url),
        FakeContext(),
        browser,
    )

    crawler.login({"headless": False, "storage_state": None})

    assert crawler.state == {"cookies": [{"name": "moodle-session"}]}
    assert browser.closed is True
