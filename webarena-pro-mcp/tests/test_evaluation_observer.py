import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from webarena_pro_mcp.browser_identity import BrowserIdentityError
from webarena_pro_mcp.supervisor import evaluation_page


@pytest.mark.parametrize("failure", [
    None, "connect", "contexts", "resolve", "capture", "cancel_connect", "cancel_capture",
])
async def test_evaluation_observer_disconnects_without_closing_browser(monkeypatch, failure):
    page = object()
    identity = {"target_id": "selected", "loader_id": "document", "url": "http://fixture/"}
    context = SimpleNamespace(close=AsyncMock())
    browser = SimpleNamespace(contexts=[context], close=AsyncMock())
    observer = SimpleNamespace(
        chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser)),
        stop=AsyncMock(),
    )
    resolve = AsyncMock(return_value=page)
    monkeypatch.setattr("playwright.async_api.async_playwright", lambda: SimpleNamespace(
        start=AsyncMock(return_value=observer),
    ))
    monkeypatch.setattr("webarena_pro_mcp.supervisor.resolve_page", resolve)
    error = RuntimeError("capture failed")
    if failure == "connect":
        error = RuntimeError("connection failed")
        observer.chromium.connect_over_cdp.side_effect = error
    elif failure == "contexts":
        browser.contexts = [context, context]
        error = BrowserIdentityError("Unexpected browser contexts")
    elif failure == "resolve":
        error = BrowserIdentityError("Selected browser target is no longer available")
        resolve.side_effect = error
    elif failure in {"cancel_connect", "cancel_capture"}:
        error = asyncio.CancelledError()
        if failure == "cancel_connect":
            observer.chromium.connect_over_cdp.side_effect = error

    async def capture():
        async with evaluation_page("http://127.0.0.1:9222", identity) as active:
            assert active is page
            if failure in {"capture", "cancel_capture"}:
                raise error

    if failure:
        with pytest.raises(type(error)) as raised:
            await capture()
        if failure != "contexts":
            assert raised.value is error
    else:
        await capture()
    observer.chromium.connect_over_cdp.assert_awaited_once_with(
        "http://127.0.0.1:9222", no_defaults=True,
    )
    if failure not in {"connect", "cancel_connect", "contexts"}:
        resolve.assert_awaited_once_with(context, identity)
    else:
        resolve.assert_not_awaited()
    observer.stop.assert_awaited_once()
    browser.close.assert_not_awaited()
    context.close.assert_not_awaited()
