import asyncio
from unittest.mock import AsyncMock

import pytest

from webarena_pro_mcp.supervisor import wait_for_devtools_endpoint


async def test_ready_devtools_port_returns_without_waiting(tmp_path, monkeypatch):
    (tmp_path / "DevToolsActivePort").write_text("9222\n/devtools/browser/fixture")
    sleep = AsyncMock(side_effect=AssertionError("Ready endpoint should not wait"))
    monkeypatch.setattr("webarena_pro_mcp.supervisor.asyncio.sleep", sleep)

    assert await wait_for_devtools_endpoint(tmp_path) == "http://127.0.0.1:9222"
    sleep.assert_not_awaited()


async def test_devtools_port_waits_for_creation_and_complete_port_line(tmp_path, monkeypatch):
    port_file = tmp_path / "DevToolsActivePort"
    writes = iter(["", "92", "9222\n/devtools/browser/fixture"])

    async def publish_next_chunk(_):
        port_file.write_text(next(writes))

    sleep = AsyncMock(side_effect=publish_next_chunk)
    monkeypatch.setattr("webarena_pro_mcp.supervisor.asyncio.sleep", sleep)

    assert await wait_for_devtools_endpoint(tmp_path) == "http://127.0.0.1:9222"
    assert sleep.await_count == 3


@pytest.mark.parametrize("contents", [None, "", "92", "invalid\n", "0\n", "65536\n"])
async def test_unavailable_devtools_port_has_bounded_diagnostic_timeout(tmp_path, contents):
    if contents is not None:
        (tmp_path / "DevToolsActivePort").write_text(contents)

    with pytest.raises(TimeoutError, match="Chromium did not publish a valid DevToolsActivePort"):
        await asyncio.wait_for(wait_for_devtools_endpoint(tmp_path, timeout=0.01), timeout=1)


async def test_devtools_port_wait_can_be_cancelled(tmp_path, monkeypatch):
    waiting = asyncio.Event()

    async def wait(_):
        waiting.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("webarena_pro_mcp.supervisor.asyncio.sleep", wait)
    pending = asyncio.create_task(wait_for_devtools_endpoint(tmp_path))
    await asyncio.wait_for(waiting.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending


async def test_devtools_port_does_not_retry_other_filesystem_errors(tmp_path):
    (tmp_path / "DevToolsActivePort").mkdir()
    with pytest.raises(IsADirectoryError):
        await wait_for_devtools_endpoint(tmp_path)
