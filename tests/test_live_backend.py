from __future__ import annotations

import asyncio

from Backend.Regulation.User import User
from client.core.live_backend import LiveBackend


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
        lambda self, limit=100: [{"title": "Public", "source_platform": "VNUHCMUS"}],
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
        lambda self, limit=100: [{"title": "Personal", "source_platform": "Portal"}],
    )

    async def scenario() -> None:
        backend = LiveBackend()
        user = await backend.login("student@example.com", "password123")
        tasks = await backend.get_tasks(user)

        assert user.id == "user-123"
        assert [task["title"] for task in tasks] == ["Public", "Personal"]

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
