"""Independent legacy SQLite consumption utilities, unused by the active client."""
from datetime import datetime
from unittest.mock import Mock
import pytest
from Database.Repository.local_task_repository import LocalTaskRepository
from Database.Repository.user_task_repository import UserTaskRepository
from Database.task_sync import sync_owner_tasks
from test_search_records import task
A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ID = "11111111-1111-4111-8111-111111111111"


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
        if url.endswith('/user_task_state'):
            assert owner in (A, B)
            assert headers['Authorization'] == f'Bearer token-{owner}'
            return Mock(ok=True, json=lambda: [])
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
