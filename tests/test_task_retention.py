"""Authorized Supabase originals shared by Calendar and Search."""

import asyncio
from datetime import date
import json
import threading
from types import SimpleNamespace
from uuid import UUID

import pytest
import requests

from academic_search import load_snapshot
from client.core.controller import ClientController
from client.core.live_backend import LiveBackend
from client.core.models import ClientUser, TaskDraft
from Database.Repository.task_repository import TaskRepository
from test_search_records import task

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
MONTH = date(2026, 11, 1)


def uid(number):
    return str(UUID(int=number, version=4))


def reply(rows, status=200):
    response = requests.Response()
    response.status_code = status
    response.reason = "Fictional response"
    response._content = json.dumps(rows).encode()
    return response


@pytest.fixture
def remote(monkeypatch):
    state = SimpleNamespace(public=[task(id=uid(1), title="Public notice")],
        personal={A: [task(id=uid(2), user_id=A, title="Private A", source_platform="Portal")],
                  B: [task(id=uid(3), user_id=B, title="Private B", source_platform="Moodle")]},
        overlays={A: {}, B: {}}, reads=[], writes=[], failure=None, block=None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.invalid")
    monkeypatch.setenv("SUPABASE_PUBLIC_KEY", "fictional-public")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "must-not-use-server-key")

    def prohibited(*a, **kw):
        raise AssertionError("Snapshot path invoked SQLite, task deletion or scheduling")

    monkeypatch.setattr("sqlite3.connect", prohibited)
    monkeypatch.setattr("requests.delete", prohibited)
    monkeypatch.setattr("Scheduler.scheduler.BranchAndBoundScheduler.schedule", prohibited)

    def get(url, *, params, headers, timeout):
        route = url.rsplit("/", 1)[1]
        owner = params.get("user_id", "").removeprefix("eq.")
        offset = params.get("offset", 0)
        assert headers["apikey"] == "fictional-public" and timeout == 30
        if owner:
            assert owner in (A, B)
            assert headers["Authorization"] == "Bearer token-" + owner
        else:
            assert route == "tasks"
            assert headers["Authorization"] == "Bearer fictional-public"
        state.reads.append((route, owner, dict(params), dict(headers)))
        if state.block and (route, owner, offset) == state.block[:3]:
            state.block[3].set()
            assert state.block[4].wait(15)
        if state.failure and (route, owner, offset) == state.failure[:3]:
            return reply([], state.failure[3])
        if route == "user_task_state":
            return reply([{"id": key, **value} for key, value in state.overlays[owner].items()])
        assert params["order"] == "id.asc"
        assert params["limit"] == 1000
        values = state.public if route == "tasks" else state.personal[owner]
        rows = [TaskRepository.task_to_row(value) | {"id": value.id, "user_id": value.user_id}
                for value in values[offset:offset + params["limit"]]]
        return reply(rows)

    def post(url, *, headers, json, timeout, **kwargs):
        owner = headers["Authorization"].removeprefix("Bearer token-")
        assert owner in (A, B) and headers["apikey"] == "fictional-public"
        state.writes.append((url, owner, json))
        if url.endswith("/user_task"):
            saved = []
            for row in json:
                assert row["user_id"] == owner
                row = {**row, "id": uid(50000 + len(state.personal[owner]))}
                state.personal[owner].append(TaskRepository.row_to_task(row))
                saved.append(row)
            return reply(saved)
        assert url.endswith("/user_task_state")
        for row in json:
            assert row["user_id"] == owner
            state.overlays[owner][row["id"]] = {key: row[key] for key in ("status", "recurrence", "compulsory", "flexible")}
        return reply(json)

    monkeypatch.setattr("requests.get", get)
    monkeypatch.setattr("requests.post", post)
    return state


def backend(owner=A):
    live = LiveBackend()
    live._access_tokens[owner] = "token-" + owner
    return live


def task_reads(remote):
    return [call for call in remote.reads if call[0] != "user_task_state"]


