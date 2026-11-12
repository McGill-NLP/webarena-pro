import os

import pytest
from playwright.async_api import async_playwright

from webarena_pro_mcp.browser_identity import (
    BrowserIdentityError, identity_capture, page_identity, resolve_page,
)
from webarena_pro_mcp.mcp_client import connect
from webarena_pro_mcp.supervisor import Supervisor, evaluation_page
from webarena_pro_mcp.tool_policy import ToolPolicy

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1 after webarena-pro-mcp install",
    ),
]


async def test_fresh_capture_survives_client_loss_and_rejects_changed_targets(tmp_path, website, task):
    url, _ = website
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    try:
        setup = await supervisor.start(30)
        policy = ToolPolicy([url], blocked_paths=setup["blocked_paths"])
        async with connect(setup["endpoint"], tmp_path / "browser", policy, 30) as browser:
            await browser.call("browser_navigate", {"url": url})
            await browser.call("browser_tabs", {"action": "new", "url": url})
            selected = await browser.identity()
            async with async_playwright() as runtime:
                client = await runtime.chromium.connect_over_cdp(setup["endpoint"], no_defaults=True)
                stale_context = client.contexts[0]
                selected_page = await resolve_page(stale_context, selected)
                await selected_page.locator("#status").evaluate("element => element.textContent = 'Selected report'")
            # The old client's handles are genuinely disconnected, while MCP
            # still sees the exact live target. No browser target was replaced.
            with pytest.raises(BrowserIdentityError, match="no longer available"):
                await resolve_page(stale_context, selected)
            assert await browser.identity() == selected

            async with async_playwright() as controller:
                client = await controller.chromium.connect_over_cdp(setup["endpoint"], no_defaults=True)
                selected_page = await resolve_page(client.contexts[0], selected)
                await selected_page.set_viewport_size({"width": 913, "height": 657})
                async with evaluation_page(setup["endpoint"], selected) as active:
                    assert await page_identity(active) == selected
                    assert await active.locator("#status").inner_text() == "Selected report"
                    assert await active.evaluate("({width: innerWidth, height: innerHeight})") == {
                        "width": 913, "height": 657,
                    }
                    async with identity_capture(active, selected):
                        assert await active.screenshot()
                # Disconnecting private capture leaves the task browser, its
                # document state, and both same-URL tabs usable by the agent.
                assert await browser.identity() == selected
                async with evaluation_page(setup["endpoint"], selected) as active:
                    assert len(active.context.pages) == 2
                    assert await active.locator("#status").inner_text() == "Selected report"
                    await active.reload()
                with pytest.raises(BrowserIdentityError, match="document changed"):
                    async with evaluation_page(setup["endpoint"], selected):
                        pytest.fail("A same-URL reload must invalidate the old document")

                reloaded = await browser.identity()
                assert reloaded["target_id"] == selected["target_id"]
                assert reloaded["loader_id"] != selected["loader_id"]
                await browser.call("browser_tabs", {"action": "close", "index": 1})
                assert (await browser.identity())["url"] == selected["url"]
                for unavailable in (reloaded, {**reloaded, "target_id": "unknown-target"}):
                    with pytest.raises(BrowserIdentityError, match="no longer available"):
                        async with evaluation_page(setup["endpoint"], unavailable):
                            pytest.fail("A same-URL tab must not replace the selected target")
                assert not (await browser.call("browser_snapshot", {}))["isError"]
    finally:
        await supervisor.close()
