"""Reproduce delayed debugger publication while keeping real Chromium running."""

import multiprocessing
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from webarena_pro_mcp.supervisor import Supervisor, _serve

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1 after webarena-pro-mcp install",
    ),
]


def _serve_with_delayed_port(connection, *args):
    read_text = Path.read_text
    delayed = False

    def delayed_read(path, *read_args, **kwargs):
        nonlocal delayed
        if path.name == "DevToolsActivePort" and not delayed:
            delayed = True
            (Path(args[1]) / "delayed-port.txt").write_text("missing on first read")
            raise FileNotFoundError(path)
        return read_text(path, *read_args, **kwargs)

    with patch.object(Path, "read_text", delayed_read):
        _serve(connection, *args)


async def test_supervisor_waits_for_delayed_devtools_port(tmp_path, task, website):
    from playwright.async_api import async_playwright

    url, _ = website
    supervisor = Supervisor(task, tmp_path, "fixture", fixture_urls={"jobportal": url})
    supervisor.process = multiprocessing.get_context("spawn").Process(
        target=_serve_with_delayed_port, args=supervisor.process._args,
    )
    try:
        startup = await supervisor.start(30)
        assert (tmp_path / "delayed-port.txt").read_text() == "missing on first read"
        async with async_playwright() as runtime:
            browser = await runtime.chromium.connect_over_cdp(startup["endpoint"])
            page = browser.contexts[0].pages[0]
            await page.goto(url)
            assert await page.title() == "Fixture"
    finally:
        await supervisor.close()
    assert not supervisor.process.is_alive()