@pytest.mark.parametrize("owner,public_count,private_count", [(None, 1001, 0), (A, 1001, 1001), (B, 2000, 1000)])
def test_every_authorized_page_including_exact_multiples(remote, owner, public_count, private_count):
    remote.public = [task(id=uid(n + 10), title=f"Public {n}") for n in range(public_count)]
    if owner:
        remote.personal[owner] = [task(id=uid(n + 10000), user_id=owner, title=f"Private {n}", source_platform="Portal") for n in range(private_count)]
    async def scenario():
        live = backend(owner) if owner else LiveBackend()
        if owner:
            controller = ClientController(live, ClientUser(owner, owner))
            await controller.load_month(MONTH)
            assert controller.state.error is None
            loaded = controller._loaded_tasks
        else:
            loaded = await live.load_tasks(None)
        assert len(loaded.snapshot.records) == public_count + private_count
        assert loaded.snapshot.row_limit is None
        assert loaded.snapshot.loaded_scopes == (("public", "personal") if owner else ("public",))
        expected = [("tasks", "", n) for n in range(0, public_count + 1, 1000)]
        if owner:
            expected += [("user_task", owner, n) for n in range(0, private_count + 1, 1000)]
        assert [(route, who, params["offset"]) for route, who, params, _ in task_reads(remote)] == expected
        if owner:
            reads = len(remote.reads)
            target = remote.public[-1]
            assert public_count > 1000
            assert controller.search(target.title).hits[0].key == ("public", target.id)
            assert controller.select_search_record(("public",target.id),session=controller.selection_session)
            assert controller.selected_search_record.title == target.title
            assert len(remote.reads) == reads
        if not owner:
            assert not remote.writes and all(call[0] == "tasks" for call in remote.reads)
    asyncio.run(scenario())


def test_standalone_loader_defaults_to_complete_paginated_public_snapshot(remote):
    remote.public = [task(id=uid(n + 10), title=f"Notice {n}") for n in range(1001)]
    snapshot = load_snapshot(supabase_url="https://example.invalid", public_key="fictional-public")
    assert len(snapshot.records) == 1001 and snapshot.row_limit is None
    assert [row[2]["offset"] for row in task_reads(remote)] == [0, 1000]


def test_original_details_survive_overlay_and_refresh_with_no_interaction_reads(remote):
    original = task(id=uid(2), user_id=A, title="Original zero point event", type="event", training_points=0,
        estimated_hours=2, source_platform="Portal", source_url="https://example.invalid/original",
        registration_start="2027-01-01T08:00:00+07:00", registration_end="2027-01-03T17:00:00+07:00",
        deadline="2027-01-04T18:00:00+07:00", start_time={"date":"2027-01-05", "time":"09:00:00"},
        end_time={"date":"2027-01-05", "time":"11:00:00"})
    remote.personal[A] = [original]
    async def scenario():
        live = backend()
        controller = ClientController(live, ClientUser(A, "A"))
        await controller.load_month(MONTH)
        assert len(task_reads(remote)) == 2
        key = ("personal", original.id)
        before = controller.state.search_snapshot.get_task(key)
        assert before.training_points == 0 and before.registration_end == original.registration_end
        assert before.deadline == original.deadline and before.start_time.date == date(2027, 1, 5)
        assert (await live.set_task_schedule_state(controller.state.user, original.id, status="scheduled", compulsory=True)).ok
        await controller.load_month()
        assert len(task_reads(remote)) == 4 and remote.writes
        assert controller.state.search_snapshot.get_task(key) == before
        calendar = next(value for value in controller._loaded_tasks.tasks if value.id == original.id)
        assert calendar.status == "scheduled" and calendar.compulsory
        reads = len(remote.reads)
        for sort in (None, "title", "latest_deadline", "soonest_deadline"):
            assert controller.search("Original", filters={"types":["event"]}, sort=sort).hits[0] == before
        assert controller.select_search_record(key, session=controller.selection_session)
        assert controller.selected_search_record.source_url == original.source_url
        controller.search("")
        controller.show_month(date(2027, 1, 1))
        assert len(remote.reads) == reads
        other = await backend(B).load_tasks(ClientUser(B, "B"))
        guest = await LiveBackend().load_tasks(None)
        assert other.snapshot.get_task(key) is None and guest.snapshot.get_task(key) is None
    asyncio.run(scenario())


