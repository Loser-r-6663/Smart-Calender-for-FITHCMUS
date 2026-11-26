from __future__ import annotations

import sys
import asyncio
import json
from contextlib import contextmanager
from types import ModuleType
from types import SimpleNamespace

import pytest

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

        def get_state(self):
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
        portal_session='{"cookies": []}',
    )

    result = run_personal_crawl(user, "access-token", {"Portal"})

    assert tuple(result) == (0, 0)
    assert result.failed_sources == ()
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
    assert tuple(run_personal_crawl(user,'fictional-token',{'Portal'})) == (1,2)
    assert saved == [discovered]


@pytest.fixture
def personal_crawl_environment(monkeypatch):
    from unittest.mock import Mock
    from DataProcessor.Crawler.PortalCrawler import PortalCrawler
    from DataProcessor.Crawler.MoodleCrawler import MoodleCrawler
    from DataProcessor.Standardization.RawTask import RawTask
    from DataProcessor.Standardization.ExtractedTask import ExtractedTask
    from DataProcessor.TaskCreator import TaskCreator
    import Database.task_sync

    owner = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    user = User(
        id=owner, username="fictional@example.invalid",
        portal_username="fictional-student", portal_password="PRIVATE-PASSWORD",
        portal_session=json.dumps({"cookies": [], "origins": [{"origin": "https://portal.invalid", "localStorage": []}]}),
        moodle_session=json.dumps({"cookies": [], "origins": [{"origin": "https://moodle.invalid", "localStorage": []}]}),
    )
    env = SimpleNamespace(user=user, saved=[], stored=[], created={}, launches=[], login_fields=[],
                          fail_fetch=set(), fail_parse=set(), reads=[], updates=[])
    monkeypatch.setenv("APP_ROLE", "SERVER")
    monkeypatch.setattr("DataProcessor.Crawler.PortalCrawler.APP_ROLE", "SERVER")
    monkeypatch.setattr("DataProcessor.Crawler.MoodleCrawler.APP_ROLE", "SERVER")

    @contextmanager
    def engine(self):
        yield object()

    def launch(self, url, settings=None):
        platform = "Portal" if isinstance(self, PortalCrawler) else "Moodle"
        env.launches.append((platform, self.user.id, self.state))
        saved_session = getattr(user, f"{platform.lower()}_session")
        if saved_session or settings is not None:
            assert self.state == (json.loads(saved_session) if saved_session else None)
        if platform in env.fail_fetch:
            raise AssertionError("PRIVATE-PAGE https://portal.invalid/?token=PRIVATE-TOKEN PRIVATE-PASSWORD")
        page = SimpleNamespace(url=self.home_url if saved_session else self.login_url,
                               wait_for_url=lambda *a, **kw: None,
                               wait_for_load_state=lambda *a, **kw: None,
                               locator=lambda selector: SimpleNamespace(
                                   fill=lambda value: env.login_fields.append(value), click=lambda: None))
        context = SimpleNamespace(storage_state=lambda **kw: self.state or {"cookies": [{"name": "fictional", "value": "PRIVATE-COOKIE"}]})
        return page, context, SimpleNamespace(close=lambda: None)

    def browse(self, page):
        platform = "Portal" if isinstance(self, PortalCrawler) else "Moodle"
        return [RawTask(title=f"New fictional {platform} task", type="class" if platform == "Portal" else "assignment",
                        course="CSC-FICTIONAL", link=f"https://{platform.lower()}.invalid/task")]

    for cls in (PortalCrawler, MoodleCrawler):
        monkeypatch.setattr(cls, "load_engine", engine)
        monkeypatch.setattr(cls, "launch_engine", launch)
        monkeypatch.setattr(cls, "browse_page", browse)

    def creator(user):
        instance = TaskCreator(user)
        crawlers = instance.crawlers(user)
        assert all(not hasattr(crawler, "state") for crawler in crawlers.values())
        env.created.update(crawlers)
        instance.crawlers = lambda user: crawlers
        return instance

    monkeypatch.setattr("DataProcessor.TaskCreator.TaskCreator", creator)

    def parse(raw):
        if raw.platform in env.fail_parse:
            raise ValueError("PRIVATE-TASK-CONTENT")
        return [ExtractedTask.from_raw_task(raw)]

    parser_module = ModuleType("DataProcessor.Parser.Parser")
    parser_module.Parser = SimpleNamespace(parse=parse)
    monkeypatch.setitem(sys.modules, "DataProcessor.Parser.Parser", parser_module)

    class Repository:
        def __init__(self, **kwargs):
            assert kwargs["user_id"] == owner
            assert kwargs["access_token"] == "PRIVATE-TOKEN"

        def get_tasks(self, limit=100):
            env.reads.append(limit)
            return list(env.stored)

        def save_tasks(self, tasks):
            assert all(task.user_id == owner for task in tasks)
            for task in tasks:
                task.id = ("11111111-1111-4111-8111-111111111111" if task.source_platform == "Portal"
                           else "22222222-2222-4222-8222-222222222222")
            env.saved.extend(tasks)
            env.stored.extend(tasks)

        def delete_tasks(self, *a, **kw):
            raise AssertionError("UI deleted tasks")

        def pop_tasks(self, *a, **kw):
            raise AssertionError("UI consumed tasks")

        def acknowledge_tasks(self, *a, **kw):
            raise AssertionError("UI acknowledged tasks")

    class UserRepository:
        def __init__(self, **kwargs):
            assert kwargs["access_token"] == "PRIVATE-TOKEN"

        def update_user(self, updated):
            assert updated.id == owner
            env.updates.append(updated)

    env.repository = Repository
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository", Repository)
    monkeypatch.setattr("Database.task_sync.UserTaskRepository", Repository)
    monkeypatch.setattr("Database.Repository.user_repository.UserRepository", UserRepository)
    monkeypatch.setattr("requests.delete", Mock(side_effect=AssertionError("UI deleted rows")))
    monkeypatch.setattr("DataProcessor.Validator.Validator.filter_expired_tasks", Mock(side_effect=AssertionError("UI expired rows")))
    monkeypatch.setattr("Scheduler.scheduler.BranchAndBoundScheduler.schedule", Mock(side_effect=AssertionError("UI scheduled tasks")))
    return env


