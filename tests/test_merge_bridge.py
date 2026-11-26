"""Offline compatibility of FE calendar state and complete original Search records."""

import asyncio
from datetime import date
import threading
from uuid import UUID

import requests

from client.core.controller import ClientController
from client.core.live_backend import LiveBackend
from client.core.mock_backend import MockBackend
from client.core.models import ClientUser, TaskDraft
from test_search_records import task

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MONTH = date(2026, 11, 1)


def test_bridge_keeps_all_calendar_rows_and_search_originals(monkeypatch):
    public = [task(id=str(UUID(int=n + 1, version=4)), title=f"Public {n}",
                   deadline="2026-11-26T09:00:00+07:00") for n in range(1001)]
    personal = task(id="aaaaaaaa-2222-4222-8222-222222222222", user_id=A, title="Private original", source_platform="Moodle")
    calls = []

    def public_read(repo, limit):
        calls.append(("public", limit))
        return public

    def personal_read(repo, limit):
        calls.append(("personal", limit, repo.user_id, repo.headers["Authorization"]))
        return [personal]

    def state_read(repo, rows):
        calls.append(("state", repo.user_id, len(rows), repo.headers["Authorization"]))
        return {public[-1].id: {"status": "rejected", "recurrence": False, "compulsory": False, "flexible": False}}

    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", public_read)
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository.get_tasks", personal_read)
    monkeypatch.setattr("Database.Repository.user_task_state_repository.UserTaskStateRepository.get_task_states", state_read)
    monkeypatch.setattr("sqlite3.connect", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Bridge opened SQLite")))

    async def scenario():
        backend = LiveBackend()
        backend._access_tokens[A] = "fictional-a"
        controller = ClientController(backend, ClientUser(A, "A"))
        await controller.load_month(MONTH)
        assert controller.state.error is None
        assert calls == [("public", None), ("personal", None, A, "Bearer fictional-a"),
                         ("state", A, 1002, "Bearer fictional-a")]
        loaded = controller._loaded_tasks
        assert len(loaded.tasks) == len(loaded.calendar_keys) == 1002
        assert len(loaded.snapshot.records) == 1002
        assert dict(loaded.snapshot.row_limits) == {"public": None, "personal": None}
        assert loaded.tasks[1000].status == "rejected"
        assert loaded.tasks[0].title == public[0].title
        assert loaded.snapshot.get_task(("public", public[0].id)).title == "Public 0"
        assert loaded.snapshot.get_task(("personal", personal.id)).title == "Private original"
        assert loaded.snapshot.get_task(("public", public[-1].id)).title == "Public 1000"
        assert len(controller.state.items) == 1001
        assert len(controller.active_items) == 1000
        assert controller.search("Private original").hits[0].key == ("personal", personal.id)
        assert controller.select_search_record(("personal", personal.id), session=controller.selection_session)
        assert controller.selected_search_record.source_url == personal.source_url
        controller.search("", sort="title")
        controller.show_month(date(2026, 12, 1))
        assert len(calls) == 3

    asyncio.run(scenario())


def test_mock_personal_tasks_stay_in_calendar_and_undated_tasks_in_agenda():
    async def scenario():
        backend = MockBackend()
        user = await backend.register("new-owner", "fictional-password")
        await backend.create_task(user, TaskDraft(title="Personal appointment", kind="personal", scheduled_date=date(2026, 11, 26)))
        await backend.create_task(user, TaskDraft(title="Undated custom assignment", kind="assignment"))
        controller = ClientController(backend, user)
        await controller.load_month(MONTH)
        assert controller.state.error is None
        assert any(item.title == "Personal appointment" for item in controller.state.items)
        assert controller.search("Personal appointment").hits[0].type == "personal"
        assert controller.search("Undated custom assignment").hits
        controller.search("")
        controller.set_view("agenda")
        item = next(item for item in controller.filtered_items if item.title == "Undated custom assignment")
        controller.select_item(item.id)
        assert controller.selected_item.title == item.title
        assert all(item.day is not None for item in controller.state.items)

    asyncio.run(scenario())


def test_late_overlay_read_cannot_repopulate_logout_caches_or_replace_account_b(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", lambda *a: [task(title="Public")])
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository.get_tasks",
                        lambda repo, limit: [task(id="cccccccc-cccc-4ccc-8ccc-cccccccccccc", title=f"Private {repo.user_id}", source_platform="Moodle", user_id=repo.user_id)])

    def state_read(repo, rows):
        if repo.user_id == A:
            entered.set()
            assert release.wait(10)
        return {}

    monkeypatch.setattr("Database.Repository.user_task_state_repository.UserTaskStateRepository.get_task_states", state_read)

    async def scenario():
        backend = LiveBackend()
        backend._access_tokens.update({A: "fictional-a", B: "fictional-b"})
        owner_a, owner_b = ClientUser(A, "A"), ClientUser(B, "B")
        controller = ClientController(backend, owner_a)
        session = controller.selection_session
        pending = asyncio.create_task(controller.load_month(MONTH))
        try:
            assert await asyncio.to_thread(entered.wait, 10)
            controller.set_user(owner_b)
            backend.logout(owner_a)
            await controller.load_month(MONTH)
        finally:
            release.set()
        await pending
        record = next(r for r in controller.state.search_snapshot.records if r.scope == "personal")
        assert record.title == f"Private {B}"
        assert controller.state.error is None and not controller.state.loading
        assert not controller.select_search_record(record.key, session=session)
        assert A not in backend._merged_tasks_by_id and A not in backend._original_groups
        assert controller.select_search_record(record.key, session=controller.selection_session)
        controller.logout()
        assert controller.selected_search_record is None and controller.state.schedule is None
        assert controller.search("").hits == ()

    asyncio.run(scenario())


def test_overlay_credential_rejection_expires_the_session(monkeypatch):
    monkeypatch.setattr("Database.Repository.task_repository.TaskRepository.get_tasks", lambda *a: [task()])
    monkeypatch.setattr("Database.Repository.user_task_repository.UserTaskRepository.get_tasks", lambda *a: [])

    def rejected(*args):
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError("Fictional expired session", response=response)

    monkeypatch.setattr("Database.Repository.user_task_state_repository.UserTaskStateRepository.get_task_states", rejected)

    async def scenario():
        backend = LiveBackend()
        backend._access_tokens[A] = "fictional-a"
        controller = ClientController(backend, ClientUser(A, "A"))
        await controller.load_month(MONTH)
        assert controller.state.session_expired
        assert controller.state.items == [] and controller.selected_search_record is None
        assert A not in backend._access_tokens and A not in backend._original_groups

    asyncio.run(scenario())
