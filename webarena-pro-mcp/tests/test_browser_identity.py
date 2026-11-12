from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from mcp_types import CallToolResult, TextContent

from webarena_pro_mcp.browser_identity import BrowserIdentityError, IDENTITY_PROBE, resolve_page, verify_identity
from webarena_pro_mcp.evaluation import grade
from webarena_pro_mcp.mcp_client import MCPBrowser
from webarena_pro_mcp.tool_policy import PolicyError, ToolPolicy

FIRST = {"target_id": "first", "loader_id": "document-1", "url": "http://fixture/same"}
SECOND = {**FIRST, "target_id": "second"}


async def test_target_resolution_ignores_order_and_duplicate_urls(monkeypatch):
    first, second = object(), object()
    monkeypatch.setattr("webarena_pro_mcp.browser_identity.page_identity", AsyncMock(
        side_effect=lambda page: FIRST if page is first else SECOND,
    ))
    assert await resolve_page(SimpleNamespace(pages=[second, first]), FIRST) is first
    assert await resolve_page(SimpleNamespace(pages=[first, second]), SECOND) is second
    with pytest.raises(BrowserIdentityError, match="no longer available"):
        await resolve_page(SimpleNamespace(pages=[second]), FIRST)


@pytest.mark.parametrize("changed", [
    {**FIRST, "loader_id": "reloaded-at-same-url"},
    {**FIRST, "url": "http://fixture/same#new-route"},
])
async def test_changed_document_is_never_substituted(monkeypatch, changed):
    page = object()
    monkeypatch.setattr("webarena_pro_mcp.browser_identity.page_identity", AsyncMock(return_value=changed))
    with pytest.raises(BrowserIdentityError, match="document changed"):
        await resolve_page(SimpleNamespace(pages=[page]), FIRST)
    with pytest.raises(BrowserIdentityError, match="document changed"):
        await verify_identity(page, FIRST)


async def test_closed_target_fails_capture(monkeypatch):
    monkeypatch.setattr("webarena_pro_mcp.browser_identity.page_identity", AsyncMock(side_effect=RuntimeError("closed")))
    with pytest.raises(BrowserIdentityError, match="no longer available"):
        await verify_identity(object(), FIRST)


async def test_grade_recaptures_snapshot_after_same_url_reload():
    reloaded = {**FIRST, "loader_id": "document-2"}
    def snapshot(text):
        return {"content": [{"type": "text", "text": text}], "isError": False}

    browser = SimpleNamespace(
        identity=AsyncMock(side_effect=[FIRST, reloaded, reloaded, reloaded]),
        call=AsyncMock(side_effect=[snapshot("stale"), snapshot("fresh")]),
    )
    supervisor = SimpleNamespace(call=AsyncMock(return_value={"score": 1}))
    result, observation = await grade(browser, supervisor, [], "submit", 2)
    assert result["score"] == 1
    assert observation == snapshot("fresh")
    supervisor.call.assert_awaited_once()
    assert supervisor.call.await_args.kwargs["snapshot"] == "fresh"
    assert supervisor.call.await_args.kwargs["identity"] == reloaded


async def test_grade_identity_retry_is_bounded_and_never_retries_evaluator_failure():
    browser = SimpleNamespace(identity=AsyncMock(return_value=FIRST), call=AsyncMock(return_value={"content": []}))
    supervisor = SimpleNamespace(call=AsyncMock(side_effect=BrowserIdentityError("changed")))
    with pytest.raises(BrowserIdentityError):
        await grade(browser, supervisor, [], "submit", 2)
    assert supervisor.call.await_count == browser.call.await_count == 3
    supervisor.call = AsyncMock(side_effect=RuntimeError("evaluator failed"))
    with pytest.raises(RuntimeError, match="evaluator failed"):
        await grade(browser, supervisor, [], "submit", 2)
    supervisor.call.assert_awaited_once()


async def test_fixed_private_probe_is_unavailable_to_agent():
    import json

    client = AsyncMock()
    client.call_tool.return_value = CallToolResult(content=[TextContent(
        type="text", text="### Result\n" + json.dumps(FIRST) + "\n### Ran Playwright code\nprivate",
    )])
    browser = MCPBrowser(client, ToolPolicy(["http://fixture"]), 1)
    assert await browser.identity() == FIRST
    assert client.call_tool.await_args.args == ("browser_run_code_unsafe", {"code": IDENTITY_PROBE})
    for name in ("browser_run_code_unsafe", "browser_run_code", "browser_evaluate"):
        with pytest.raises(PolicyError):
            await browser.call(name, {"code": "caller-controlled"})


async def test_supervisor_cancellation_disables_channel_reuse(monkeypatch):
    import asyncio
    from webarena_pro_mcp.supervisor import Supervisor

    supervisor = Supervisor.__new__(Supervisor)
    supervisor.broken = False
    supervisor.connection = SimpleNamespace(poll=lambda timeout: True)
    monkeypatch.setattr(asyncio, "to_thread", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await supervisor.receive(30)
    assert supervisor.broken
    with pytest.raises(RuntimeError, match="no longer synchronized"):
        await supervisor.call("evaluate")


async def test_grade_deadline_includes_identity_capture():
    import asyncio

    async def delayed_identity():
        await asyncio.sleep(1)
        return FIRST

    browser = SimpleNamespace(identity=delayed_identity)
    supervisor = SimpleNamespace(call=AsyncMock())
    with pytest.raises(TimeoutError):
        await grade(browser, supervisor, [], "submit", 0.01)
    supervisor.call.assert_not_awaited()


@pytest.mark.parametrize("identities", [
    [BrowserIdentityError("target closed"), FIRST, FIRST],
    [FIRST, BrowserIdentityError("target replaced"), SECOND, SECOND],
])
async def test_inventory_retries_a_transient_identity_probe_failure(identities):
    from webarena_pro_mcp.media_policy import MediaSettings

    media = AsyncMock()
    media.call_tool.return_value = CallToolResult(content=[], structured_content={"sources": []})
    browser = MCPBrowser(AsyncMock(), ToolPolicy(["http://fixture"], media=MediaSettings()), 1, media)
    browser.identity = AsyncMock(side_effect=identities)
    assert await browser.inventory() == []
    assert media.call_tool.await_args.args[1]["identity"] == identities[-1]


async def test_inventory_identity_failure_has_a_bounded_attempt_count():
    from webarena_pro_mcp.media_policy import MediaSettings

    browser = MCPBrowser(AsyncMock(), ToolPolicy(["http://fixture"], media=MediaSettings()), 1, AsyncMock())
    browser.identity = AsyncMock(side_effect=BrowserIdentityError("target unavailable"))
    with pytest.raises(BrowserIdentityError, match="3 attempts"):
        await browser.inventory()
    assert browser.identity.await_count == 3


@pytest.mark.parametrize("changed", [False, True])
async def test_failed_capture_retries_only_if_document_changed(monkeypatch, changed):
    from webarena_pro_mcp.browser_identity import identity_capture

    monkeypatch.setattr("webarena_pro_mcp.browser_identity.page_identity", AsyncMock(
        return_value={**FIRST, "loader_id": "new-document"} if changed else FIRST,
    ))
    with pytest.raises(BrowserIdentityError if changed else ValueError):
        async with identity_capture(object(), FIRST):
            raise ValueError("screenshot failed")