def test_all_history_sources_and_custom_types_are_searchable_only_by_owner(remote):
    expired = task(id=uid(4), user_id=A, title="Expired scheduled source", deadline="2000-01-01T09:00:00+07:00", source_platform="Portal")
    custom = task(id=uid(5), user_id=A, title="Owner custom appointment", type="personal", source_platform=None, source_url="")
    remote.personal[A] += [expired, custom]
    remote.overlays[A][expired.id] = {"status":"scheduled", "recurrence":False, "compulsory":True, "flexible":False}
    async def scenario():
        live = backend()
        controller = ClientController(live, ClientUser(A, "A"))
        await controller.load_month(MONTH)
        assert len(controller.search("").hits) == 4
        controller.set_filter("personal")
        assert [r.key for r in controller.search("Owner custom").hits] == [("personal", custom.id)]
        assert controller.select_search_record(("personal",custom.id),session=controller.selection_session)
        assert controller.selected_search_record.type == "personal"
        controller.set_filter("all")
        assert controller.search("Expired").hits[0].key == ("personal",expired.id)
        assert controller.select_search_record(("personal",expired.id),session=controller.selection_session)
        await live.set_source_enabled(controller.state.user,"Portal",False)
        await controller.load_month()
        assert all(r.publisher != "Portal" for r in controller.state.search_snapshot.records)
        assert all(item.source != "Portal" for item in controller.state.items)
        assert controller.selected_search_record is None
        controller.set_user(ClientUser(B,"B"))
        live._access_tokens[B] = "token-" + B
        await controller.load_month()
        assert controller.search("Owner custom").hits == ()
        assert not controller.select_search_record(("personal",custom.id),session=controller.selection_session)
    asyncio.run(scenario())


@pytest.mark.parametrize("duplicate", ["same-page", "later-page", "cross-source"])
def test_duplicate_keys_and_cross_source_collisions_fail_before_overlay(remote, duplicate):
    if duplicate == "same-page":
        remote.public *= 2
    elif duplicate == "later-page":
        remote.public = [task(id=uid(n+10)) for n in range(1000)] + [task(id=uid(10))]
    else:
        remote.personal[A] = [task(id=remote.public[0].id, user_id=A)]
    async def scenario():
        controller = ClientController(backend(),ClientUser(A,"A"))
        await controller.load_month(MONTH)
        assert "UUID" in controller.state.error and not controller.state.session_expired
        assert controller.search("").hits == () and controller.state.items == []
        assert controller.state.search_snapshot.loaded_scopes == ()
        assert not any(row[0] == "user_task_state" for row in remote.reads)
    asyncio.run(scenario())


@pytest.mark.parametrize("route,owner", [("tasks", ""), ("user_task", A)])
@pytest.mark.parametrize("status", [500, 401])
def test_later_page_failure_never_publishes_partial_or_old_details(remote, route, owner, status):
    async def scenario():
        controller = ClientController(backend(),ClientUser(A,"A"))
        await controller.load_month(MONTH)
        assert controller.select_search_record(("personal",uid(2)),session=controller.selection_session)
        values = [task(id=uid(n+10000),user_id=A if owner else None) for n in range(1001)]
        if owner: remote.personal[A] = values
        else: remote.public = values
        remote.failure = (route,owner,1000,status)
        await controller.load_month()
        assert controller.state.error
        assert controller.state.session_expired == (status == 401)
        assert controller.selected_search_record is None
        assert controller.state.items == [] and controller.search("").hits == ()
        assert not controller.state.loading
    asyncio.run(scenario())