@pytest.mark.parametrize("sources", [{"Portal"}, {"Moodle"}, {"Portal", "Moodle"}])
def test_fresh_crawlers_use_concrete_owner_session_loaders(personal_crawl_environment, sources):
    env = personal_crawl_environment
    result = run_personal_crawl(env.user, "PRIVATE-TOKEN", sources)
    assert tuple(result) == (len(sources), len(sources))
    assert result.failed_sources == ()
    assert {platform for platform, owner, state in env.launches} == sources
    assert {task.source_platform for task in env.saved} == sources
    assert all(task.user_id == env.user.id for task in env.saved)
    for platform in sources:
        assert "get_state" not in env.created[platform].__dict__
        assert env.created[platform].state == json.loads(getattr(env.user, f"{platform.lower()}_session"))


def test_portal_needs_no_llm_or_moodle_session(personal_crawl_environment, monkeypatch):
    env = personal_crawl_environment
    env.user.moodle_session = None
    monkeypatch.setitem(sys.modules, "DataProcessor.Parser.Parser", None)
    result = run_personal_crawl(env.user, "PRIVATE-TOKEN", {"Portal"})
    assert tuple(result) == (1, 1)
    assert result.failed_sources == ()
    assert {platform for platform, _, _ in env.launches} == {"Portal"}


def test_portal_can_start_from_saved_credentials_without_session(personal_crawl_environment, monkeypatch):
    env = personal_crawl_environment
    env.user.portal_session = None
    monkeypatch.setattr("DataProcessor.Crawler.PortalCrawler.APP_ROLE", None)
    result = run_personal_crawl(env.user, "PRIVATE-TOKEN", {"Portal"})
    assert tuple(result) == (1, 1)
    assert env.login_fields == [env.user.portal_username, env.user.portal_password]
    assert json.loads(env.user.portal_session)["cookies"][0]["name"] == "fictional"


@pytest.mark.parametrize("failure_stage", ["fetch", "parse"])
def test_portal_persists_despite_moodle_failure(personal_crawl_environment, failure_stage, caplog):
    env = personal_crawl_environment
    getattr(env, f"fail_{failure_stage}").add("Moodle")
    result = run_personal_crawl(env.user, "PRIVATE-TOKEN", {"Portal", "Moodle"})
    assert tuple(result) == (1, 1)
    assert result.failed_sources == ("Moodle",)
    assert [task.source_platform for task in env.saved] == ["Portal"]
    assert env.user.portal_status
    assert env.user.moodle_status == (failure_stage == "parse")
    assert f"source=Moodle stage={failure_stage} error=" in caplog.text
    assert "PRIVATE-" not in caplog.text


