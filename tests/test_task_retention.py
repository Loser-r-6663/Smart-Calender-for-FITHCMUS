"""Authenticated retention, acknowledgement ordering and retry regressions."""

import asyncio
from datetime import date, datetime
from unittest.mock import Mock

import pytest

from Database.Repository.local_task_repository import LocalTaskRepository
from Database.Repository.user_task_repository import UserTaskRepository
from Database.task_sync import sync_owner_tasks
from DataProcessor.Standardization.User import User
from client.core.controller import ClientController
from client.core.live_backend import LiveBackend
from client.core.models import ClientUser
from test_search_records import task

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ID = "11111111-1111-4111-8111-111111111111"
RETAINED = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def remote(monkeypatch):
    from Database.Repository.task_repository import TaskRepository
    state = {'public': [task(title='Public')], 'personal': {A:[task(user_id=A,title='Private A')], B:[task(user_id=B,title='Private B')]},
             'gets': [], 'acks': [], 'fail_ack': False, 'commits': []}
    monkeypatch.setenv('SUPABASE_URL','https://example.invalid')
    monkeypatch.setenv('SUPABASE_PUBLIC_KEY','fictional-public')
    monkeypatch.setenv('SUPABASE_SECRET_KEY','server-key-must-not-be-used')
    original_ingest = LocalTaskRepository.ingest_sources
    def ingest(store, groups):
        result = original_ingest(store, groups)
        state['commits'].append(store.owner_id)
        return result
    monkeypatch.setattr(LocalTaskRepository,'ingest_sources',ingest)
    def get(url, *, params, headers, timeout):
        assert headers['apikey'] == 'fictional-public'
        owner = params.get('user_id','')[3:]
        state['gets'].append((url,owner,params['limit'],headers['Authorization']))
        values = state['personal'].get(owner,[]) if owner else state['public']
        if owner:
            assert headers['Authorization'] == f'Bearer token-{owner}'
        rows = [TaskRepository.task_to_row(item) | {'id':item.id, 'user_id':item.user_id} for item in values]
        return Mock(ok=True,json=lambda: rows)
    def delete(url, *, params, headers, timeout):
        owner, task_id = params['user_id'][3:], params['id'][3:]
        assert owner in (A,B) and url.endswith('/user_task')
        assert headers['Authorization'] == f'Bearer token-{owner}'
        assert state['commits'][-1] == owner
        with LocalTaskRepository(owner) as persisted:
            saved = persisted.get_task(('personal',task_id))
            assert saved is not None
        state['acks'].append((owner,task_id,params['updated_at']))
        if state['fail_ack']:
            raise RuntimeError('injected acknowledgement failure')
        state['personal'][owner] = [item for item in state['personal'][owner]
            if item.id != task_id or 'eq.' + item.updated_at.isoformat() != params['updated_at']]
        return Mock(ok=True)
    monkeypatch.setattr('requests.get',get)
    monkeypatch.setattr('requests.delete',delete)
    return state


def manager(owner=A):
    from user import UserManager
    result = UserManager.__new__(UserManager)
    result.user = User(id=owner,username=owner+'@example.invalid')
    result.access_token = 'token-'+owner
    return result


def backend(owner=A):
    result = LiveBackend()
    result._access_tokens[owner] = 'token-'+owner
    return result


def test_open_reads_committed_history_all_rows_then_interactions_and_months_do_not_read(remote, monkeypatch):
    with LocalTaskRepository(A) as store:
        retained = [task(id=f'{number:08x}-2222-4222-8222-222222222222',title=f'Retained {number}',user_id=A)
                    for number in range(125)]
        store.ingest_sources((('personal',retained),))
    async def scenario():
        live = backend()
        controller = ClientController(live,ClientUser(A,'A'))
        await controller.load_month(date(2026,11,1))
        assert len(remote['gets']) == 2 and len(remote['commits']) == 2
        assert len(controller.state.search_snapshot.records) == 127
        assert dict(controller.state.search_snapshot.row_limits) == {'public':1000,'personal':1000}
        assert len(controller.search('Retained').hits) == 125
        snapshot = controller.state.search_snapshot
        with monkeypatch.context() as context:
            context.setattr('sqlite3.connect',Mock(side_effect=AssertionError('Interaction opened SQLite')))
            context.setattr('requests.get',Mock(side_effect=AssertionError('Interaction read Supabase')))
            controller.search('Retained',filters={'types':['announcement']},sort='title')
            controller.search('')
            assert controller.select_search_record(('personal',retained[0].id),session=controller.selection_session)
            assert controller.selected_search_record.title == 'Retained 0'
            controller.show_month(date(2027,1,1))
            assert controller.state.search_snapshot is snapshot
        assert remote['acks'] == []
    asyncio.run(scenario())


