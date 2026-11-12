import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

from webarena_pro_core.eval.ui_evidence import MAX_TEXT, MAX_REACTIONS, UIEvidence, UIEvidencePlan, UIProbe
from webarena_pro_core.ui_evidence import sync_api, async_api

COUNT = UIProbe(kind="count", selector=".target:visible")
TEXT = UIProbe(kind="first_text", selector=".target")
REACTIONS = UIProbe(kind="nextcloud_reactions")
PLAN = UIEvidencePlan(probes=[COUNT, TEXT, REACTIONS])


def reaction(message_id="12", selected=True, hidden=False, inside=True, emoji="✅"):
    return f'''<div class="{'messages-list__scroller' if inside else 'unrelated'}">
    <div data-message-id="{message_id}" style="{'display:none' if hidden else ''}">
    <button class="reaction-button--trigger {'button-vue--primary' if selected else ''}">
    <span class="reaction-emoji">{emoji}</span></button></div></div>'''.replace(
        '<button class=', '<div class="reactions-wrapper"><button class='
    ).replace('</button>', '</button></div>')


@pytest.mark.parametrize("body,expected_count,expected_text", [
    ("<main>empty</main>", 0, ""),
    ('<div class="target">first</div><div class="target">second</div>', 2, "first"),
    ('<div class="target" style="display:none">hidden first</div><div class="target">visible</div>', 1, "hidden first"),
])
def test_sync_async_capture_parity_and_raw_semantics(body, expected_count, expected_text):
    body += reaction() + reaction("13", selected=False, emoji="👍") + reaction("14", hidden=True) + reaction("15", inside=False)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.set_content(body)
        sync = sync_api.collect_ui_evidence(page, PLAN, step=5)
        browser.close()

    async def collect():
        async with async_playwright() as runtime:
            browser = await runtime.chromium.launch()
            page = await browser.new_page()
            await page.set_content(body)
            value = await async_api.collect_ui_evidence(page, PLAN, step=5)
            await browser.close()
            return value

    asynchronous = asyncio.run(collect())
    assert sync.status == asynchronous.status == "ok"
    assert sync.semantic_data() == asynchronous.semantic_data()
    assert sync.result(COUNT).count == expected_count
    assert sync.result(TEXT).text == expected_text
    assert [r.model_dump() for r in sync.result(REACTIONS).reactions] == [
        {"message_id": "12", "text": "✅", "selected": True},
        {"message_id": "13", "text": "👍", "selected": False},
    ]
    assert UIEvidence.model_validate_json(sync.model_dump_json()) == sync


def test_limits_are_explicit_and_invalid_selectors_do_not_hide_valid_results():
    bad = UIProbe(kind="count", selector="[invalid")
    plan = UIEvidencePlan(probes=[COUNT, TEXT, REACTIONS, bad])
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page()
        page.set_content('<div class="target">' + 'x' * (MAX_TEXT + 1) + '</div>' + reaction() * (MAX_REACTIONS + 1))
        captured = sync_api.collect_ui_evidence(page, plan)
        assert captured.status == "ok"
        assert captured.result(COUNT).count == 1
        assert captured.results[TEXT.key].status == "truncated"
        assert captured.results[REACTIONS.key].status == "truncated"
        assert len(captured.results[REACTIONS.key].reactions) == MAX_REACTIONS
        assert captured.results[bad.key].status == "error"
        assert captured.results[bad.key].error == "Error"
        browser.close()


@pytest.mark.parametrize("change", ["url", "document", "tab", "closed"])
async def test_capture_identity_changes_are_rejected(change):
    page = SimpleNamespace()
    page.context = SimpleNamespace(pages=[page])
    before = {"url": "http://fixture/", "document": "1"}
    after = dict(before)
    if change == "url": after["url"] = "http://elsewhere/"
    if change == "document": after["document"] = "2"

    async def identities(*_):
        if page.evaluate.await_count == 1:
            return before
        if change == "tab": page.context.pages.insert(0, object())
        if change == "closed": raise RuntimeError("SECRET DOM TEXT")
        return after

    page.evaluate = AsyncMock(side_effect=identities)
    evidence = await async_api.collect_ui_evidence(page, UIEvidencePlan(), step=5)
    assert evidence.status == ("error" if change == "closed" else "stale")
    assert not evidence.results
    assert "SECRET" not in evidence.model_dump_json()


async def test_async_collection_is_cancellable_without_owning_or_closing_the_page():
    entered = asyncio.Event()

    async def evaluate(*_):
        entered.set()
        await asyncio.Event().wait()

    page = SimpleNamespace(evaluate=evaluate, close=AsyncMock())
    page.context = SimpleNamespace(pages=[page])
    pending = asyncio.create_task(async_api.collect_ui_evidence(page, UIEvidencePlan()))
    await asyncio.wait_for(entered.wait(), 2)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError): await pending
    page.close.assert_not_awaited()


async def test_oversized_browser_metadata_returns_error_without_raising():
    page = SimpleNamespace(evaluate=AsyncMock(return_value={"url": "x" * 8193, "document": "1"}))
    page.context = SimpleNamespace(pages=[page])
    evidence = await async_api.collect_ui_evidence(page, UIEvidencePlan())
    assert evidence.status == "error"
    assert evidence.error == "ValidationError"
    assert evidence.url == ""
    assert evidence.results == {}


def test_generated_async_source_is_current():
    subprocess.run([sys.executable, str(Path(__file__).parents[2] / "scripts/generate_ui_evidence_async.py"), "--check"], check=True)