def test_all_sources_fail_with_safe_diagnostics(personal_crawl_environment, caplog, capsys):
    from client.core.personal_crawl import PersonalCrawlError

    env = personal_crawl_environment
    env.fail_fetch.update({"Portal", "Moodle"})
    with pytest.raises(PersonalCrawlError, match="all enabled sources") as caught:
        run_personal_crawl(env.user, "PRIVATE-TOKEN", {"Portal", "Moodle"})
    for source in ("Portal", "Moodle"):
        assert f"source={source} stage=fetch error=AssertionError" in caplog.text
    assert not env.saved
    assert env.updates == [env.user]
    assert "PRIVATE-" not in str(caught.value) + caplog.text + capsys.readouterr().out
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("stage", ["read stored tasks", "deduplicate", "save tasks", "save connection status"])
def test_processing_failures_have_safe_stage_diagnostics(personal_crawl_environment, stage, monkeypatch, caplog):
    from client.core.personal_crawl import PersonalCrawlError
    from unittest.mock import Mock

    env = personal_crawl_environment
    failing = Mock(side_effect=ValueError("PRIVATE-TASK-CONTENT PRIVATE-TOKEN"))
    target = {
        "read stored tasks": "Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
        "deduplicate": "DataProcessor.Validator.Validator.deduplicate_task",
        "save tasks": "Database.Repository.user_task_repository.UserTaskRepository.save_tasks",
        "save connection status": "Database.Repository.user_repository.UserRepository.update_user",
    }[stage]
    monkeypatch.setattr(target, failing)
    with pytest.raises(PersonalCrawlError, match=stage) as caught:
        run_personal_crawl(env.user, "PRIVATE-TOKEN", {"Portal"})
    assert f"stage={stage} error=ValueError" in caplog.text
    assert "PRIVATE-" not in caplog.text + str(caught.value)


@pytest.mark.parametrize("moodle", ["disabled", "fetch", "parse"])
def test_backend_crawl_then_supabase_refresh_exposes_new_owner_task(personal_crawl_environment, monkeypatch, moodle):
    from client.core.live_backend import LiveBackend
    from client.core.models import ClientUser
    from client.core.controller import ClientController
    from datetime import date

    env = personal_crawl_environment
    states = {}
    monkeypatch.setattr("Database.Repository.user_task_state_repository.UserTaskStateRepository.get_task_states", lambda *a: states)
    monkeypatch.setattr("sqlite3.connect", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("UI opened SQLite")))
    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", lambda *a, **kw: [])

    async def scenario():
        backend = LiveBackend()
        user = ClientUser(id=env.user.id, username=env.user.username)
        backend._users[user.id] = env.user
        backend._access_tokens[user.id] = "PRIVATE-TOKEN"
        if moodle == "disabled":
            await backend.set_source_enabled(user, "Moodle", False)
        else:
            getattr(env, f"fail_{moodle}").add("Moodle")
        result = await backend.sync(user)
        assert result.ok == (moodle == "disabled")
        if moodle != "disabled":
            assert "partially completed" in result.message and "Moodle failed" in result.message
        assert "1 new" in result.message
        loaded = await backend.load_tasks(user)
        assert [(record.scope, str(record.id), record.title) for record in loaded.snapshot.records] == [
            ("personal", "11111111-1111-4111-8111-111111111111", "New fictional Portal task")]
        assert loaded.snapshot.row_limit is None
        assert env.reads == [1000, None]
        controller = ClientController(backend, user)
        await controller.load_month(date(2026, 11, 1))
        record = controller.search("New fictional Portal task").hits[0]
        states[record.id] = {"status": "scheduled", "recurrence": False, "compulsory": True, "flexible": False}
        await controller.load_month()
        assert controller.select_search_record(record.key, session=controller.selection_session)
        assert controller.selected_search_record == record
        assert len(env.stored) == 1
        again = await backend.sync(user)
        assert again.ok == (moodle == "disabled")
        assert "0 new" in again.message
        assert len(env.saved) == 1

    asyncio.run(scenario())