def test_consumption_is_commit_then_owner_version_ack_retry_preserves_schedule_and_ui_history(remote):
    with LocalTaskRepository(A) as store:
        store.ingest_sources((('personal',remote['personal'][A]),))
        store.update_task(('personal',ID),{'status':'scheduled', 'start_time':{'date':'2026-01-02','time':'08:00:00'},
                                         'end_time':{'date':'2026-01-02','time':'09:00:00'}})
    remote['fail_ack'] = True
    with pytest.raises(RuntimeError,match='acknowledgement'):
        manager().get_tasks()
    assert remote['personal'][A]
    with LocalTaskRepository(A) as store:
        assert len(store.get_tasks()) == 2
        assert store.get_task(('personal',ID)).status == 'scheduled'
    remote['fail_ack'] = False
    tasks = manager().get_tasks()
    assert len(tasks) == 2 and remote['personal'][A] == []
    assert remote['personal'][B][0].title == 'Private B'
    assert all(owner == A and task_id == ID for owner,task_id,_ in remote['acks'])
    assert manager().get_tasks()[1].status == 'scheduled'
    async def scenario():
        loaded = await backend().load_tasks(ClientUser(A,'A'))
        records = {record.key:record for record in loaded.snapshot.records}
        assert records[('personal',ID)].title == 'Private A'
        assert records[('personal',ID)].start_time is None
        calendar = next(item for item in loaded.tasks if item.key == ('personal',ID))
        assert calendar.start_time.date == date(2026,1,2)
    asyncio.run(scenario())


def test_local_write_failure_rolls_back_and_never_acknowledges(remote):
    with LocalTaskRepository(A) as store:
        store.connection.execute("""CREATE TRIGGER fail_write BEFORE INSERT ON tasks
            BEGIN SELECT RAISE(ABORT, 'injected persistence failure'); END""")
    with pytest.raises(Exception,match='persistence failure'):
        manager().get_tasks()
    assert remote['acks'] == [] and remote['commits'] == []
    with LocalTaskRepository(A) as store:
        assert store.get_tasks() == []
    assert remote['personal'][A][0].id == ID


def test_guests_never_open_owner_stores_and_accounts_keep_collisions_isolated(remote,monkeypatch):
    async def scenario():
        with monkeypatch.context() as context:
            context.setattr('Database.Repository.local_task_repository.LocalTaskRepository',Mock(side_effect=AssertionError('Guest opened owner store')))
            guest = await backend().load_tasks(None)
            assert [r.key for r in guest.snapshot.records] == [('public',ID)]
        first = ClientController(backend(),ClientUser(A,'A'))
        await first.load_month()
        assert [r.key for r in first.search('').hits] == [('personal',ID),('public',ID)]
        assert first.select_search_record(('personal',ID),session=first.selection_session)
        old_session = first.selection_session
        live_b = first.backend
        live_b._access_tokens[B] = 'token-'+B
        first.set_user(ClientUser(B,'B'))
        await first.load_month()
        assert not first.select_search_record(('personal',ID),session=old_session)
        assert first.selected_search_record is None
        assert [r.title for r in first.search('Private').hits] == ['Private B']
        first.logout()
        assert first.search('').hits == ()
    asyncio.run(scenario())


def test_disabled_sources_expired_scheduled_and_unscheduled_consumed_history(remote):
    expired = task(id=RETAINED,title='Expired scheduled source',user_id=A,deadline='2000-01-01T08:00:00+07:00',source_platform='Moodle')
    remote['personal'][A].append(expired)
    manager().get_tasks()
    with LocalTaskRepository(A) as store:
        store.update_task(('personal',RETAINED),{'status':'scheduled'})
    async def scenario():
        live = backend()
        loaded = await live.load_tasks(ClientUser(A,'A'))
        assert len(loaded.snapshot.records) == 3
        assert {r.title for r in loaded.snapshot.records} == {'Public','Private A','Expired scheduled source'}
        await live.set_source_enabled(ClientUser(A,'A'),'Moodle',False)
        hidden = await live.load_tasks(ClientUser(A,'A'))
        assert 'Expired scheduled source' not in [r.title for r in hidden.snapshot.records]
        await live.set_source_enabled(ClientUser(A,'A'),'Moodle',True)
        assert 'Expired scheduled source' in [r.title for r in (await live.load_tasks(ClientUser(A,'A'))).snapshot.records]
    asyncio.run(scenario())


