"""Cooperative preparation uses explicit passage batches, never dummy queries."""

import asyncio
from collections import Counter
from dataclasses import replace
from datetime import date
import threading
from unittest.mock import AsyncMock

import pytest

from academic_search import SearchSnapshot
from academic_search.semantic import HybridSearch
from client.core.backend import TaskLoad
from client.core.controller import ClientController
from client.core.mock_backend import MockBackend
from client.core.models import ClientUser
from test_search_embedding_cache import Encoder, records


def prepare_all(ranker, source, token):
    epoch=ranker.begin_preparation(source,cache_token=token)
    start=0
    while True:
        status=ranker.prepare_batch(source,cache_token=token,expected_epoch=epoch,start=start)
        if status['state']!='running': return status
        start=status['next_index']


@pytest.mark.parametrize('entry_limit,byte_limit',[(2,64),(3,32)])
def test_explicit_preparation_no_queries_and_no_eviction_churn(entry_limit,byte_limit):
    source=records()
    encoder=Encoder()
    ranker=HybridSearch(encoder,max_cache_entries=entry_limit,max_cache_bytes=byte_limit)
    token=object()
    status=prepare_all(ranker,source,token)
    assert status['state']=='partial' and status['cached']==2 and status['total']==3
    assert ranker.cached_vector_bytes==32
    assert all(text.startswith('passage: ') for call in encoder.calls for text in call)
    previous=encoder.passages()
    assert prepare_all(ranker,source,token)['state']=='partial'
    assert encoder.passages()==previous
    ranker.clear_cache()
    ranker=HybridSearch(encoder)
    assert prepare_all(ranker,source,token)['state']=='complete'
    previous=encoder.passages()
    ranker(source,'different topic',cache_token=token)
    assert encoder.passages()==previous


def test_foreground_has_priority_between_batches_and_no_duplicate_passages():
    async def scenario():
        entered,release=threading.Event(),threading.Event()
        class Delayed(Encoder):
            def encode(self,texts):
                if not entered.is_set():
                    entered.set()
                    assert release.wait(10)
                return super().encode(texts)
        source=records()
        backend=MockBackend()
        backend.load_tasks=AsyncMock(return_value=TaskLoad((),SearchSnapshot(source,('public',))))
        controller=ClientController(backend,ClientUser('A','A'))
        encoder=Delayed();controller._hybrid_search=HybridSearch(encoder)
        await controller.load_month(date(2026,11,1))
        assert controller.state.search_query=='' and controller.state.selected_search_key is None
        assert await asyncio.to_thread(entered.wait,5)
        query=asyncio.create_task(controller.search_async('topic'))
        await asyncio.sleep(0)
        release.set()
        assert (await query).hits==source
        await controller._preparation_task
        assert encoder.calls[0][0].startswith('passage: ')
        assert encoder.calls[1][0]=='query: topic'
        passage_counts=Counter(t for call in encoder.calls for t in call if t.startswith('passage: '))
        assert len(passage_counts)==3 and set(passage_counts.values())=={1}
        assert controller.preparation_status['state']=='complete'
        assert backend.load_tasks.await_count==1
    asyncio.run(scenario())


@pytest.mark.parametrize('transition',['account','refresh','source','logout','expiry'])
def test_obsolete_preparation_cannot_repopulate_or_publish(transition):
    async def scenario():
        entered,release=threading.Event(),threading.Event()
        class Delayed(Encoder):
            def encode(self,texts):
                if not entered.is_set():
                    entered.set();assert release.wait(10)
                return super().encode(texts)
        source=records()
        backend=MockBackend()
        backend.load_tasks=AsyncMock(return_value=TaskLoad((),SearchSnapshot(source,('personal',))))
        controller=ClientController(backend,ClientUser('A','A'))
        controller._hybrid_search=HybridSearch(Delayed())
        await controller.load_month(date(2026,11,1))
        old=controller._preparation_task
        assert await asyncio.to_thread(entered.wait,5)
        if transition in ('logout','expiry'):
            controller.logout();controller.state.session_expired=transition=='expiry'
        else:
            if transition=='account': controller.set_user(ClientUser('B','B'))
            changed=replace(source[0],title='excluded wording',publisher='Different source')
            backend.load_tasks.return_value=TaskLoad((),SearchSnapshot((changed,),('personal',)))
            await controller.load_month()
        release.set();await old
        if transition in ('logout','expiry'):
            assert controller._hybrid_search.cached_passage_count==0
            assert controller.preparation_status['state']=='cancelled'
        else:
            await controller._preparation_task
            assert controller.preparation_status['state']=='complete'
            assert controller._hybrid_search.cached_passage_count==1
            assert controller.search('topic').hits==()
        assert controller.state.selected_search_key is None
    asyncio.run(scenario())


def test_keyword_only_does_not_start_or_initialize_preparation(monkeypatch):
    monkeypatch.delenv('SEARCH_SEMANTIC_MODEL',raising=False)
    monkeypatch.setattr('academic_search.semantic.LocalEncoder',lambda *_:pytest.fail('model initialized'))
    async def scenario():
        backend=MockBackend()
        backend.load_tasks=AsyncMock(return_value=TaskLoad((),SearchSnapshot(records(),('public',))))
        controller=ClientController(backend,ClientUser('A','A'))
        await controller.load_month()
        assert controller.preparation_status['state']=='disabled'
        assert controller._preparation_task is None
        assert controller.search('Fictional').hits
    asyncio.run(scenario())


def test_ui_gate_allows_calendar_readiness_before_model_work():
    async def scenario():
        backend=MockBackend()
        backend.load_tasks=AsyncMock(return_value=TaskLoad((),SearchSnapshot(records(),('public',))))
        controller=ClientController(backend,ClientUser('A','A'))
        encoder=Encoder()
        controller._hybrid_search=HybridSearch(encoder)
        gate=controller.defer_preparation()
        await controller.load_month()
        await asyncio.sleep(0)
        assert not controller.state.loading
        assert controller.state.search_snapshot.records
        assert controller.preparation_status['state']=='pending'
        assert encoder.calls==[]
        gate.set()
        await controller._preparation_task
        assert controller.preparation_status['state']=='complete'
        assert all(t.startswith('passage: ') for call in encoder.calls for t in call)
    asyncio.run(scenario())


def test_unavailable_preparation_keeps_keyword_fallback_and_no_private_vectors():
    class Unavailable(Encoder):
        def encode(self,texts):
            raise RuntimeError('Unavailable fictional model')
    source=records()
    ranker=HybridSearch(Unavailable())
    assert prepare_all(ranker,source,object())['state']=='unavailable'
    assert ranker.cached_passage_count==0
    result=ranker(source,'Fictional')
    from academic_search import search_records
    assert result==search_records(source,'Fictional')


def test_logout_before_first_paint_cancels_waiting_preparation():
    async def scenario():
        backend=MockBackend()
        backend.load_tasks=AsyncMock(return_value=TaskLoad((),SearchSnapshot(records(),('personal',))))
        controller=ClientController(backend,ClientUser('A','A'))
        encoder=Encoder()
        controller._hybrid_search=HybridSearch(encoder)
        gate=controller.defer_preparation()
        await controller.load_month()
        task=controller._preparation_task
        controller.logout()
        gate.set()
        await asyncio.gather(task,return_exceptions=True)
        assert task.cancelled()
        assert encoder.calls==[]
        assert controller.preparation_status['state']=='cancelled'
        assert controller.state.search_snapshot.records==()
    asyncio.run(scenario())
