from __future__ import annotations

import asyncio

import pytest

from DataProcessor.Standardization.User import User
from client.core.live_backend import LiveBackend
from test_search_records import task


def test_live_backend_uses_supabase_auth_and_personal_task_repository(
    monkeypatch,
) -> None:
    backend_user = User(
        id="user-123",
        username="student@example.com",
        portal_status=True,
    )

    monkeypatch.setattr(
        "Database.auth.sign_in",
        lambda username, password: ("access-token", backend_user),
    )
    monkeypatch.setattr(
        "Database.Repository.task_repository.TaskRepository.get_tasks",
        lambda self, limit=100: [task(title="Public", source_platform="VNUHCMUS")],
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
        lambda self, limit=100: [task(id="22222222-2222-4222-8222-222222222222", title="Personal", source_platform="Portal")],
    )

    async def scenario() -> None:
        backend = LiveBackend()
        user = await backend.login("student@example.com", "password123")
        tasks = await backend.get_tasks(user)

        assert user.id == "user-123"
        assert [task.title for task in tasks] == ["Public", "Personal"]

    asyncio.run(scenario())


def test_sync_accepts_portal_credentials_without_a_prior_browser_session(monkeypatch):
    from client.core.models import ClientUser
    calls = []

    def crawl(user, token, enabled):
        calls.append((user.id, token, enabled))
        return 1, 1

    monkeypatch.setattr("client.core.personal_crawl.run_personal_crawl", crawl)

    async def scenario():
        backend = LiveBackend()
        user = ClientUser(id="fictional-owner", username="fictional@example.invalid")
        backend._users[user.id] = User(id=user.id, portal_username="fictional", portal_password="PRIVATE-PASSWORD")
        backend._access_tokens[user.id] = "PRIVATE-TOKEN"
        await backend.set_source_enabled(user, "Moodle", False)
        result = await backend.sync(user)
        assert result.ok
        assert calls == [(user.id, "PRIVATE-TOKEN", {"Portal"})]

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["initialization", "all sources"])
def test_sync_failures_notify_safely_and_release_owner_lock(monkeypatch, caplog, failure):
    from client.core.models import ClientUser
    from client.core.personal_crawl import PersonalCrawlError
    calls = []

    def crawl(user, token, enabled):
        calls.append(user.id)
        if len(calls) == 1:
            if failure == "initialization":
                raise ValueError("PRIVATE-PASSWORD PRIVATE-TOKEN PRIVATE-PAGE")
            raise PersonalCrawlError("Personal crawl failed for all enabled sources. Reconnect Portal/Moodle in Settings.")
        return 0, 0

    monkeypatch.setattr("client.core.personal_crawl.run_personal_crawl", crawl)

    async def scenario():
        backend = LiveBackend()
        user = ClientUser(id="fictional-owner", username="fictional@example.invalid")
        backend._users[user.id] = User(id=user.id, portal_username="fictional", portal_password="PRIVATE-PASSWORD")
        backend._access_tokens[user.id] = "PRIVATE-TOKEN"
        result = await backend.sync(user)
        assert not result.ok and "Settings" in result.message
        assert "PRIVATE-" not in result.message
        assert not backend._crawl_locks[user.id].locked()
        assert (await backend.sync(user)).ok

    asyncio.run(scenario())
    if failure == "initialization":
        assert "stage=initialization error=ValueError" in caplog.text
    assert "PRIVATE-" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_sync_keeps_per_owner_lock_and_source_preferences(monkeypatch):
    from client.core.models import ClientUser
    import threading

    started, release = threading.Event(), threading.Event()
    calls = []

    def crawl(user, token, enabled):
        calls.append((user.id, token, enabled))
        started.set()
        assert release.wait(10)
        return 0, 0

    monkeypatch.setattr("client.core.personal_crawl.run_personal_crawl", crawl)

    async def scenario():
        backend = LiveBackend()
        user = ClientUser(id="fictional-owner", username="fictional@example.invalid")
        backend._users[user.id] = User(id=user.id, portal_username="fictional", portal_password="PRIVATE-PASSWORD")
        backend._access_tokens[user.id] = "PRIVATE-TOKEN"
        await backend.set_source_enabled(user, "Moodle", False)
        pending = asyncio.create_task(backend.sync(user))
        try:
            assert await asyncio.to_thread(started.wait, 10)
            concurrent = await backend.sync(user)
            assert not concurrent.ok and "already running" in concurrent.message
        finally:
            release.set()
        assert (await pending).ok
        assert calls == [(user.id, "PRIVATE-TOKEN", {"Portal"})]
        await backend.set_source_enabled(user, "Portal", False)
        disabled = await backend.sync(user)
        assert not disabled.ok and "Enable Portal or Moodle" in disabled.message
        assert len(calls) == 1

    asyncio.run(scenario())


def test_live_sync_runs_the_signed_in_users_personal_crawler(monkeypatch) -> None:
    backend_user = User(
        id="user-123",
        username="student@example.com",
        portal_username="23123456",
        portal_password="secret",
        portal_session='{"cookies": []}',
    )
    monkeypatch.setattr(
        "client.core.personal_crawl.run_personal_crawl",
        lambda user, access_token, enabled_sources: (2, 7),
    )

    async def scenario() -> None:
        backend = LiveBackend()
        backend._users["user-123"] = backend_user
        backend._access_tokens["user-123"] = "access-token"

        result = await backend.sync(
            user=await backend.login("student@example.com", "password123")
        )

        assert result.ok is True
        assert result.message == "Personal calendar refreshed: 2 new, 7 stored"

    monkeypatch.setattr(
        "Database.auth.sign_in",
        lambda username, password: ("access-token", backend_user),
    )
    asyncio.run(scenario())
