"""Deterministic cache lifecycle checks; real latency is measured separately."""

import asyncio
import json
import threading
from dataclasses import replace
from datetime import date
from unittest.mock import AsyncMock

from academic_search import SearchSnapshot
from academic_search.semantic import HybridSearch
from client.core.backend import SessionExpiredError, TaskLoad
from client.core.controller import ClientController
from client.core.mock_backend import MockBackend
from client.core.models import ClientUser
from fixtures.search_semantic.run_keyword import load_inputs


import pytest
pytestmark = pytest.mark.search_core

class Encoder:
    def __init__(self):
        self.calls = []
        self.fail = False

    def encode(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError('fictional inference failure')
        return [[0., 1.] if 'excluded wording' in text else [1., 0.] for text in texts]

    def passages(self):
        return sum(t.startswith('passage: ') for call in self.calls for t in call)


def records():
    template = load_inputs()[1][0].record
    return tuple(replace(template, id=f'{i:08d}-1111-4111-8111-111111111111',
                         title=f'Fictional activity {i}', training_points=i)
                 for i in (4, 5, 7))


def test_lazy_narrow_widen_different_query_repeat_and_sort():
    source = tuple(replace(record, type='event') for record in records())
    encoder = Encoder()
    search = HybridSearch(encoder)
    assert search(source, '5 điểm').hits == (source[1],)
    assert not encoder.calls
    assert search(source, 'topic từ 7 điểm').hits == (source[2],)
    assert encoder.passages() == 1
    search(source, 'different paraphrase')
    assert encoder.passages() == 3
    for query, filters, sort in [('third topic', None, None), ('third topic', None, 'title'),
                                  ('third topic', {'min_training_points':7}, None),
                                  ('third topic', None, 'latest_deadline')]:
        result = search(source, query, filters=filters, sort=sort)
        assert set(r.key for r in result.hits) <= set(r.key for r in source)
        assert encoder.passages() == 3
        assert encoder.calls[-1] == ['query: '+query]


def test_snapshot_context_text_source_and_account_identity():
    source = records()
    encoder = Encoder()
    search = HybridSearch(encoder)
    token = object()
    assert search(source, 'topic', cache_token=token).hits == source
    search(source, 'topic', cache_token=token)
    assert encoder.passages() == 3
    search(source, 'topic', cache_token=object())
    assert encoder.passages() == 6
    changed = (replace(source[0], title='excluded wording'),)
    assert search(changed, 'topic', cache_token=token).hits == ()
    assert encoder.passages() == 7
    assert search(source[1:], 'topic', cache_token=token).hits == source[1:]
    assert search.cached_passage_count == 2


def test_bounded_lru_and_failure_retry():
    source = records()
    encoder = Encoder()
    search = HybridSearch(encoder, max_cache_entries=2, max_cache_bytes=32)
    assert search(source, 'topic').hits == source
    assert search.cached_passage_count == 2
    assert search.cached_vector_bytes == 32
    search(source, 'topic', filters={'min_training_points':5})
    assert encoder.passages() == 3
    encoder.fail = True
    assert search(source, 'unmatched').hits == ()
    assert search.cached_passage_count == 0
    encoder.fail = False
    attempted = encoder.passages()
    search(source, 'topic')
    assert encoder.passages() == attempted + 3


def test_current_controller_session_refresh_logout_expiry_and_no_reads():
    async def scenario():
        source = records()
        backend = MockBackend()
        snapshot = SearchSnapshot(source, ('public',), None)
        backend.load_tasks = AsyncMock(return_value=TaskLoad((), snapshot))
        controller = ClientController(backend, ClientUser('account-a', 'A'))
        encoder = Encoder()
        controller._hybrid_search = HybridSearch(encoder)
        await controller.load_month(date(2026,11,1))
        controller.search('first topic')
        controller.search('second topic', sort='title')
        controller.show_month(date(2026,12,1))
        controller.state.selected_search_key = source[0].key
        assert controller.selected_search_record is source[0]
        assert encoder.passages() == 3 and backend.load_tasks.await_count == 1
        await controller.load_month()
        assert controller._hybrid_search.cached_passage_count == 0
        controller.search('topic')
        assert encoder.passages() == 6
        controller.set_user(ClientUser('account-b','B'))
        assert controller.selected_search_record is None
        assert controller._hybrid_search.cached_passage_count == 0
        private = replace(source[0], scope='personal', title='excluded wording')
        controller.state.search_snapshot = SearchSnapshot((private,), ('personal',), None)
        assert controller.search('topic').hits == ()
        controller.logout()
        assert controller._hybrid_search.cached_passage_count == 0
        controller.set_user(ClientUser('account-a','A'))
        controller.state.search_snapshot = snapshot
        controller.search('topic')
        backend.load_tasks = AsyncMock(side_effect=SessionExpiredError('expired'))
        await controller.load_month()
        assert controller._hybrid_search.cached_passage_count == 0
        assert controller.state.session_expired
    asyncio.run(scenario())


def test_async_completion_after_account_change_cannot_publish_or_recache_private_text():
    async def scenario():
        source = records()
        entered, release = threading.Event(), threading.Event()
        class Delayed(Encoder):
            def encode(self, texts):
                if not entered.is_set():
                    entered.set()
                    assert release.wait(10)
                return super().encode(texts)
        backend = MockBackend()
        controller = ClientController(backend, ClientUser('account-a','A'))
        controller._hybrid_search = HybridSearch(Delayed())
        controller.state.search_snapshot = SearchSnapshot(source, ('personal',), None)
        old = asyncio.create_task(controller.search_async('topic'))
        assert await asyncio.to_thread(entered.wait, 5)
        controller.set_user(ClientUser('account-b','B'))
        changed = replace(source[0], scope='personal', title='excluded wording')
        controller.state.search_snapshot = SearchSnapshot((changed,), ('personal',), None)
        current = asyncio.create_task(controller.search_async('different topic'))
        await asyncio.sleep(0)
        release.set()
        assert await old is None
        assert (await current).hits == ()
        assert controller._hybrid_search.cached_passage_count == 1
        controller.logout()
        assert controller._hybrid_search.cached_passage_count == 0
    asyncio.run(scenario())


def test_async_new_query_wins_and_event_loop_keeps_running():
    async def scenario():
        entered, release = threading.Event(), threading.Event()
        class Delayed(Encoder):
            def encode(self, texts):
                if not entered.is_set():
                    entered.set()
                    assert release.wait(10)
                return super().encode(texts)
        controller = ClientController(MockBackend(), ClientUser('A','A'))
        controller._hybrid_search = HybridSearch(Delayed())
        controller.state.search_snapshot = SearchSnapshot(records(), ('public',), None)
        old = asyncio.create_task(controller.search_async('old topic'))
        assert await asyncio.to_thread(entered.wait, 5)
        new = asyncio.create_task(controller.search_async('new topic'))
        await asyncio.sleep(0)
        assert controller.state.search_query == 'new topic'
        release.set()
        assert await old is None
        assert (await new).topic == 'new topic'
    asyncio.run(scenario())


def test_source_preference_refresh_invalidates_warmed_passages(tmp_path):
    from search_ui_support import fictional_tasks
    fixture = tmp_path/'tasks.json'
    fixture.write_text(json.dumps(fictional_tasks()), encoding='utf-8')
    async def scenario():
        backend = MockBackend(fixture)
        backend.load_tasks = AsyncMock(wraps=backend.load_tasks)
        controller = ClientController(backend, ClientUser('demo-user','A',True,True))
        controller._hybrid_search = HybridSearch(Encoder())
        await controller.load_month(date(2026,11,1))
        assert len(controller.search('paraphrase').hits) == 6
        assert controller._hybrid_search.cached_passage_count == 6
        await backend.set_source_enabled(controller.state.user,'Moodle',False)
        await controller.load_month()
        assert controller._hybrid_search.cached_passage_count == 0
        result = controller.search('paraphrase')
        assert len(result.hits) == 4
        assert all(r.publisher != 'Moodle' for r in result.hits)
        assert controller._hybrid_search.cached_passage_count == 4
        assert backend.load_tasks.await_count == 2
    asyncio.run(scenario())
