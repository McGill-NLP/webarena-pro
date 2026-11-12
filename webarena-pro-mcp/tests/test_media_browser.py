"""Two real MCP transports, real media decoding, a local ASR fixture and an external MCP caller."""

import base64
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from webarena_pro_mcp.media_policy import MediaSettings
from webarena_pro_mcp.session import open_session

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("WP_MCP_BROWSER_TESTS") != "1",
        reason="Set WP_MCP_BROWSER_TESTS=1",
    ),
]


@pytest.mark.parametrize("profile,long_transcription", [
    ("standard", False), ("audio", False), ("video", False), ("omni", False),
    ("standard", True),
])
async def test_two_mcp_servers_media_profiles_and_core_grade(tmp_path, task, monkeypatch, profile, long_transcription):
    from webarena_pro_media.binaries import ffmpeg_binary

    video = tmp_path / "fixture.mp4"
    duration = 125 if long_transcription else 2
    subprocess.run(
        [
            ffmpeg_binary(),
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=s=64x48:r=10:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(video),
        ],
        check=True,
        timeout=30,
    )
    if profile == "omni":
        # A valid trailing MP4 free box reproduces the >32 MiB source regression
        # without making a large, slow-to-decode visual fixture.
        with video.open("ab") as output:
            output.write((33 * 1024 * 1024).to_bytes(4, "big") + b"free")
            output.truncate(output.tell() + 33 * 1024 * 1024 - 8)
    audio_enabled = profile in {"audio", "omni"}
    video_enabled = profile in {"video", "omni"}
    asr, media_cookies, failures = [], [], []
    actions = ["media_listen", "media_extract_frames", "media_watch", "media_transcribe"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, body, mime="application/json", status=200, cookie=False):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            if cookie:
                self.send_header("Set-Cookie", "media_auth=fixture; Path=/; HttpOnly")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/fixture.mp4":
                media_cookies.append(self.headers.get("Cookie", ""))
                if "media_auth=fixture" not in media_cookies[-1]:
                    self.reply(b"Unauthorized", status=401)
                    return
                self.reply(video.read_bytes(), "video/mp4")
            else:
                html = b'<html><title>Media fixture</title><video controls preload="none" src="/fixture.mp4" aria-label="Test clip"></video>'
                if profile == "audio":
                    html += b'<script type="module">const response=await fetch("/fixture.mp4");const blob=await response.blob();document.querySelector("video").src=URL.createObjectURL(blob);</script>'
                self.reply(html + b'</html>', "text/html", cookie=True)


        def do_POST(self):
            try:
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if self.path == "/v1/audio/transcriptions":
                    assert b"RIFF" in body and b"whisper-1" in body
                    asr.append(body)
                    if long_transcription:
                        # Each request fits the 3s API timeout, but three sequential
                        # requests exceed it and need the separate overall deadline.
                        time.sleep(1.2)
                    self.reply(b'{"text":"fixture transcript"}')
                    return
                self.reply(b'{"error":"unknown endpoint"}', status=404)
            except Exception as exc:
                failures.append(exc)
                self.reply(b'{"error":"fixture assertion"}', status=500)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("WEBARENA_PRO_ASR_API_KEY", "fixture-asr-key")
    monkeypatch.setenv("WEBARENA_PRO_ASR_BASE_URL", url + "/v1")
    directory = tmp_path / "evidence"
    config = {
        "task": task.raw_task,
        "urls": {"jobportal": url},
        "max_steps": 5,
        "media": MediaSettings(
            profile="standard" if profile == "standard" else "omni", audio=audio_enabled, video=video_enabled,
            **({"timeout": 3, "transcription_timeout": 30} if long_transcription else {}),
        ).as_dict(),
    }
    try:
        async with open_session(config, directory, fixture_urls=config["urls"]) as session:
            initial = json.loads((directory / "initial.json").read_text())
            ref = re.search(r"ref=(m[0-9a-f]{24})", json.dumps(initial)).group(1)
            names = set(session.tools)
            expected = {"media_extract_frames", "media_transcribe", "media_watch"}
            if audio_enabled:
                expected.add("media_listen")
            assert {name for name in names if name.startswith("media_")} == expected
            assert not {"browser_evaluate", "browser_run_code", "media_inventory", "media_verify"} & names
            results = []
            for name in actions:
                arguments = {"ref": ref, "start_seconds": 0, "end_seconds": 1}
                if name == "media_extract_frames":
                    arguments["n_frames"] = 2
                if name == "media_watch":
                    arguments.update(mode="detail" if video_enabled else "overview", include_audio=audio_enabled and video_enabled, fps=2)
                if name == "media_transcribe" and long_transcription:
                    arguments["end_seconds"] = duration
                started = time.monotonic()
                results.append(await session.call(name, arguments))
                if name == "media_transcribe" and long_transcription:
                    assert time.monotonic() - started > config["media"]["timeout"]
            assert [r["isError"] for r in results] == (
                [not audio_enabled, False, False, False]
            )
            if audio_enabled:
                audio = next(p for p in results[0]["content"] if p["type"] == "audio")
                assert audio["mimeType"] == "audio/wav"
                assert base64.b64decode(audio["data"]).startswith(b"RIFF")
            if video_enabled:
                video_part = next(p for p in results[2]["content"] if p["type"] == "resource")
                assert video_part["resource"]["mimeType"] == "video/mp4"
                assert b"ftyp" in base64.b64decode(video_part["resource"]["blob"])[:32]
            frames = [p for p in results[1]["content"] if p["type"] == "image"]
            assert len(frames) == 2
            assert all(base64.b64decode(p["data"]).startswith(b"\xff\xd8") for p in frames)
            assert "fixture transcript" in json.dumps(results[3])
            assert not (await session.call("webarena_submit", {"answer": "42"}))["isError"]
            result = await session.finalize()
            expected_steps = 4 if profile in {"audio", "omni"} else 3
            assert result["status"] == "graded" and result["steps"] == expected_steps
            assert result["score"] == 1 and result["terminal_evaluation"]["evaluated_at_step"] == expected_steps
            assert not failures, failures
            assert len(asr) == (3 if long_transcription else 1)
            assert media_cookies and all("media_auth=fixture" in c for c in media_cookies)
            assert json.loads((directory / "diagnostics.json").read_text())["downloads"] == []
            servers = json.loads((directory / "mcp_servers.json").read_text())
            server_name = "webarena-pro" if profile == "standard" else "webarena-pro-omni"
            assert set(servers) == {"playwright", server_name}
            assert servers[server_name]["profile"] == ("standard" if profile == "standard" else "omni")
            assert (directory / "browser/mcp-process.json").exists()
            assert (directory / "media/mcp-process.json").exists()
            audit = json.loads(next((directory / "media").glob("transcription-*.json")).read_text())
            if long_transcription:
                assert audit["phase"] == "returned" and len(audit["chunks"]) == 3
                assert all(chunk["phase"] == "returned" for chunk in audit["chunks"])
                assert results[3]["structuredContent"]["transcript"] == "\n".join(["fixture transcript"] * 3)
            assert audit["phase"] == "returned"
            assert (directory / "media/attachments" / audit["audio_sha256"]).read_bytes().startswith(b"RIFF")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
