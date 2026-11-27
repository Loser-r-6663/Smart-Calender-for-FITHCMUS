"""Reproduce the guide's inclusive week and ordering through the real controls."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from test_search_ui import assert_keys, choose, close_details, serve_ui, submit


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/search_demo/tasks.json"
C = "personal:a7100000-0000-4000-8000-000000000001"
B = "personal:33333333-3333-4333-8333-333333333333"
G = "personal:a7100000-0000-4000-8000-000000000002"


def test_frozen_cases_keep_keyword_results_when_optional_model_is_missing(tmp_path, monkeypatch):
    from academic_search.semantic import HybridSearch
    from fixtures.search_semantic.run_keyword import evaluate

    monkeypatch.setenv("SEARCH_SEMANTIC_MODEL", str(tmp_path / "missing-model"))
    keyword = evaluate()
    fallback = evaluate(matcher=HybridSearch())
    assert fallback["cases"] == keyword["cases"]
    assert fallback["correctness_violations"] == keyword["correctness_violations"]
    assert fallback["paraphrase_retrieval"] == keyword["paraphrase_retrieval"]


@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844)])
def test_documented_course_week_sorts_and_original_source(tmp_path, monkeypatch, width, height):
    monkeypatch.delenv("SEARCH_SEMANTIC_MODEL", raising=False)
    tasks = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with serve_ui(tmp_path, tasks=tasks) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            context = browser.new_context(viewport={"width": width, "height": height})
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url)
                          else route.fulfill(body="<h1>Controlled fictional source</h1>")
                          if route.request.url.startswith("https://example.invalid/") else route.abort())
            page = context.new_page()
            page.goto(url + "/start")
            submit(page, "")
            reads = page.request.get(url + "/test-state").json()["reads"]
            choose(page, "Type", "Assignments")
            choose(page, "Course", "CSC10006")
            page.get_by_label("Deadline from").fill("2026-11-30")
            page.get_by_label("Deadline through").fill("2026-12-06")
            for order, keys in (("Soonest deadline", [C, B, G]),
                                ("Latest deadline", [G, B, C]),
                                ("Title A–Z", [B, C, G])):
                choose(page, "Sort", order)
                assert_keys(page, keys)
                expect(page.locator(".search-count")).to_have_text(f"3 tasks · {order}")
                expect(page.get_by_label("Deadline from")).to_have_value("2026-11-30")
                expect(page.get_by_label("Deadline through")).to_have_value("2026-12-06")
            page.screenshot(path=str(tmp_path / "demo-week.png"), full_page=True)
            result = page.locator(f'[data-search-key="{C}"]')
            result.click()
            dialog = page.locator(".search-detail-dialog")
            expect(dialog.locator(".detail-title")).to_have_text("Chuẩn bị truy vấn dữ liệu")
            expected = next(row for row in tasks if row["id"] == C.split(":")[1])
            expect(dialog.locator(".source-link")).to_have_attribute("href", expected["source_url"])
            with context.expect_page() as popup:
                dialog.locator(".source-link").click()
            expect(popup.value.get_by_role("heading")).to_have_text("Controlled fictional source")
            assert popup.value.url == expected["source_url"]
            popup.value.close()
            page.screenshot(path=str(tmp_path / "demo-detail.png"), full_page=True)
            close_details(page)
            expect(result).to_be_focused()
            assert_keys(page, [B, C, G])
            assert page.request.get(url + "/test-state").json()["reads"] == reads
        finally:
            browser.close()
