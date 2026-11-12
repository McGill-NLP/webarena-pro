from unittest.mock import AsyncMock

import pytest
from mcp_types import CallToolResult, TextContent
from test_policy import schemas
from webarena_pro_mcp.mcp_client import (
    MCPBrowser,
    UnsupportedObservationError,
    result_content,
    text_content,
)
from webarena_pro_mcp.tool_policy import PolicyError, ToolPolicy


async def test_stale_reference_error_and_inline_observation():
    policy = ToolPolicy(["http://example.test"])
    policy.expose(schemas())
    policy.observe('- button "Save" [ref=e1]')
    client = AsyncMock()
    client.call_tool.side_effect = [
        CallToolResult(content=[TextContent(type="text", text="Ref e1 not found in the current page snapshot. Try capturing new snapshot.")], is_error=True),
        CallToolResult(content=[TextContent(type="text", text='### Snapshot\n- button "Save" [ref=e2]')]),
        CallToolResult(content=[]),
    ]
    result = await MCPBrowser(client, policy, 1).call("browser_click", {"target": "e1"})
    assert result["isError"] is True and "Ref e1 not found" in text_content(result)
    assert result["rejected_before_action"] is True
    assert policy.refs == {"e2"}
    assert [call.args[0] for call in client.call_tool.call_args_list] == ["browser_click", "browser_snapshot"]


@pytest.mark.parametrize("url", ["http://example.test/next", "http://other.test/", "http://example.test/reset"])
async def test_active_url_is_validated_browser_state(url):
    client = AsyncMock()
    client.call_tool.return_value = CallToolResult(content=[TextContent(
        type="text", text=f"- 0: (current) [Page]({url})"
    )])
    browser = MCPBrowser(client, ToolPolicy(["http://example.test"]), 1)
    if url == "http://example.test/next":
        assert await browser.current_url() == url
    else:
        with pytest.raises(PolicyError):
            await browser.current_url()


def test_unsupported_content_does_not_fetch_links():
    class Result:
        def model_dump(self, **_):
            return {"content": [{"type": "resource_link", "uri": "file:///private/secret"}]}

    with pytest.raises(UnsupportedObservationError):
        result_content(Result())


@pytest.mark.parametrize("tab_count", [1, 2])
async def test_repeated_tab_listing_preserves_last_tab_protection(tab_count):
    policy = ToolPolicy(["http://example.test"])
    policy.expose(schemas())
    listing = "- 0: (current) [Page](http://example.test/)"
    if tab_count == 2:
        listing += "\n- 1: [Other](http://example.test/other)"
    client = AsyncMock()
    client.call_tool.side_effect = [
        CallToolResult(content=[TextContent(type="text", text=f"### Result\n{listing}\n### Open tabs\n{listing}")]),
        CallToolResult(content=[]),
        CallToolResult(content=[]),
    ]
    browser = MCPBrowser(client, policy, 1)
    if tab_count == 1:
        with pytest.raises(PolicyError, match="last browser tab"):
            await browser.call("browser_tabs", {"action": "close"})
        assert client.call_tool.call_count == 1
    else:
        await browser.call("browser_tabs", {"action": "close"})
        assert client.call_tool.call_args_list[1].args == ("browser_tabs", {"action": "close"})
