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


def test_ui_personal_crawl_keeps_expired_remote_history_and_can_add_new_tasks(monkeypatch):
    from test_search_records import task
    from unittest.mock import Mock
    from client.core.personal_crawl import run_personal_crawl

    retained = task(type='assignment',title='Historical coursework',deadline='2000-01-01T09:00:00+07:00')
    discovered = task(id='22222222-2222-4222-8222-222222222222',title='Old volunteer notice newly discovered',
                      deadline='2000-02-01T09:00:00+07:00')
    saved = []
    class Crawler:
        state = {'cookies':[]}
        def fetch_data(self): return []
    class Creator:
        def __init__(self,user): pass
        def crawlers(self,user): return {'Portal':Crawler()}
        def parse_tasks(self,raw): return [discovered]
    class Repository:
        def __init__(self,**kwargs):
            assert kwargs['user_id'] == 'owner'
            assert kwargs['access_token'] == 'fictional-token'
        def get_tasks(self,limit): return [retained]
        def save_tasks(self,items): saved.extend(items)
        def delete_tasks(self,*args): raise AssertionError('UI deleted tasks')
        def pop_tasks(self,*args): raise AssertionError('UI consumed tasks')
    creator_module = ModuleType('DataProcessor.TaskCreator')
    creator_module.TaskCreator = Creator
    monkeypatch.setitem(sys.modules,'DataProcessor.TaskCreator',creator_module)
    monkeypatch.setattr('Database.Repository.user_task_repository.UserTaskRepository',Repository)
    monkeypatch.setattr('Database.Repository.user_repository.UserRepository.update_user',Mock())
    monkeypatch.setattr('DataProcessor.Validator.Validator.filter_expired_tasks',Mock(side_effect=AssertionError('UI invoked expiry cleanup')))
    monkeypatch.setattr('Scheduler.scheduler.BranchAndBoundScheduler.schedule',Mock(side_effect=AssertionError('UI scheduled tasks')))
    user = User(id='owner',portal_username='fictional',portal_password='fictional',portal_session='{}')
    assert run_personal_crawl(user,'fictional-token',{'Portal'}) == (1,2)
    assert saved == [discovered]
