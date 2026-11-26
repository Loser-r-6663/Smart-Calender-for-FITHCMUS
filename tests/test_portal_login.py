"""Portal login integration uses mocked browser I/O and fictional owner state."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from DataProcessor.Crawler.BaseCrawler.PlaywrightCrawler import PlaywrightCrawler
from DataProcessor.Crawler.PortalCrawler import PortalCrawler
from DataProcessor.Standardization.User import User


class FictionalUser(User):
    def __repr__(self):
        return '<fictional owner>'

    __str__ = __repr__


def login_environment(monkeypatch, tmp_path, *, role='CLIENT', owner='owner-a'):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('DataProcessor.Crawler.PortalCrawler.APP_ROLE', role)
    prior = {'cookies': [], 'origins': []}
    user = FictionalUser(id=owner, portal_username='fictional-account',
                         portal_password='fictional-password', portal_session=json.dumps(prior))
    crawler = PortalCrawler(user)
    controls = {name: Mock() for name in ('username', 'password', 'submit', 'body')}
    controls['body'].inner_text.return_value = 'Controlled sign-in page'

    def locate(selector):
        if 'txtUsername' in selector:
            return controls['username']
        if 'txtPassword' in selector:
            return controls['password']
        return controls['body' if selector == 'body' else 'submit']

    def wait(predicate, *, timeout):
        assert predicate(crawler.home_url + '?view=registered')
        assert not predicate(crawler.login_url)
        assert timeout == (30_000 if role == 'SERVER' else 120_000)

    page = SimpleNamespace(url=crawler.login_url, locator=locate, wait_for_url=Mock(side_effect=wait))
    fresh = {'cookies': [], 'origins': [{'origin': 'https://portal.invalid', 'localStorage': []}]}

    def storage_state(*, path=None):
        if path is not None:
            Path(path).write_text(json.dumps(fresh), encoding='utf-8')
        return fresh

    context = SimpleNamespace(storage_state=Mock(side_effect=storage_state))
    browser = SimpleNamespace(close=Mock())
    launched_settings = []

    def launch(url, settings):
        launched_settings.append(json.loads(json.dumps(settings)))
        return page, context, browser

    crawler.launch_engine = Mock(side_effect=launch)
    return SimpleNamespace(crawler=crawler, user=user, page=page, context=context,
                           browser=browser, controls=controls, fresh=fresh, prior=prior,
                           launched_settings=launched_settings)


@pytest.mark.parametrize('role', ['CLIENT', 'SERVER'])
def test_authenticate_preserves_owner_loader_waits_and_role_persistence(monkeypatch, tmp_path, role):
    env = login_environment(monkeypatch, tmp_path, role=role)
    env.crawler.authenticate()
    settings = env.launched_settings[0]
    loaded_owner_state = settings['storage_state'] == env.prior
    state_refreshed = env.crawler.state == env.fresh
    credentials_forwarded = (
        env.controls['username'].fill.call_args.args == (env.user.portal_username,)
        and env.controls['password'].fill.call_args.args == (env.user.portal_password,)
    )
    assert loaded_owner_state and state_refreshed and credentials_forwarded
    assert settings['headless'] == (role == 'SERVER')
    env.page.wait_for_url.assert_called_once()
    env.browser.close.assert_called_once_with()
    kwargs = env.context.storage_state.call_args.kwargs
    if role == 'SERVER':
        assert kwargs == {}
        assert not Path('DataProcessor/Crawler/State').exists()
    else:
        file = Path(kwargs['path'])
        assert file.name == f'{env.crawler.state_key}.json'
        assert file.resolve().is_relative_to(tmp_path)
        persisted_owner_state = json.loads(file.read_text(encoding='utf-8')) == env.fresh
        assert persisted_owner_state


def test_callers_derive_distinct_owner_keys_without_reading_global_session(monkeypatch, tmp_path):
    env = login_environment(monkeypatch, tmp_path)
    from DataProcessor.TaskCreator import TaskCreator

    other = FictionalUser(id='owner-b', portal_session=json.dumps({'cookies': [], 'origins': []}))
    a = TaskCreator(env.user).crawlers(env.user)['Portal']
    b = TaskCreator(other).crawlers(other)['Portal']
    assert a.state_key == PortalCrawler(env.user).state_key
    assert a.state_key != b.state_key
    global_file = Path('DataProcessor/Crawler/State/PortalState.json')
    global_file.write_text('{}', encoding='utf-8')
    from_owner_record = a.get_state() == json.loads(env.user.portal_session)
    assert from_owner_record
    env.crawler.authenticate()
    assert global_file.read_text(encoding='utf-8') == '{}'


def test_missing_owner_never_writes_a_shared_state_file(monkeypatch, tmp_path):
    env = login_environment(monkeypatch, tmp_path, owner=None)
    env.crawler.authenticate()
    assert env.crawler.state_key is None
    env.context.storage_state.assert_called_once_with()
    assert not Path('DataProcessor/Crawler/State').exists()
    env.browser.close.assert_called_once_with()


def test_already_authenticated_page_closes_without_login_or_file_write(monkeypatch, tmp_path):
    env = login_environment(monkeypatch, tmp_path)
    env.page.url = env.crawler.home_url
    env.crawler.authenticate()
    env.page.wait_for_url.assert_not_called()
    env.context.storage_state.assert_not_called()
    env.controls['username'].fill.assert_not_called()
    env.browser.close.assert_called_once_with()


@pytest.mark.parametrize('stage', ['fill', 'click', 'wait', 'diagnostics', 'storage', 'directory'])
def test_login_failure_always_closes_browser(monkeypatch, tmp_path, stage):
    env = login_environment(monkeypatch, tmp_path)
    expected = RuntimeError
    if stage == 'fill':
        env.controls['username'].fill.side_effect = RuntimeError('Controlled form failure')
    elif stage == 'click':
        env.controls['submit'].click.side_effect = RuntimeError('Controlled submit failure')
    elif stage in ('wait', 'diagnostics'):
        env.page.wait_for_url.side_effect = TimeoutError('Controlled navigation timeout')
        expected = AssertionError
        if stage == 'diagnostics':
            env.controls['body'].inner_text.side_effect = RuntimeError('Controlled diagnostic failure')
    elif stage == 'storage':
        env.context.storage_state.side_effect = OSError('Controlled state save failure')
        expected = OSError
    else:
        monkeypatch.setattr(Path, 'mkdir', Mock(side_effect=PermissionError('Controlled directory failure')))
        expected = PermissionError
    with pytest.raises(expected) as caught:
        env.crawler.authenticate()
    if stage in ('wait', 'diagnostics'):
        assert str(caught.value).startswith('Portal login failed before reaching the timetable page')
        assert isinstance(caught.value.__cause__, TimeoutError)
    env.browser.close.assert_called_once_with()


@pytest.mark.parametrize('stage', ['launch', 'context', 'page', 'navigation'])
def test_partial_browser_initialization_is_closed(stage):
    crawler = PlaywrightCrawler()
    crawler.state = {'cookies': [], 'origins': []}
    page = Mock()
    context = Mock()
    browser = Mock()
    browser.new_context.return_value = context
    context.new_page.return_value = page
    launch = Mock(return_value=browser)
    crawler.crawler = SimpleNamespace(chromium=SimpleNamespace(launch=launch))
    failing = {'launch': launch, 'context': browser.new_context,
               'page': context.new_page, 'navigation': page.goto}[stage]
    failing.side_effect = RuntimeError('Controlled browser initialization failure')
    with pytest.raises(RuntimeError):
        crawler.launch_engine('https://portal.invalid')
    if stage == 'launch':
        browser.close.assert_not_called()
    else:
        browser.close.assert_called_once_with()
