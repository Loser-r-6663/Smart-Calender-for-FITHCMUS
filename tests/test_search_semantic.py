"""Hybrid control-flow checks use fictional vectors, not retrieval-quality evidence."""

from dataclasses import replace
from datetime import timedelta

import pytest

from academic_search.matcher import search_records
from academic_search.semantic import HybridSearch
from fixtures.search_semantic.run_keyword import evaluate, load_inputs, visible_records


class Encoder:
    def __init__(self):
        self.calls = []

    def encode(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0] for _ in texts]


def test_unavailable_fallback_is_frozen_keyword_baseline(monkeypatch):
    monkeypatch.setenv("SEARCH_SEMANTIC_MODEL", "missing-model-directory")
    hybrid = evaluate(matcher=HybridSearch())
    assert hybrid == evaluate()


@pytest.mark.parametrize("query", ["", "5 điểm", "từ 5 điểm", "nhiều hơn 5 điểm", "bé hơn 5 điểm"])
def test_filter_only_skips_inference(query):
    _, owned, _, _ = load_inputs()
    encoder = Encoder()
    records = tuple(x.record for x in owned)
    assert HybridSearch(encoder)(records, query) == search_records(records, query)
    assert not encoder.calls


def test_all_frozen_views_and_points_remain_eligible_only():
    accounts, owned, cases, _ = load_inputs()
    encoder = Encoder()
    search = HybridSearch(encoder)
    for case in cases:
        visible = visible_records(owned, accounts, case)
        result = search(visible, case['query'], filters=case['filters'], sort=case['sort'])
        baseline = search_records(visible, case['query'], filters=case['filters'], sort=case['sort'])
        assert result.eligible_records == baseline.eligible_records
        assert all(any(r is allowed for allowed in baseline.eligible_records) for r in result.hits)
        assert len({r.key for r in result.hits}) == len(result.hits)
        assert set(r.key for r in baseline.hits) <= set(r.key for r in result.hits)
        exact = any(baseline.topic.casefold() in (r.title.casefold(), (r.course or '').casefold())
                    for r in baseline.eligible_records)
        if baseline.topic and baseline.eligible_records and not exact:
            assert encoder.calls[-1][0] == 'query: ' + baseline.topic


def test_exact_priority_sorts_text_refresh_and_collisions():
    _, owned, _, _ = load_inputs()
    first = owned[0].record
    records = (replace(first, title='Exact title', course='CSC999'),
               replace(first, scope='personal', title='Other title'),
               replace(first, id='ffffffff-ffff-4fff-8fff-ffffffffffff', title='A title'))
    encoder = Encoder()
    search = HybridSearch(encoder)
    for query in ('Exact title', 'CSC999'):
        assert search(records, query).hits[0] is records[0]
    keys = {r.key for r in records}
    for sort in ('best_match', 'title', 'soonest_deadline', 'latest_deadline'):
        assert {r.key for r in search(records, 'paraphrase', sort=sort).hits} == keys
    assert search(records, 'paraphrase', sort='title').hits == (records[2], records[0], records[1])
    later = replace(records[2], deadline=first.deadline + timedelta(days=1))
    undated = replace(first, id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', deadline=None)
    dated = (records[0], records[1], later, undated)
    assert search(dated, 'paraphrase', sort='soonest_deadline').hits == (records[1], records[0], later, undated)
    assert search(dated, 'paraphrase', sort='latest_deadline').hits == (later, records[1], records[0], undated)
    changed = replace(records[1], title='New private facts')
    assert search((changed,), 'paraphrase').hits == (changed,)
    assert 'New private facts' in encoder.calls[-1][1]
    assert search((), 'paraphrase').hits == ()


def test_encoder_failure_preserves_literal_order():
    class Broken:
        def encode(self, texts):
            raise RuntimeError('private details must not be logged')
    _, owned, _, _ = load_inputs()
    records = [item.record for item in owned]
    assert HybridSearch(Broken())(records, '5 điểm') == search_records(records, '5 điểm')
    assert HybridSearch(Broken())(records, 'thời điểm') == search_records(records, 'thời điểm')


@pytest.mark.parametrize('query', ['Buổi thực hành robot', 'ROB202'])
@pytest.mark.parametrize('sort', ['best_match', 'title', 'soonest_deadline', 'latest_deadline'])
def test_exact_topic_keeps_complete_literal_set(query, sort):
    _, owned, _, _ = load_inputs()
    template = owned[0].record
    exact = replace(template, title='Buổi thực hành robot', course='ROB202')
    loose = replace(template, scope='personal', title='Buổi thực hành robot nâng cao',
                    description='ROB202', course=None)
    semantic_only = replace(template, id='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
                            title='Lắp ráp máy tự động', course=None)
    records = (semantic_only, loose, exact)
    encoder = Encoder()
    result = HybridSearch(encoder)(records, query, sort=sort)
    expected = search_records(records, query, sort=sort)
    assert result == expected
    assert {r.key for r in result.hits} == {exact.key, loose.key}
    assert not encoder.calls


def test_ineligible_exact_does_not_suppress_paraphrase_expansion():
    _, owned, _, _ = load_inputs()
    template = owned[0].record
    exact = replace(template, title='tìm nơi rèn kỹ năng', training_points=5)
    paraphrase = replace(template, scope='personal', title='Xưởng thực tập sáng tạo',
                         description='Hướng dẫn chế tạo thiết bị', training_points=7)
    encoder = Encoder()
    hybrid = HybridSearch(encoder)
    assert search_records((paraphrase,), exact.title).hits == ()
    # Authorization/source selection supplies only permitted records to retrieval.
    assert hybrid((paraphrase,), exact.title).hits == (paraphrase,)
    assert hybrid((exact, paraphrase), exact.title + ' nhiều hơn 5 điểm').hits == (paraphrase,)
    assert len(encoder.calls) == 2
