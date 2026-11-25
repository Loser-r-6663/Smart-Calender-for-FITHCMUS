"""Actual NiceGUI open/Sync using the live adapter and temporary owner SQLite."""

import pytest
from playwright.sync_api import expect
from test_search_ui import APP, PERSONAL, OFF_MONTH, page, serve_ui, fictional_tasks, submit, choose, close_details

OWNER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
LIVE_SETUP = r"""
from client.core.live_backend import LiveBackend
from DataProcessor.Standardization.User import User
from Database.Repository.local_task_repository import LocalTaskRepository
from Database.Repository.task_repository import TaskRepository
from Database.Repository.user_task_repository import UserTaskRepository
from Database.Repository.user_task_state_repository import UserTaskStateRepository
from Scheduler.scheduler import BranchAndBoundScheduler
import client.core.personal_crawl as personal_crawl
import sqlite3

OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
os.environ['SUPABASE_PUBLIC_KEY'] = 'fictional-public-key'
os.environ['SUPABASE_URL'] = 'https://example.invalid'
counts = {'ingestions':0, 'sqlite':0, 'crawls':0}
real_connect = sqlite3.connect
def connect(*args, **kwargs):
    connection = real_connect(*args, **kwargs)
    def trace(sql): counts['sqlite'] += 1
    connection.set_trace_callback(trace)
    return connection
sqlite3.connect = connect
real_ingest = LocalTaskRepository.ingest_sources
def ingest(store, groups):
    counts['ingestions'] += 1
    return real_ingest(store, groups)
LocalTaskRepository.ingest_sources = ingest
backend = LiveBackend()
backend.fixture_path = Path(os.environ['SEARCH_UI_FIXTURE'])
backend.reads = 0
backend._access_tokens[OWNER] = 'fictional-session'
backend._users[OWNER] = User(id=OWNER,username='student',portal_username='fictional',portal_password='fictional',portal_session='{}')
def read(repo, limit):
    backend.reads += 1
    assert repo.headers['apikey'] == 'fictional-public-key'
    personal = isinstance(repo, UserTaskRepository)
    if personal:
        assert repo.user_id == OWNER
        assert repo.headers['Authorization'] == 'Bearer fictional-session'
    values = json.loads(backend.fixture_path.read_text(encoding='utf-8'))
    return [ExtractedTask.model_validate(value) for value in values if bool(value.get('user_id')) == personal][:limit]
TaskRepository.get_tasks = read
UserTaskRepository.get_tasks = read
UserTaskStateRepository.get_task_states = lambda self, tasks: {}
def prohibited(*args, **kwargs): raise AssertionError('UI consumed/deleted tasks or invoked scheduler')
UserTaskRepository.pop_tasks = prohibited
UserTaskRepository.delete_tasks = prohibited
UserTaskRepository.acknowledge_tasks = prohibited
BranchAndBoundScheduler.schedule = prohibited
def crawl(*args):
    counts['crawls'] += 1
    return 0,0
personal_crawl.run_personal_crawl = crawl
"""


@pytest.fixture(scope='module')
def ui_server(tmp_path_factory):
    start = APP.index('class CountingBackend')
    end = APP.index('baseline =')
    code = APP[:start] + LIVE_SETUP + APP[end:]
    code = code.replace('ClientUser("demo-user", "student", True, True)', f'ClientUser("{OWNER}", "student", True, True)')
    code = code.replace('return {"reads": backend.reads, "selected": keys}',
                        'return {"reads": backend.reads, "selected": keys, "counts": dict(counts)}')
    extension = r"""
@app.post('/remove-remote-personal')
def remove_personal():
    values = json.loads(backend.fixture_path.read_text(encoding='utf-8'))
    backend.fixture_path.write_text(json.dumps([value for value in values if not value.get('user_id')]),encoding='utf-8')
    return {'ok':True}
"""
    code = code.replace('ui.run(host=', extension + '\nui.run(host=')
    tasks = fictional_tasks()
    for value in tasks:
        if value.get('user_id'):
            value['user_id'] = OWNER
            if value['title'] == 'Beta drive':
                value['deadline'] = '2000-01-01T09:00:00+07:00'
    with serve_ui(tmp_path_factory.mktemp('retention-ui'),code,tasks) as url:
        yield url


def test_actual_open_sync_retained_details_and_month_navigation_reuse_snapshot(page,ui_server):
    def state(): return page.request.get(ui_server+'/test-state').json()
    first = state()
    assert first['reads'] == 2 and first['counts']['ingestions'] == 1
    page.request.post(ui_server+'/remove-remote-personal')
    old_id = page.locator('.search-results').get_attribute('id')
    page.get_by_role('button',name='Run personal crawl',exact=True).click()
    expect(page.locator('.search-results')).not_to_have_attribute('id',old_id)
    expect(page.get_by_text('6 tasks · Soonest deadline',exact=True)).to_be_visible()
    after = state()
    assert after['reads'] == 4
    assert after['counts']['ingestions'] == 2 and after['counts']['crawls'] == 1
    submit(page,'Beta')
    expect(page.locator('.search-result')).to_have_count(1)
    choose(page,'Sort','Title A–Z')
    page.locator(f'[data-search-key="{PERSONAL}"]').click()
    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Beta drive')
    expect(page.locator('.search-detail-dialog').get_by_text('Deadline: 01 Jan 2000, 09:00 (Vietnam)',exact=True)).to_be_visible()
    close_details(page)
    page.locator('.search-query-row').get_by_role('button',name='Clear',exact=True).click()
    expect(page.locator('.search-result')).to_have_count(6)
    for month in ('December 2026','January 2027'):
        page.locator('.month-controls button').nth(1).click()
        expect(page.locator('.month-label')).to_have_text(month)
    expect(page.locator('.event-pill').filter(has_text='Off-month report')).to_be_visible()
    page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Off-month report')
    close_details(page)
    last = state()
    assert last['reads'] == after['reads']
    assert last['counts']['sqlite'] == after['counts']['sqlite']
    assert last['counts']['ingestions'] == 2

    page.goto(ui_server+'/calendar')
    expect(page.locator('.search-result')).to_have_count(6)
    reopened = state()
    assert reopened['reads'] == 6 and reopened['counts']['ingestions'] == 3
    assert reopened['counts']['crawls'] == 1
