from __future__ import annotations

import asyncio
from datetime import date, datetime, time

import pytest
from pydantic import ValidationError

from DataProcessor.Standardization.ExtractedTask import ExtractedTask, VN_TZ
from Database.Repository.user_task_repository import UserTaskRepository
from client.core.controller import TaskMapper
from client.core.live_backend import LiveBackend
from client.core.mock_backend import MockBackend
from client.core.models import ClientUser, TaskDraft


def test_live_backend_saves_custom_task_for_signed_in_user(monkeypatch) -> None:
    user = ClientUser(id="user-123", username="student@example.com")
    backend = LiveBackend()
    backend._access_tokens[user.id] = "access-token"
    saved_tasks = []

    def save_tasks(repository, tasks):
        assert repository.user_id == user.id
        assert repository.headers["Authorization"] == "Bearer access-token"
        saved_tasks.extend(tasks)

    monkeypatch.setattr(UserTaskRepository, "save_tasks", save_tasks)

    result = asyncio.run(
        backend.create_task(
            user,
            TaskDraft(
                title="Personal event",
                kind="event",
                scheduled_date=date(2026, 11, 24),
                start_time=time(10, 0),
                end_time=time(11, 0),
            ),
        )
    )

    assert result.ok is True
    assert len(saved_tasks) == 1
    task = saved_tasks[0]
    assert task.user_id == user.id
    assert task.source_platform == "Custom"
    assert task.start_time.date == date(2026, 11, 24)
    assert task.start_time.time == time(10, 0)

    row = UserTaskRepository.task_to_row(task, user_id=user.id)
    row.update({"id": "task-456", "user_id": user.id})
    restored = UserTaskRepository.row_to_task(row)
    assert restored.type == "event"
    assert restored.source_platform == "Custom"
    assert restored.user_id == user.id


def test_live_create_task_requires_signed_in_access_token() -> None:
    result = asyncio.run(
        LiveBackend().create_task(
            ClientUser(id="user-123", username="student@example.com"),
            TaskDraft(title="Task", kind="assignment"),
        )
    )

    assert result.ok is False
    assert "Sign in again" in result.message


def test_live_backend_updates_and_deletes_only_custom_tasks(monkeypatch) -> None:
    user = ClientUser(id="user-123", username="student@example.com")
    backend = LiveBackend()
    backend._access_tokens[user.id] = "access-token"
    operations = []

    def update_custom_task(repository, task_id, task):
        operations.append(("update", repository.user_id, task_id, task))
        return True

    def delete_custom_task(repository, task_id):
        operations.append(("delete", repository.user_id, task_id))
        return True

    monkeypatch.setattr(
        UserTaskRepository,
        "update_custom_task",
        update_custom_task,
    )
    monkeypatch.setattr(
        UserTaskRepository,
        "delete_custom_task",
        delete_custom_task,
    )

    async def scenario() -> None:
        updated = await backend.update_task(
            user,
            "task-456",
            TaskDraft(title="Updated", kind="assignment"),
        )
        deleted = await backend.delete_task(user, "task-456")
        assert updated.ok is True
        assert deleted.ok is True

    asyncio.run(scenario())

    assert operations[0][:3] == ("update", user.id, "task-456")
    assert operations[0][3].title == "Updated"
    assert operations[0][3].source_platform == "Custom"
    assert operations[1] == ("delete", user.id, "task-456")


def test_live_backend_reports_custom_task_not_found(monkeypatch) -> None:
    user = ClientUser(id="user-123", username="student@example.com")
    backend = LiveBackend()
    backend._access_tokens[user.id] = "access-token"
    monkeypatch.setattr(
        UserTaskRepository,
        "delete_custom_task",
        lambda self, task_id: False,
    )

    result = asyncio.run(backend.delete_task(user, "other-users-task"))

    assert result.ok is False
    assert result.message == "Custom task was not found"


def test_custom_repository_scopes_mutations_to_owned_custom_tasks(
    monkeypatch,
) -> None:
    calls = []

    class Response:
        ok = True

        def json(self):
            return [{"id": "task-456"}]

    def patch(url, *, params, **kwargs):
        calls.append(("patch", params))
        return Response()

    def delete(url, *, params, **kwargs):
        calls.append(("delete", params))
        return Response()

    monkeypatch.setattr(
        "Database.Repository.user_task_repository.requests.patch",
        patch,
    )
    monkeypatch.setattr(
        "Database.Repository.user_task_repository.requests.delete",
        delete,
    )

    user = ClientUser(id="user-123", username="student@example.com")
    task = LiveBackend._task_model(
        user,
        TaskDraft(title="Custom", kind="event"),
    )
    repository = UserTaskRepository(
        supabase_url="https://supabase.example",
        supabase_key="public-key",
        access_token="access-token",
        user_id=user.id,
    )

    assert repository.update_custom_task("task-456", task) is True
    assert repository.delete_custom_task("task-456") is True
    assert calls == [
        (
            "patch",
            {
                "id": "eq.task-456",
                "user_id": "eq.user-123",
                "source_platform": "eq.Custom",
            },
        ),
        (
            "delete",
            {
                "id": "eq.task-456",
                "user_id": "eq.user-123",
                "source_platform": "eq.Custom",
            },
        ),
    ]


def test_mock_backend_created_task_is_returned_to_calendar() -> None:
    async def scenario() -> None:
        backend = MockBackend()
        user = await backend.login("student", "demo")
        result = await backend.create_task(
            user,
            TaskDraft(
                title="Custom class",
                kind="class",
                scheduled_date=date(2026, 11, 24),
            ),
        )
        tasks = await backend.get_tasks(user)

        assert result.ok is True
        created = next(task for task in tasks if task["title"] == "Custom class")
        item = TaskMapper.map_range(
            created,
            date(2026, 11, 1),
            date(2026, 11, 30),
        )[0]
        assert item.day == date(2026, 11, 24)
        assert item.time_label == "All day"

        updated = await backend.update_task(
            user,
            created["id"],
            TaskDraft(title="Updated custom class", kind="class"),
        )
        tasks = await backend.get_tasks(user)
        assert updated.ok is True
        assert not any(task["title"] == "Custom class" for task in tasks)
        assert any(task["title"] == "Updated custom class" for task in tasks)

        deleted = await backend.delete_task(user, created["id"])
        tasks = await backend.get_tasks(user)
        assert deleted.ok is True
        assert not any(task["id"] == created["id"] for task in tasks)

        other_user = ClientUser(id="other", username="other")
        assert not (
            await backend.delete_task(other_user, created["id"])
        ).ok

    asyncio.run(scenario())


def test_non_custom_events_still_require_crawler_metadata() -> None:
    with pytest.raises(ValidationError):
        ExtractedTask(
            title="Crawler event",
            type="event",
            source_url="https://example.test/event",
            source_platform="Moodle",
            updated_at=datetime.now(VN_TZ),
        )
