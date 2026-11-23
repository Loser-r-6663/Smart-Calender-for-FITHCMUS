from __future__ import annotations

import sys
from types import ModuleType

from DataProcessor.Standardization.User import User
from client.core.personal_crawl import run_personal_crawl


def test_personal_crawl_uses_and_updates_the_current_users_session(
    monkeypatch,
) -> None:
    class FakeCrawler:
        def __init__(self) -> None:
            self.state = {"cookies": [{"name": "session"}]}

        def fetch_data(self):
            assert self.get_state() == self.state
            return []

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
        portal_session='{"cookies": []}',
    )

    result = run_personal_crawl(user, "access-token", {"Portal"})

    assert result == (0, 0)
    assert user.portal_status is True
    assert user.portal_session == '{"cookies": [{"name": "session"}]}'
    assert updated_users == [user]