def test_consumption_requires_pair_and_never_acknowledges_unpersisted_or_other_owner_rows(remote):
    with pytest.raises(ValueError):
        sync_owner_tasks(A,'',consume=True)
    assert remote['gets'] == []
    repo = UserTaskRepository(supabase_url='https://example.invalid',supabase_key='fictional-public',access_token='token-'+A,user_id=A)
    repo.pop_tasks(persist=lambda tasks: set())
    assert remote['acks'] == []
    with pytest.raises(ValueError):
        repo.acknowledge_tasks([task(user_id=B)])
    assert remote['acks'] == []


def test_scheduler_preserves_scoped_schedules_and_applies_expiry_without_deleting_history(remote,monkeypatch):
    import Scheduler.scheduler as module
    import DataProcessor.Validator as validation
    class ClockType(type):
        def __instancecheck__(cls,value):
            return isinstance(value,datetime)
    class Clock(datetime,metaclass=ClockType):
        @classmethod
        def now(cls,tz=None):
            return cls(2026,11,25,9,tzinfo=tz)
    monkeypatch.setattr(module,'datetime',Clock)
    monkeypatch.setattr(validation,'datetime',Clock)
    public = task(type='class',title='Public fixed class',start_time={'date':'2026-11-26','time':'09:00:00'},
                  end_time={'date':'2026-11-26','time':'10:00:00'})
    personal = task(type='class',title='Personal fixed class',user_id=A,start_time={'date':'2026-11-26','time':'11:00:00'},
                    end_time={'date':'2026-11-26','time':'12:00:00'})
    expired = task(id=RETAINED,title='Expired unscheduled',type='class',user_id=A,
                   start_time={'date':'2000-01-01','time':'09:00:00'},end_time={'date':'2000-01-01','time':'10:00:00'})
    remote['public'] = [public]
    remote['personal'][A] = [personal,expired]
    first = manager()
    first.user_repo = Mock()
    result = first.schedule_tasks()
    assert {item.key for item in result.scheduled_tasks} == {('public',ID),('personal',ID)}
    with LocalTaskRepository(A) as store:
        assert len(store.get_tasks()) == 3
        assert store.get_task(('personal',RETAINED)).status == 'proposed'
        assert store.get_task(('personal',ID)).status == 'scheduled'
        store.update_task(('personal',ID), {'scheduled_occurrences':[
            {'start_time':{'date':'2026-11-26','time':'11:00:00'},'end_time':{'date':'2026-11-26','time':'12:00:00'}},
            {'start_time':{'date':'2026-11-27','time':'11:00:00'},'end_time':{'date':'2026-11-27','time':'12:00:00'}},
        ]})
        original = store.get_task(('personal',ID)).model_dump(mode='json')
    second = manager()
    second.user_repo = Mock()
    repeated = second.schedule_tasks()
    assert sorted(item.start_time.date.day for item in repeated.scheduled_tasks if item.scope == 'personal') == [26,27]
    with LocalTaskRepository(A) as store:
        assert len(store.get_tasks()) == 3
        assert store.get_task(('personal',ID)).model_dump(mode='json') == original
        assert len(store.get_verified_tasks()) == 3
    assert all(owner == A for owner,_,_ in remote['acks'])


def test_shared_path_is_independent_of_process_working_directory(monkeypatch,tmp_path):
    monkeypatch.setenv('LOCAL_TASK_DB_DIR','Database/data')
    before = LocalTaskRepository.path_for_owner(A)
    monkeypatch.chdir(tmp_path)
    assert LocalTaskRepository.path_for_owner(A) == before


def test_remote_newer_version_is_not_acknowledged_by_an_older_durable_copy(remote):
    original = remote['personal'][A][0]
    repo = UserTaskRepository(supabase_url='https://example.invalid',supabase_key='fictional-public',access_token='token-'+A,user_id=A)
    def persist(values):
        with LocalTaskRepository(A) as store:
            ids = store.ingest_sources((('personal',values),))
        remote['personal'][A] = [original.model_copy(update={'updated_at':datetime.fromisoformat('2027-01-01T09:00:00+07:00')})]
        return ids
    repo.pop_tasks(persist=persist)
    assert remote['personal'][A][0].updated_at.year == 2027


def test_failed_local_commit_rolls_back_without_acknowledgement(remote,monkeypatch):
    import sqlite3
    original = LocalTaskRepository.ingest_sources
    def fail_commit(store,groups):
        def authorize(action, first, second, database, trigger):
            if action == sqlite3.SQLITE_TRANSACTION and first == 'COMMIT':
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        store.connection.set_authorizer(authorize)
        try:
            return original(store,groups)
        finally:
            store.connection.set_authorizer(None)
    monkeypatch.setattr(LocalTaskRepository,'ingest_sources',fail_commit)
    with pytest.raises(sqlite3.DatabaseError):
        manager().get_tasks()
    assert remote['acks'] == []
    with LocalTaskRepository(A) as store:
        assert store.get_tasks() == []
