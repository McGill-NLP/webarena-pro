import asyncio
import base64
import json
import os
import re
import socket

import httpx
import pytest
import uvicorn
from mcp import Client
from webarena_pro_mcp.media_policy import MediaSettings

from webarena_pro_mcp.session import open_session
from webarena_pro_mcp.server import control_socket, finalize, make_app

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1",
    ),
]


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("profile", ["browser-only", "standard", "omni"])
async def test_real_http_mcp_browser_and_private_core_grading(
    tmp_path, task, media_website, control_path, external, profile
):
    url, state = media_website
    task.raw_task["private_marker"] = "PRIVATE_GRADER_MARKER"
    config = {
        "task": task.raw_task,
        "urls": {"jobportal": url},
        "media": MediaSettings(
            enabled=profile != "browser-only",
            profile="omni" if profile == "omni" else "standard",
            audio=profile == "omni", video=profile == "omni",
            transcription="disabled",
        ).as_dict(),
    }
    async with open_session(
        config, tmp_path / "evidence", fixture_urls=None if external else config["urls"]
    ) as episode:
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(make_app(episode), log_level="error"))
        serving = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(0.02)
            base = f"http://127.0.0.1:{port}"
            async with httpx.AsyncClient() as http:
                assert (await http.get(base + "/health")).status_code == 200
                for path in ("/finalize", "/result.json", "/evaluate", "/json/version"):
                    assert (await http.get(base + path)).status_code == 404
            async with control_socket(episode, control_path):
                async with Client(base + "/mcp") as client:
                    names = {t.name for t in (await client.list_tools()).tools}
                    assert "webarena_submit" in names
                    assert "PRIVATE_GRADER_MARKER" not in str((await client.list_tools()).tools)
                    expected_media = (
                        set() if profile == "browser-only" else {"media_extract_frames", "media_watch"}
                    )
                    if profile == "omni":
                        expected_media |= {"media_listen", "media_watch"}
                    assert {name for name in names if name.startswith("media_")} == expected_media
                    assert (
                        not {"browser_evaluate", "browser_run_code", "media_inventory", "evaluate"}
                        & names
                    )
                    closed = await client.call_tool("browser_tabs", {"action": "close"})
                    assert closed.is_error
                    assert "last browser tab" in " ".join(
                        p.text for p in closed.content if p.type == "text"
                    )
                    assert not (
                        await client.call_tool("browser_tabs", {"action": "new", "url": url})
                    ).is_error
                    assert not (
                        await client.call_tool("browser_tabs", {"action": "close"})
                    ).is_error
                    result = await client.call_tool("browser_snapshot", {})
                    text = "\n".join(p.text for p in result.content if p.type == "text")
                    ref = re.search(r'button "Save" \[ref=([^\]]+)\]', text).group(1)
                    clicked = await client.call_tool("browser_click", {
                        "target": ref, "webarena_rationale": "Save the completed form",
                    })
                    assert not clicked.is_error
                    assert any(part.type == "image" for part in clicked.content)
                    assert "Saved" in "\n".join(part.text for part in clicked.content if part.type == "text")
                    assert episode.trajectory[-1]["agent_info"] == {"think": "Save the completed form"}
                    assert episode.trajectory[-1]["obs"]["url"].rstrip("/") == url
                    assert state["saved"]
                    blocked = await client.call_tool(
                        "browser_navigate", {"url": url + "/api/eval/state"}
                    )
                    assert blocked.is_error
                    assert state["private_hits"] == 0
                    if expected_media:
                        snapshot = await client.call_tool("browser_snapshot", {})
                        text = "\n".join(p.text for p in snapshot.content if p.type == "text")
                        media_ref = re.search(r"ref=(m[0-9a-f]{24})", text).group(1)
                        arguments = {"ref": media_ref, "start_seconds": 0, "end_seconds": 1}
                        frames = await client.call_tool(
                            "media_extract_frames", {**arguments, "n_frames": 2}
                        )
                        overview = await client.call_tool("media_watch", arguments)
                        for result in (frames, overview):
                            assert not result.is_error
                            assert result.structured_content is None
                            metadata, *images = result.content
                            assert metadata.type == "text"
                            assert len(json.loads(metadata.text)["timestamps"]) == len(images) > 0
                            assert all(
                                p.type == "image" and p.mime_type == "image/jpeg" for p in images
                            )
                        assert len([p for p in frames.content if p.type == "image"]) == 2
                        if profile == "omni":
                            audio = await client.call_tool("media_listen", arguments)
                            assert not audio.is_error
                            assert any(
                                p.type == "audio" and base64.b64decode(p.data).startswith(b"RIFF")
                                for p in audio.content
                            )
                            video = await client.call_tool(
                                "media_watch",
                                {**arguments, "mode": "detail", "include_audio": True},
                            )
                            assert not video.is_error
                            assert video.structured_content == json.loads(video.content[0].text)
                            assert any(
                                p.type == "resource" and p.resource.mime_type == "video/mp4"
                                for p in video.content
                            )
                    before = episode.steps
                # Reconnection cannot reset the action counter or browser state.
                async with Client(base + "/mcp") as client:
                    assert not (
                        await client.call_tool("webarena_submit", {"answer": "42"})
                    ).is_error
                    assert episode.steps == before
                    assert (await client.call_tool("browser_snapshot", {})).is_error
                await finalize(control_path, 30)
                rewards = json.loads((tmp_path / "evidence/result.json").read_text())["rewards"]
                assert rewards["reward"] == rewards["success"] == 1
                assert (tmp_path / f"evidence/evaluation-{episode.steps}-input.json").is_file()
                assert (
                    json.loads((tmp_path / "evidence/evaluation-state.json").read_text())["status"]
                    == "graded"
                )
                assert (
                    json.loads((tmp_path / "evidence/result.json").read_text())["final_answer"]
                    == "42"
                )
        finally:
            server.should_exit = True
            await serving
