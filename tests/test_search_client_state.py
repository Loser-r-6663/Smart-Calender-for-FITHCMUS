"""Offline checks of shared task loads and session-owned Search state."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
import requests

from client.core.backend import SessionExpiredError, task_load
from client.core.controller import ClientController
from client.core.live_backend import LiveBackend
from client.core.mock_backend import MockBackend
from client.core.models import ClientUser
from test_search_records import task

OWNER_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OWNER_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TASK_ID = "11111111-1111-4111-8111-111111111111"
MONTH = date(2026, 11, 1)


def install_reads(monkeypatch):
    calls = []
    public = task(title="Off-month public", deadline="2027-01-12T08:00:00+07:00")
    personal = task(title="Private undated", source_platform="Moodle")
    weekly = task(id="22222222-2222-4222-8222-222222222222",
                  title="Weekly class", type="class", source_platform="Portal",
                  start_time={"day": "T2", "time": "08:00:00"})

    def public_read(repo, limit):
        calls.append(("public", limit, repo.headers["apikey"], repo.headers["Authorization"]))
        return [public]

    def personal_read(repo, limit):
        calls.append(("personal", limit, repo.user_id, repo.headers["apikey"], repo.headers["Authorization"]))
        return [personal, weekly]

    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_PUBLIC_KEY", "fictional-public-key")
    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", public_read)
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository.get_tasks", personal_read)
    return calls


def test_one_live_load_serves_calendar_search_and_scoped_details(monkeypatch):
    calls = install_reads(monkeypatch)

    async def scenario():
        backend = LiveBackend()
        backend._access_tokens[OWNER_A] = "fictional-token-a"
        controller = ClientController(backend, ClientUser(OWNER_A, "A"))
        await controller.load_month(MONTH)
        assert calls == [
            ("public", 1000, "fictional-public-key", "Bearer fictional-public-key"),
            ("personal", 1000, OWNER_A, "fictional-public-key", "Bearer fictional-token-a"),
        ]
        snapshot = controller.state.search_snapshot
        assert snapshot.loaded_scopes == ("public", "personal")
        assert dict(snapshot.row_limits) == {"public": 1000, "personal": 1000}
        assert [item.day for item in controller.state.items] == [
            date(2026, 10, 26), *[date(2026, 11, n) for n in (2, 9, 16, 23, 30)],
        ]
        assert controller.state.visible_month == MONTH
        assert [r.key for r in controller.search("off-month").hits] == [("public", TASK_ID)]
        controller.set_query("undated")
        assert [r.key for r in controller.search_results.hits] == [("personal", TASK_ID)]
        controller.state.selected_search_key = ("personal", TASK_ID)
        assert controller.selected_search_record.title == "Private undated"
        controller.set_query("")
        assert len(controller.search_results.hits) == 3
        assert len(calls) == 2
        assert controller.state.search_snapshot is snapshot
        await backend.set_source_enabled(controller.state.user, "Portal", False)
        await backend.set_source_enabled(controller.state.user, "Moodle", False)
        await controller.load_month()
        assert len(calls) == 4
        assert controller.state.items == []
        assert [r.key for r in controller.search_results.hits] == [("public", TASK_ID)]
        assert controller.selected_search_record is None
        assert controller.state.search_snapshot.loaded_scopes == ("public", "personal")

    asyncio.run(scenario())


def test_mock_contract_stable_keys_source_filters_and_personal_visibility():
    async def scenario():
        backend = MockBackend()
        user = await backend.login("student", "demo")
        controller = ClientController(backend, user)
        await controller.load_month(MONTH)
        keys = [r.key for r in controller.state.search_snapshot.records]
        assert len(keys) == 6
        assert len(controller.search("scholarship").hits) == 1
        assert all(item.day is not None for item in controller.state.items)
        await controller.load_month()
        assert [r.key for r in controller.state.search_snapshot.records] == keys
        await backend.set_source_enabled(user, "Portal", False)
        await controller.load_month()
        assert all(r.publisher != "Portal" for r in controller.state.search_snapshot.records)
        assert all(item.source != "Portal" for item in controller.state.items)
        assert dict(controller.state.search_snapshot.row_limits) == {"public": 1000, "personal": 1000}
        new_user = await backend.register("new-user", "password123")
        controller.set_user(new_user)
        await controller.load_month(MONTH)
        assert controller.state.search_snapshot.loaded_scopes == ("public",)
        assert all(r.scope == "public" for r in controller.state.search_snapshot.records)

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "failure", "expiry"])
def test_account_switch_discards_old_load_success_error_and_loading(outcome):
    async def scenario():
        backend = MockBackend()
        entered, release = asyncio.Event(), asyncio.Event()
        private_a = task(title="Private A")
        private_b = task(title="Private B")

        async def load(user):
            if user.id == OWNER_A:
                entered.set()
                await release.wait()
                if outcome == "failure":
                    raise RuntimeError("Late A service error")
                if outcome == "expiry":
                    raise SessionExpiredError("Late A expiry")
                return task_load((("personal", [private_a]),), set())
            return task_load((("personal", [private_b]),), set())

        backend.load_tasks = load
        controller = ClientController(backend, ClientUser(OWNER_A, "A"))
        controller.state.selected_item_id = "old-calendar-detail"
        controller.state.selected_search_key = ("personal", TASK_ID)
        pending = asyncio.create_task(controller.load_month(MONTH))
        await entered.wait()
        controller.set_user(ClientUser(OWNER_B, "B"))
        assert controller.selected_item is None
        assert controller.selected_search_record is None
        await controller.load_month(MONTH)
        controller.state.selected_search_key = ("personal", TASK_ID)
        release.set()
        await pending
        assert controller.state.user.id == OWNER_B
        assert controller.selected_search_record.title == "Private B"
        assert controller.state.error is None
        assert not controller.state.loading
        assert [r.title for r in controller.search("").hits] == ["Private B"]

    asyncio.run(scenario())


def test_backend_logout_invalidates_all_session_controllers_and_pending_load():
    async def scenario():
        backend = LiveBackend()
        backend._access_tokens[OWNER_A] = "token"
        user = ClientUser(OWNER_A, "A")
        first, second = ClientController(backend, user), ClientController(backend, user)
        loaded = task_load((("personal", [task(title="Private")]),), set())
        backend.load_tasks = AsyncMock(return_value=loaded)
        await first.load_month(MONTH)
        first.state.selected_search_key = ("personal", TASK_ID)
        entered, release = asyncio.Event(), asyncio.Event()

        async def late_load(user):
            entered.set()
            await release.wait()
            return loaded

        backend.load_tasks = late_load
        pending = asyncio.create_task(second.load_month(MONTH))
        await entered.wait()
        backend.logout(user)
        release.set()
        await pending
        for controller in (first, second):
            assert controller.state.user is None
            assert controller.state.items == []
            assert controller.search_results.hits == ()
            assert controller.selected_search_record is None
            assert controller.selected_item is None
            assert controller.state.error is None
            assert not controller.state.loading
        assert OWNER_A not in backend._access_tokens

    asyncio.run(scenario())


def test_missing_live_session_expires_without_repository_access(monkeypatch):
    calls = install_reads(monkeypatch)

    async def scenario():
        controller = ClientController(LiveBackend(), ClientUser(OWNER_A, "A"))
        await controller.load_month(MONTH)
        assert calls == []
        assert controller.state.session_expired
        assert controller.state.user is None

    asyncio.run(scenario())


def test_old_completion_cannot_clear_new_sessions_loading_state():
    async def scenario():
        backend = MockBackend()
        started_a, started_b = asyncio.Event(), asyncio.Event()
        release_a, release_b = asyncio.Event(), asyncio.Event()

        async def load(user):
            started, release = (started_a, release_a) if user.id == OWNER_A else (started_b, release_b)
            started.set()
            await release.wait()
            return task_load((("personal", [task(title=user.username)]),), set())

        backend.load_tasks = load
        controller = ClientController(backend, ClientUser(OWNER_A, "A"))
        pending_a = asyncio.create_task(controller.load_month(MONTH))
        await started_a.wait()
        controller.set_user(ClientUser(OWNER_B, "B"))
        pending_b = asyncio.create_task(controller.load_month(MONTH))
        await started_b.wait()
        release_a.set()
        await pending_a
        assert controller.state.loading
        assert controller.state.search_snapshot.records == ()
        assert controller.state.error is None
        release_b.set()
        await pending_b
        assert not controller.state.loading
        assert [r.title for r in controller.search("").hits] == ["B"]

    asyncio.run(scenario())


@pytest.mark.parametrize("status", [401, 403, 503, 200])
def test_live_expiry_service_error_and_empty_are_distinct(monkeypatch, status):
    install_reads(monkeypatch)
    reads = []

    def read(repo, limit):
        reads.append(repo)
        if status == 200:
            return []
        response = requests.Response()
        response.status_code = status
        raise requests.HTTPError("Controlled read failure", response=response)

    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", read)
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository.get_tasks", read)

    async def scenario():
        backend = LiveBackend()
        backend._access_tokens[OWNER_A] = "token"
        controller = ClientController(backend, ClientUser(OWNER_A, "A"))
        controller.state.search_snapshot = task_load((("personal", [task()]),), set()).snapshot
        controller.state.selected_search_key = ("personal", TASK_ID)
        await controller.load_month(MONTH)
        assert controller.state.items == []
        assert controller.search_results.hits == ()
        assert controller.selected_search_record is None
        assert not controller.state.loading
        if status in (401, 403):
            assert controller.state.user is None
            assert controller.state.session_expired
            assert controller.state.error == "Session expired. Sign in again."
            assert OWNER_A not in backend._access_tokens
        elif status == 503:
            assert controller.state.user is not None
            assert not controller.state.session_expired
            assert controller.state.error == "Controlled read failure"
        else:
            assert controller.state.error is None
            assert controller.state.search_snapshot.loaded_scopes == ("public", "personal")
            assert len(reads) == 2

    asyncio.run(scenario())
