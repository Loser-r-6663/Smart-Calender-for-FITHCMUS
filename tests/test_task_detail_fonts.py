"""Offline browser checks for Vietnamese detail-heading font coverage."""

import json
import unicodedata

import pytest
from playwright.sync_api import expect, sync_playwright

from test_search_ui import PUBLIC, fictional_tasks, serve_ui

TITLE = "Tổng kết Buổi giới thiệu về các chương trình học bổng trường Đại học Quốc gia Seoul (Hàn Quốc)"
WORDS = ("kết", "về", "bổng", "Quốc")


def rendered_fonts(session, selector):
    root = session.send("DOM.getDocument")["root"]["nodeId"]
    node = session.send("DOM.querySelector", {"nodeId": root, "selector": selector})["nodeId"]
    return session.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]


def probe_words(locator):
    locator.evaluate("""element => {
        const text = element.textContent;
        element.replaceChildren();
        text.split(' ').forEach((word, index) => {
            if (index) element.append(' ');
            const span = document.createElement('span');
            span.textContent = word;
            span.dataset.fontWord = word.normalize('NFC');
            element.append(span);
        });
    }""")


@pytest.mark.parametrize("form", ["NFC", "NFD"])
@pytest.mark.parametrize("width,height", [(1280, 900), (390, 844)])
def test_vietnamese_detail_fonts_in_dialog_and_calendar_panels(tmp_path, form, width, height):
    title = unicodedata.normalize(form, TITLE)
    tasks = fictional_tasks()
    tasks[0].update(title=title, description="Thông tin học bổng. " + title)
    with serve_ui(tmp_path, tasks=tasks) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2)
            context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
            page = context.new_page()
            page.goto(url + "/start")
            expect(page.locator(".search-result")).to_have_count(6)
            page.get_by_label("Query", exact=True).fill("học bổng")
            page.get_by_label("Query", exact=True).press("Enter")
            expect(page.locator(".search-result")).to_have_count(1)
            row = page.locator(".search-result-title")
            assert row.text_content() == title
            page.locator(f'[data-search-key="{PUBLIC}"]').click()
            heading = page.locator(".search-detail-dialog .detail-title")
            expect(heading).to_be_visible()
            assert heading.text_content() == row.text_content() == title
            assert unicodedata.normalize("NFC", heading.text_content()) == TITLE
            style = heading.evaluate("e => ({family:getComputedStyle(e).fontFamily,weight:getComputedStyle(e).fontWeight,size:getComputedStyle(e).fontSize,lineHeight:getComputedStyle(e).lineHeight})")
            assert style["weight"] == "600" and style["size"] == "19.2px" and style["lineHeight"] == "24px"
            assert style["family"] == row.evaluate("e => getComputedStyle(e).fontFamily")
            session = context.new_cdp_session(page)
            session.send("DOM.enable")
            session.send("CSS.enable")
            fonts = rendered_fonts(session, ".search-result-title")
            expected = {(font["familyName"], font["postScriptName"]) for font in fonts}
            assert expected
            observations = {"unicode_form": form, "width": width, "style": style, "row_fonts": fonts}

            def inspect_title(selector, label):
                element = page.locator(selector)
                assert element.text_content() == title
                probe_words(element)
                assert element.text_content() == title
                element.screenshot(path=str(tmp_path / f"{label}-title-{form}-{width}.png"), animations="disabled")
                details = {"title_fonts": rendered_fonts(session, selector), "words": {}}
                assert {(font["familyName"], font["postScriptName"]) for font in details["title_fonts"]} == expected
                for word in WORDS:
                    word_fonts = rendered_fonts(session, selector + f' [data-font-word="{word}"]')
                    assert word_fonts
                    assert {(font["familyName"], font["postScriptName"]) for font in word_fonts} == expected
                    details["words"][word] = word_fonts
                observations[label] = details

            inspect_title(".search-detail-dialog .detail-title", "dialog")
            page.screenshot(path=str(tmp_path / f"dialog-{form}-{width}.png"), animations="disabled")
            page.locator(".search-detail-dialog").get_by_role("button", name="Close", exact=True).click()
            expect(page.locator(".search-detail-dialog")).not_to_be_visible()
            page.locator(".search-query-row").get_by_role("button", name="Clear", exact=True).click()
            expect(page.locator(".search-result")).to_have_count(6)
            expect(page.get_by_label("Query", exact=True)).to_have_value("")
            page.get_by_role("button", name="Agenda", exact=True).click()
            expect(page.locator(".agenda-list")).to_be_visible()
            assert title in page.locator(".agenda-title").all_text_contents(), page.locator(".agenda-list").inner_text()
            page.locator(".agenda-item").filter(has_text=title).click()
            expect(page.locator(".task-panel .detail-title")).to_have_text(title)
            inspect_title(".task-panel .detail-title", "agenda")
            page.get_by_role("button", name="Calendar", exact=True).click()
            expect(page.locator(".month-grid")).to_be_visible()
            previous_heading = page.locator(".task-panel .detail-title").get_attribute("id")
            page.locator(".event-pill").filter(has_text=title).click()
            expect(page.locator(".task-panel .detail-title")).not_to_have_attribute("id", previous_heading)
            expect(page.locator(".task-panel .detail-title")).to_have_text(title)
            inspect_title(".task-panel .detail-title", "calendar")
            page.locator(".task-panel").screenshot(path=str(tmp_path / f"calendar-panel-{form}-{width}.png"), animations="disabled")
            (tmp_path / "rendered-fonts.json").write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            browser.close()
