from test_search_ui import close_search
from test_search_ui import open_search
"""Actual NiceGUI open/Sync through paginated Supabase originals, without SQLite."""

import pytest
from playwright.sync_api import expect
from test_search_ui import APP, OFF_MONTH, page, serve_ui, fictional_tasks, submit, choose, close_details

OWNER = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PERSONAL = "personal:66666666-6666-4666-8666-666666666666"
LIVE_SETUP = r"""
from client.core.live_backend import LiveBackend
from DataProcessor.Standardization.User import User
from Scheduler.scheduler import BranchAndBoundScheduler
from Database.Repository.user_task_repository import UserTaskRepository
from Database.Repository.task_repository import TaskRepository
import client.core.personal_crawl as personal_crawl
import requests
import sqlite3

OWNER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
os.environ['SUPABASE_PUBLIC_KEY'] = 'fictional-public-key'
os.environ['SUPABASE_URL'] = 'https://example.invalid'
counts = {'sqlite':0, 'crawls':0, 'deletes':0, 'schedules':0}
states = {}
backend = LiveBackend()
backend.fixture_path = Path(os.environ['SEARCH_UI_FIXTURE'])
backend.reads = 0
backend._access_tokens[OWNER] = 'fictional-session'
backend._users[OWNER] = User(id=OWNER,username='student',portal_username='fictional',portal_password='fictional',portal_session='{}')

def read(url, *, params, headers, timeout):
    assert headers['apikey'] == 'fictional-public-key'
    route = url.rsplit('/',1)[1]
    if route != 'tasks':
        assert params['user_id'] == 'eq.' + OWNER
        assert headers['Authorization'] == 'Bearer fictional-session'
    if route == 'user_task_state':
        return response([{'id':key, **value} for key,value in states.items()])
    backend.reads += 1
    assert params['limit'] == 1000 and params['order'] == 'id.asc'
    values = json.loads(backend.fixture_path.read_text(encoding='utf-8'))
    personal = route == 'user_task'
    values = [value for value in values if bool(value.get('user_id')) == personal]
    rows = [TaskRepository.task_to_row(ExtractedTask.model_validate(value)) |
            {'id':value['id'], 'user_id':value.get('user_id')}
            for value in values[params['offset']:params['offset']+params['limit']]]
    return response(rows)

def response(values):
    from types import SimpleNamespace
    return SimpleNamespace(ok=True, json=lambda:values)

requests.get = read

def prohibited(kind):
    def call(*args, **kwargs):
        counts[kind] += 1
        raise AssertionError('UI opened SQLite, consumed/deleted tasks or invoked scheduler')
    return call
sqlite3.connect = prohibited('sqlite')
requests.delete = prohibited('deletes')
UserTaskRepository.pop_tasks = prohibited('deletes')
UserTaskRepository.delete_tasks = prohibited('deletes')
UserTaskRepository.acknowledge_tasks = prohibited('deletes')
BranchAndBoundScheduler.schedule = prohibited('schedules')

def crawl(user, token, enabled):
    assert user.id == OWNER and token == 'fictional-session' and 'Portal' in enabled
    counts['crawls'] += 1
    values = json.loads(backend.fixture_path.read_text(encoding='utf-8'))
    if not any(value['title'] == 'Fresh Portal coursework' for value in values):
        values.append({**values[0], 'id':'77777777-7777-4777-8777-777777777777',
            'user_id':OWNER, 'title':'Fresh Portal coursework', 'type':'assignment',
            'source_platform':'Portal', 'source_url':'https://example.invalid/new-portal',
            'training_points':None, 'training_point_category':None,
            'deadline':'2027-01-15T09:00:00+07:00'})
        backend.fixture_path.write_text(json.dumps(values),encoding='utf-8')
        return 1,3
    return 0,3
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
    tasks = fictional_tasks()
    for value in tasks:
        if value.get('user_id'):
            value['user_id'] = OWNER
            if value['title'] == 'Beta drive':
                value['id'] = PERSONAL.split(':')[1]
                value['deadline'] = '2000-01-01T09:00:00+07:00'
    with serve_ui(tmp_path_factory.mktemp('supabase-ui'),code,tasks) as url:
        yield url


def test_actual_open_sync_original_details_and_month_navigation_reuse_snapshot(page,ui_server):
    def state(): return page.request.get(ui_server+'/test-state').json()
    first = state()
    assert first['reads'] == 2
    old_id = page.locator('.search-results').get_attribute('id')
    close_search(page)
    page.get_by_role('button',name='Run personal crawl',exact=True).click()
    expect(page.get_by_text('Personal calendar refreshed:',exact=False)).to_be_visible()
    open_search(page)
    expect(page.locator('.search-results')).not_to_have_attribute('id',old_id)
    expect(page.get_by_text('7 tasks · Soonest deadline',exact=True)).to_be_visible()
    after = state()
    assert after['reads'] == 4 and after['counts']['crawls'] == 1
    submit(page,'Fresh Portal')
    expect(page.locator('.search-result')).to_have_count(1)
    page.locator('.search-result').click()
    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Fresh Portal coursework')
    expect(page.locator('.search-detail-dialog .source-link')).to_have_attribute('href','https://example.invalid/new-portal')
    close_details(page)
    submit(page,'Weekly class')
    expect(page.locator('.search-result')).to_have_count(1)
    page.locator('.search-result').click()
    expect(page.locator('.search-detail-dialog').get_by_text('Scheduled start: Every Monday, 08:00',exact=True)).to_be_visible()
    expect(page.locator('.search-detail-dialog').get_by_text('Date not provided',exact=True)).to_be_visible()
    close_details(page)
    submit(page,'Beta')
    expect(page.locator('.search-result')).to_have_count(1)
    choose(page,'Sort','Title A–Z')
    page.locator(f'[data-search-key="{PERSONAL}"]').click()
    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Beta drive')
    expect(page.locator('.search-detail-dialog').get_by_text('Deadline: 01 Jan 2000, 09:00 (Vietnam)',exact=True)).to_be_visible()
    close_details(page)
    previous_query_id = page.get_by_label("Query", exact=True).get_attribute("id")
    page.locator('.search-query-row').get_by_role('button',name='Clear',exact=True).click()
    expect(page.get_by_label("Query", exact=True)).not_to_have_attribute("id", previous_query_id)
    page.get_by_label("Query", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.get_by_label("Query", exact=True).press("Enter")
    expect(page.locator('.search-result')).to_have_count(7)
    for month in ('December 2026','January 2027'):
        close_search(page)
        old_trigger = page.get_by_role("button", name="Search tasks", exact=True).get_attribute("id")
        page.locator('.month-controls button').nth(1).click()
        expect(page.get_by_role("button", name="Search tasks", exact=True)).not_to_have_attribute("id", old_trigger)
        page.wait_for_timeout(200)
        open_search(page)
        expect(page.locator('.month-label')).to_have_text(month)
    expect(page.locator('.event-pill').filter(has_text='Off-month report')).to_be_visible()
    page.locator(f'[data-search-key="{OFF_MONTH}"]').click()
    expect(page.locator('.search-detail-dialog .detail-title')).to_have_text('Off-month report')
    expect(page.locator('.search-detail-dialog').get_by_text('Scheduled start: 16 Jan 2027, 09:00',exact=True)).to_be_visible()
    expect(page.locator('.search-detail-dialog').get_by_text('0 training points',exact=True)).to_be_visible()
    close_details(page)
    last = state()
    assert last["reads"] == after["reads"] and last["counts"] == after["counts"]
    assert last['counts'] == {'sqlite':0, 'crawls':1, 'deletes':0, 'schedules':0}
    page.goto(ui_server+'/calendar')
    open_search(page)
    page.get_by_label("Query", exact=True).wait_for(state="visible")
    page.wait_for_function("window.did_handshake === true")
    page.get_by_label("Query", exact=True).press("Enter")
    expect(page.locator('.search-result')).to_have_count(7)
    reopened = state()
    assert reopened['reads'] == 6 and reopened['counts'] == last['counts']
