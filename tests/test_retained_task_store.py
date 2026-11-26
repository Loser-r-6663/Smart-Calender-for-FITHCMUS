"""Scoped owner-store migration and source/schedule separation checks."""

import json
import sqlite3
from datetime import date

import pytest

from DataProcessor.Standardization.Task import Task
from DataProcessor.Standardization.BaseTask import DateDayTime
from Database.Repository.local_task_repository import LocalTaskRepository
from client.core.controller import TaskMapper
from test_search_records import task

OWNER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ID = "11111111-1111-4111-8111-111111111111"


def test_scoped_identity_updates_deletion_owner_validation_and_independent_source_facts(tmp_path):
    public = task(title="Public source")
    personal = task(title="Personal source", user_id=OWNER)
    with LocalTaskRepository(OWNER, tmp_path) as store:
        store.ingest_sources((("public", [public]), ("personal", [personal])))
        assert [item.key for item in store.get_tasks()] == [("public", ID), ("personal", ID)]
        saved = store.update_task(("personal", ID), {"status": "scheduled",
            "start_time": {"date": "2026-11-26", "time": "10:00:00"},
            "end_time": {"date": "2026-11-26", "time": "11:00:00"}})
        store.ingest_sources((("personal", [personal.model_copy(update={"title": "Changed original"})]),))
        assert store.get_task(("personal", ID)).status == "scheduled"
        assert store.get_task(("personal", ID)).start_time.date == date(2026, 11, 26)
        assert store.get_task(("personal", ID)).title == "Changed original"
        _, original, calendar = store.get_verified_tasks()[1]
        assert original.start_time is None
        assert calendar.start_time.time.hour == 10
        store.delete_tasks([saved])
        assert store.get_task(("personal", ID)) is None
        assert store.get_task(("public", ID)).title == "Public source"
        with pytest.raises(ValueError):
            store.update_task(ID, {})
        with pytest.raises(ValueError):
            store.save_tasks([saved.model_copy(update={"owner_id": "other"})])
        with pytest.raises(ValueError):
            store.ingest_sources((("personal", [task(user_id="other")]),))
        assert len(store.get_tasks()) == 1


def legacy_database(tmp_path):
    path = LocalTaskRepository.path_for_owner(OWNER, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = Task.from_extracted_task(task(title="Legacy scheduled", deadline="2026-01-01T09:00:00+07:00"))
    data.status = "scheduled"
    data.start_time = DateDayTime(date="2025-12-31", time="08:00:00")
    data.end_time = DateDayTime(date="2025-12-31", time="09:00:00")
    payload = data.model_dump(mode="json")
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY, title TEXT, start_time TEXT, end_time TEXT, status TEXT, payload TEXT)")
        connection.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?)", (ID, payload['title'],
            json.dumps(payload['start_time']), json.dumps(payload['end_time']), payload['status'], json.dumps(payload)))
    return path, payload


def test_transactional_legacy_migration_preserves_schedule_and_never_guesses_scope(tmp_path):
    path, payload = legacy_database(tmp_path)
    for _ in range(2):
        with LocalTaskRepository(OWNER, tmp_path) as store:
            legacy = store.get_tasks()[0]
            assert legacy.key == ("unknown", ID)
            assert legacy.status == "scheduled"
            assert legacy.start_time.date == date(2025,12,31)
            assert legacy.end_time.time.hour == 9
            assert store.get_verified_tasks() == []
            assert json.loads(store.connection.execute("SELECT legacy_row FROM tasks").fetchone()[0])['payload'] == json.dumps(payload)
    with LocalTaskRepository(OWNER, tmp_path) as store:
        store.ingest_sources((("public", [task()]), ("personal", [task(user_id=OWNER)])))
        assert len(store.get_tasks()) == 3
        assert store.get_task(("unknown", ID)).status == "scheduled"
        assert len(store.get_verified_tasks()) == 2
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE store_owner SET owner_id='other'")
    with pytest.raises(ValueError, match="another owner"):
        LocalTaskRepository(OWNER, tmp_path)


def test_failed_migration_rolls_back_and_retries_without_losing_legacy_table(monkeypatch, tmp_path):
    path, _ = legacy_database(tmp_path)
    original = LocalTaskRepository._create_tasks
    def fail(store):
        original(store)
        raise RuntimeError("injected migration failure")
    with monkeypatch.context() as context:
        context.setattr(LocalTaskRepository, '_create_tasks', fail)
        with pytest.raises(RuntimeError):
            LocalTaskRepository(OWNER, tmp_path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT status FROM tasks").fetchone()[0] == 'scheduled'
        assert not connection.execute("SELECT name FROM sqlite_master WHERE name='tasks_legacy'").fetchall()
    with LocalTaskRepository(OWNER, tmp_path) as store:
        assert store.get_tasks()[0].key == ('unknown', ID)


def test_ingestion_rollback_keeps_existing_facts_and_schedules(tmp_path):
    with LocalTaskRepository(OWNER, tmp_path) as store:
        store.ingest_sources((("personal", [task(user_id=OWNER)]),))
        store.update_task(('personal', ID), {'status': 'scheduled'})
        store.connection.execute("""CREATE TRIGGER fail_ingest BEFORE INSERT ON tasks
            WHEN NEW.id != '11111111-1111-4111-8111-111111111111'
            BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
        with pytest.raises(sqlite3.IntegrityError):
            store.ingest_sources((('personal', [task(title='Should roll back'),
                task(id='22222222-2222-4222-8222-222222222222')]),))
        assert store.get_task(('personal', ID)).title == 'Sinh hoạt sinh viên'
        assert store.get_task(('personal', ID)).status == 'scheduled'
        assert len(store.get_tasks()) == 1


def test_all_retained_rows_and_split_schedule_occurrences_survive_source_refresh(tmp_path):
    records = [task(id=f"{number:08x}-1111-4111-8111-111111111111", title=f"Fictional {number}") for number in range(135)]
    with LocalTaskRepository(OWNER, tmp_path) as store:
        store.ingest_sources((('personal', records),))
        current = store.get_tasks()[0]
        current.status = 'scheduled'
        first = current.model_copy(update={'start_time': {'date':'2026-11-26','time':'08:00:00'},
                                         'end_time': {'date':'2026-11-26','time':'09:00:00'}})
        second = current.model_copy(update={'start_time': {'date':'2026-11-26','time':'14:00:00'},
                                          'end_time': {'date':'2026-11-26','time':'15:00:00'}})
        store.save_schedule([current], [first,second])
        store.ingest_sources((('personal', records),))
        saved = store.get_tasks()[0]
        assert len(saved.scheduled_occurrences) == 2
        items = TaskMapper.map_range(saved, date(2026,11,1), date(2026,11,30))
        assert [item.start.hour for item in items] == [8,14]
        assert len({item.id for item in items}) == 2
        assert len(store.get_verified_tasks()) == len(store.get_tasks()) == 135


def test_source_updates_refresh_unscheduled_times_instead_of_treating_them_as_saved_schedules(tmp_path):
    old = task(end_time={'date': '2000-01-01', 'time': '10:00:00'})
    fresh = task(end_time={'date': '2099-01-01', 'time': '11:00:00'})
    with LocalTaskRepository(OWNER, tmp_path) as store:
        store.ingest_sources((('personal', [old]),))
        store.save_tasks(store.get_tasks())
        store.ingest_sources((('personal', [fresh]),))
        current = store.get_task(('personal', ID))
        assert current.status == 'proposed'
        assert current.end_time.date == date(2099, 1, 1)
        assert current.end_time.time.hour == 11