def test_successful_empty_read_is_distinct_from_failure(remote):
    remote.public = []
    remote.personal[A] = []
    async def scenario():
        controller = ClientController(backend(),ClientUser(A,"A"))
        await controller.load_month(MONTH)
        assert controller.state.error is None and not controller.state.session_expired
        assert controller.state.search_snapshot.loaded_scopes == ("public","personal")
        assert controller.search("").hits == ()
    asyncio.run(scenario())


def test_account_switch_during_second_personal_page_discards_old_completion(remote):
    entered, release = threading.Event(), threading.Event()
    remote.personal[A] = [task(id=uid(n+10000),user_id=A,title=f"Private A {n}") for n in range(1001)]
    remote.block = ("user_task",A,1000,entered,release)
    async def scenario():
        live = backend()
        live._access_tokens[B] = "token-" + B
        first = ClientUser(A,"A")
        controller = ClientController(live,first)
        old_session = controller.selection_session
        pending = asyncio.create_task(controller.load_month(MONTH))
        try:
            assert await asyncio.to_thread(entered.wait,10)
            controller.set_user(ClientUser(B,"B"))
            live.logout(first)
            await controller.load_month(MONTH)
            expected = controller.state.search_snapshot
        finally:
            release.set()
        await pending
        assert controller.state.search_snapshot is expected
        assert [r.title for r in controller.search("Private").hits] == ["Private B"]
        assert not controller.state.error and not controller.state.loading
        assert not controller.select_search_record(("personal",uid(10000)),session=old_session)
        assert A not in live._original_groups
        controller.logout()
        assert controller.selected_search_record is None and controller.search("").hits == ()
    asyncio.run(scenario())


def test_owner_creates_personal_and_assignment_types_without_changing_scope(remote):
    async def scenario():
        live = backend()
        user = ClientUser(A, "A")
        for kind, title in (("personal", "Custom appointment"), ("assignment", "Custom coursework")):
            result = await live.create_task(user, TaskDraft(title=title, kind=kind))
            assert result.ok
        controller = ClientController(live, user)
        await controller.load_month(MONTH)
        for kind, title in (("personal", "Custom appointment"), ("assignment", "Custom coursework")):
            controller.set_filter(kind)
            record = controller.search(title).hits[0]
            assert record.type == kind and record.scope == "personal"
            assert controller.select_search_record(record.key, session=controller.selection_session)
            assert controller.selected_search_record.title == title
            assert (await backend(B).load_tasks(ClientUser(B,"B"))).snapshot.get_task(record.key) is None
    asyncio.run(scenario())


def test_wrong_owner_response_is_rejected_before_overlay(remote):
    remote.personal[A] = [task(id=uid(4), user_id=B, title="Foreign private row")]
    async def scenario():
        controller = ClientController(backend(),ClientUser(A,"A"))
        await controller.load_month(MONTH)
        assert "another owner" in controller.state.error
        assert controller.search("").hits == ()
        assert not any(row[0] == "user_task_state" for row in remote.reads)
    asyncio.run(scenario())


def test_source_change_during_overlay_read_uses_one_enabled_set_for_both_views(remote):
    entered, release = threading.Event(), threading.Event()
    remote.block = ("user_task_state",A,0,entered,release)
    async def scenario():
        live = backend()
        user = ClientUser(A,"A")
        controller = ClientController(live,user)
        pending = asyncio.create_task(controller.load_month(MONTH))
        try:
            assert await asyncio.to_thread(entered.wait,10)
            await live.set_source_enabled(user,"Portal",False)
        finally:
            release.set()
        await pending
        assert controller.state.error is None
        assert controller.state.search_snapshot.loaded_scopes == ("public","personal")
        assert [record.key for record in controller.search("").hits] == [("public",uid(1))]
        assert all(value.source_platform != "Portal" for value in controller._loaded_tasks.tasks)
        assert len(task_reads(remote)) == 2
    asyncio.run(scenario())
