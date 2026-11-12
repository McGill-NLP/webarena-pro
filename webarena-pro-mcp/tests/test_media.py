import asyncio
import base64
import hashlib
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from mcp.types import CallToolResult
from webarena_pro_mcp.mcp_client import MCPBrowser, UnsupportedObservationError, media_content
from webarena_pro_mcp.media_policy import MEDIA_TOOLS, MediaSettings, schemas, validate
from webarena_pro_mcp.media_server import MediaEngine
from webarena_pro_media.cache import MediaSource
from webarena_pro_mcp.tool_policy import PolicyError, URLPolicy

REF = "m" + "1" * 24
FULL = MediaSettings(profile="omni", audio=True, video=True)


def test_capability_filtered_schemas():
    assert set(schemas(FULL)) == MEDIA_TOOLS
    assert set(schemas(MediaSettings())) == {"media_transcribe", "media_extract_frames", "media_watch"}
    assert "media_transcribe" not in schemas(MediaSettings(transcription="disabled"))
    assert schemas(MediaSettings(enabled=False)) == {}
    with pytest.raises(PolicyError):
        validate("media_watch", {"ref": REF, "mode": "detail"}, MediaSettings())


@pytest.mark.parametrize("name", ["media_listen"])
async def test_standard_profile_rejects_omni_calls_at_client_and_server(name):
    policy = SimpleNamespace(media=MediaSettings())
    client = SimpleNamespace(call_tool=AsyncMock())
    browser = MCPBrowser(None, policy, 10, client)
    with pytest.raises(PolicyError):
        await browser.call(name, {"ref": REF})
    client.call_tool.assert_not_awaited()
    engine = object.__new__(MediaEngine)
    engine.settings = policy.media
    engine.fetch = lambda _: pytest.fail("Disallowed tool fetched media")
    with pytest.raises(PolicyError):
        await engine.perform(name, {"ref": REF})


@pytest.mark.parametrize("audio,video", [(False, False), (True, False), (False, True), (True, True)])
def test_independent_native_capabilities(audio, video):
    settings = MediaSettings(profile="omni" if audio or video else "standard", audio=audio, video=video)
    tools = schemas(settings)
    assert ("media_listen" in tools) == audio
    assert tools["media_watch"]["inputSchema"]["properties"]["mode"]["enum"] == (
        ["overview", "detail", "full"] if video else ["overview"]
    )
    validate("media_watch", {"ref": REF}, settings)
    if not video:
        with pytest.raises(PolicyError):
            validate("media_watch", {"ref": REF, "mode": "full"}, settings)
    if not audio:
        with pytest.raises(PolicyError):
            validate("media_watch", {"ref": REF, "mode": "full", "include_audio": True}, settings)


def test_omni_requires_a_native_capability():
    with pytest.raises(ValueError, match="audio or video"):
        MediaSettings(profile="omni")


async def test_server_entry_points_cannot_serve_the_other_profile():
    from webarena_pro_mcp.media_server import serve

    with pytest.raises(ValueError, match="standard media server cannot serve the omni"):
        await serve({"settings": FULL.as_dict()})
    with pytest.raises(ValueError, match="omni media server cannot serve the standard"):
        await serve({"settings": MediaSettings().as_dict()}, profile="omni")


@pytest.mark.parametrize(
    "arguments",
    [
        {"ref": REF, "url": "http://host/reset"},
        {"ref": "http://host/a.wav"},
        {"ref": REF, "end_seconds": -1},
        {"ref": REF, "start_seconds": -1},
        {"ref": REF, "start_seconds": float("nan")},
        {"ref": REF, "fps": float("nan")},
        {"ref": REF, "max_frames": 121},
        {"ref": REF, "mode": "invalid"},
    ],
)
def test_bounded_media_arguments(arguments):
    with pytest.raises(PolicyError):
        validate("media_watch", arguments, FULL)


def test_only_inline_verified_video_resources_are_accepted():
    blob = b"fixture-mp4"
    resource = {
        "uri": "webarena-media://clip/" + hashlib.sha256(blob).hexdigest(),
        "mimeType": "video/mp4",
        "blob": base64.b64encode(blob).decode(),
    }
    result = CallToolResult.model_validate({"content": [{"type": "resource", "resource": resource}]})
    converted = media_content(result)
    assert converted["content"][0]["resource"] == resource
    resource["uri"] = "file:///private/secret"
    with pytest.raises(UnsupportedObservationError, match="identity"):
        media_content(
            CallToolResult.model_validate({"content": [{"type": "resource", "resource": resource}]})
        )


@pytest.mark.parametrize("destination", ["/private", "http://external.invalid/audio"])
async def test_media_fetch_rejects_redirect_before_private_endpoint(tmp_path, monkeypatch, destination):
    engine = object.__new__(MediaEngine)
    engine.root, engine.settings = tmp_path, MediaSettings()
    engine.policy = URLPolicy(["http://fixture"], ["/private"])
    engine.context = SimpleNamespace(cookies=AsyncMock(return_value=[]))
    engine.resolve = AsyncMock(return_value=(None, {"src": "http://fixture/audio"}))
    visited = []

    def get(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"Location": destination})

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(get), **kwargs)
    )
    with pytest.raises(PolicyError):
        await engine.fetch(REF)
    assert visited == ["http://fixture/audio"]
    engine.context.cookies.assert_awaited_once_with(["http://fixture/audio"])


async def test_source_reference_becomes_stale_when_element_changes():
    engine = object.__new__(MediaEngine)
    frame = SimpleNamespace(
        url="http://fixture/",
        is_detached=lambda: False,
        evaluate=AsyncMock(return_value=[{"index": 0, "src": "http://fixture/new.wav"}]),
    )
    engine.entries = {REF: (frame, {"index": 0, "src": "http://fixture/old.wav"}, frame.url)}
    with pytest.raises(PolicyError, match="changed"):
        await engine.resolve(REF)
    with pytest.raises(PolicyError, match="Unknown"):
        await engine.resolve("m" + "2" * 24)


async def test_async_processing_keeps_loop_live_and_drains_on_cancel(tmp_path, monkeypatch):
    from webarena_pro_media import video

    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    owner = threading.get_ident()
    data = b"validated fixture bytes"
    engine = object.__new__(MediaEngine)
    engine.root, engine.settings = tmp_path, MediaSettings()
    source = MediaSource(tmp_path / "source.media", "fixture", len(data), {})
    engine.fetch = AsyncMock(return_value=(source, {"src": "http://fixture/video"}))
    engine.prune_sources = lambda _: None

    def decode(*args, **kwargs):
        assert threading.get_ident() != owner
        assert kwargs["source"] == source
        assert "page" not in kwargs
        entered.set()
        assert release.wait(5)
        finished.set()
        return [{"image_b64": "aW1hZ2U=", "timestamp": 0}]

    monkeypatch.setattr(video, "extract_video_frames", decode)
    pending = asyncio.create_task(engine.perform("media_extract_frames", {"ref": REF}))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done() and not finished.is_set()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await pending
    assert finished.is_set()


async def test_cancelled_asr_keeps_unknown_outcome_pending(tmp_path, monkeypatch):
    from webarena_pro_media import async_api
    import openai

    engine = object.__new__(MediaEngine)
    engine.root, engine.settings = tmp_path, MediaSettings()
    source = MediaSource(tmp_path / "source.media", "fixture", 6, {})
    engine.fetch = AsyncMock(return_value=(source, {"src": "http://fixture/audio"}))
    monkeypatch.setattr("webarena_pro_media.video.probe_video_duration", lambda _: 30)
    monkeypatch.setattr(async_api, "extract_media_clip", AsyncMock(return_value={"audio_b64": "UklGRg=="}))
    entered, closed = asyncio.Event(), asyncio.Event()

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            assert kwargs["api_key"] == "fixture-asr-key"
            assert kwargs["timeout"] == 180
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self.transcribe))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            closed.set()

        async def transcribe(self, **kwargs):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setenv("WEBARENA_PRO_ASR_API_KEY", "fixture-asr-key")
    monkeypatch.setattr(openai, "AsyncOpenAI", Client)
    pending = asyncio.create_task(engine.perform("media_transcribe", {"ref": REF}))
    await asyncio.wait_for(entered.wait(), 5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert closed.is_set()
    audit = json.loads(next(tmp_path.glob("transcription-*.json")).read_text())
    assert audit["phase"] == "pending"
    assert "fixture-asr-key" not in json.dumps(audit)


def test_full_source_and_long_intervals_remain_bounded():
    assert validate("media_watch", {"ref": REF}, MediaSettings())["end_seconds"] is None
    assert validate("media_extract_frames", {"ref": REF, "end_seconds": 600, "n_frames": 120}, FULL)["end_seconds"] == 600
    assert validate("media_transcribe", {"ref": REF, "end_seconds": 600}, FULL)["end_seconds"] == 600
    assert validate("media_listen", {"ref": REF, "start_seconds": 120}, FULL)["end_seconds"] == 150
    for name, end in [("media_listen", 61), ("media_transcribe", 3601)]:
        with pytest.raises(PolicyError):
            validate(name, {"ref": REF, "end_seconds": end}, FULL)


def http_engine(tmp_path):
    engine = object.__new__(MediaEngine)
    engine.root, engine.settings = tmp_path, MediaSettings()
    engine.policy = URLPolicy(["http://fixture"], ["/private"])
    engine.context = SimpleNamespace(cookies=AsyncMock(return_value=[]))
    engine.resolve = AsyncMock(return_value=(None, {"src": "http://fixture/audio"}))
    return engine


async def test_large_http_source_streams_to_disk(tmp_path, monkeypatch):
    engine = http_engine(tmp_path)
    chunk = b"\0" * 65536

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"RIFF"
            for _ in range(640):
                yield chunk

    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers={"Content-Type": "audio/wav"}, stream=Stream())),
        **kwargs,
    ))
    source, _ = await engine.fetch(REF)
    assert source.size == source.path.stat().st_size == 40 * 1024 * 1024 + 4
    with source.path.open("rb") as data:
        assert hashlib.file_digest(data, "sha256").hexdigest() == source.version
    assert not list((tmp_path / "sources").glob(".fetch-*"))


@pytest.mark.parametrize("failure", ["header", "stream", "container", "cancel"])
async def test_failed_fetch_removes_partial_source(tmp_path, monkeypatch, failure):
    import webarena_pro_mcp.media_server as server

    engine = http_engine(tmp_path)
    monkeypatch.setattr(server, "MAX_SOURCE_BYTES", 65536)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"RIFF" if failure != "container" else b"#EXTM3U"
            if failure == "cancel":
                raise asyncio.CancelledError
            if failure == "stream":
                yield b"x" * 65536

    headers = {"Content-Type": "audio/wav"}
    if failure == "header":
        headers["Content-Length"] = "65537"
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, headers=headers, stream=Stream())), **kwargs,
    ))
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else PolicyError):
        await engine.fetch(REF)
    assert list((tmp_path / "sources").iterdir()) == []


async def test_blob_source_is_consumed_in_chunks_and_reader_is_closed(tmp_path):
    engine = http_engine(tmp_path)
    pieces = iter([base64.b64encode(b"RIFF" + b"x" * 65532).decode(), base64.b64encode(b"y" * 100).decode(), None])

    async def evaluate(script):
        return None if "cancel" in script else next(pieces)

    reader = SimpleNamespace(evaluate=AsyncMock(side_effect=evaluate), dispose=AsyncMock())
    frame = SimpleNamespace(evaluate_handle=AsyncMock(return_value=reader))
    engine.resolve = AsyncMock(return_value=(frame, {"src": "blob:http://fixture/id"}))
    source, _ = await engine.fetch(REF)
    assert source.size == 65636
    reader.dispose.assert_awaited_once()
    assert "cancel" in reader.evaluate.await_args.args[0]


@pytest.mark.parametrize("duration", [600, 3600])
async def test_one_transcription_call_chunks_a_long_interval(tmp_path, monkeypatch, duration):
    from webarena_pro_media import async_api

    engine = http_engine(tmp_path)
    engine.settings = MediaSettings(transcription="local")
    source = MediaSource(tmp_path / "source.media", "fixture", 100, {})
    engine.fetch = AsyncMock(return_value=(source, {"src": "http://fixture/audio"}))
    engine.prune_sources = lambda _: None
    monkeypatch.setattr("webarena_pro_media.video.probe_video_duration", lambda _: duration)
    intervals = []

    async def clip(_url, start, end, **kwargs):
        assert kwargs["source"] is source
        assert 0.1 <= end - start <= 60
        intervals.append((start, end))
        return {"audio_b64": "UklGRg==", "start": start, "end": end}

    monkeypatch.setattr(async_api, "extract_media_clip", clip)
    monkeypatch.setattr(async_api, "transcribe_audio", AsyncMock(return_value="words"))
    result = await engine.perform("media_transcribe", {"ref": REF})
    count = duration // 60
    assert intervals == [(i * 60, (i + 1) * 60) for i in range(count)]
    assert result["structuredContent"]["transcript"] == "\n".join(["words"] * count)
    audit = json.loads(next(tmp_path.glob("transcription-*.json")).read_text())
    assert audit["phase"] == "returned" and len(audit["chunks"]) == count
    assert all(chunk["phase"] == "returned" for chunk in audit["chunks"])


def test_source_pruning_evicts_derived_variants_of_the_current_source(tmp_path, monkeypatch):
    import webarena_pro_mcp.media_server as server

    engine = http_engine(tmp_path)
    keep = tmp_path / "sources/current"
    keep.mkdir(parents=True)
    (keep / "source.media").write_bytes(b"RIFF")
    for name in ["old-clip", "new-clip"]:
        (keep / name).mkdir()
        (keep / name / "clip.mp4").write_bytes(b"1234")
    monkeypatch.setattr(server, "MAX_CACHE_BYTES", 10)
    engine.prune_sources(keep)
    assert (keep / "source.media").exists()
    assert sum(p.stat().st_size for p in keep.rglob("*") if p.is_file()) <= 10


async def test_one_call_surveys_a_real_ten_minute_video(tmp_path):
    import subprocess
    from webarena_pro_media.binaries import ffmpeg_binary

    engine = http_engine(tmp_path)
    directory = tmp_path / "sources/fixture"
    directory.mkdir(parents=True)
    path = directory / "source.media"
    subprocess.run([
        ffmpeg_binary(), "-nostdin", "-y", "-v", "error", "-f", "lavfi",
        "-i", "color=c=blue:s=64x48:r=1:d=600", "-c:v", "libx264",
        "-preset", "ultrafast", "-f", "mp4", str(path),
    ], check=True, timeout=30)
    source = MediaSource(path, "fixture", path.stat().st_size, {})
    engine.fetch = AsyncMock(return_value=(source, {"src": "http://fixture/video"}))
    frames = await engine.perform("media_extract_frames", {"ref": REF, "n_frames": 20})
    overview = await engine.perform("media_watch", {"ref": REF})
    for result in [frames, overview]:
        assert len([p for p in result["content"] if p["type"] == "image"]) == 20
        assert max(result["structuredContent"]["timestamps"]) > 550
    assert overview["structuredContent"]["duration"] == 600


@pytest.mark.parametrize("url,category", [
    ("http://outside.fixture/path?token=secret", "outside_task_origins"),
    ("http://fixture/api/eval/state?token=secret", "private_endpoint"),
    ("http://fixture/api/list?token=secret", "application_api"),
    ("http://user:secret@fixture/path", "unsupported_or_invalid_url"),
    ("chrome://version", "unsupported_or_invalid_url"),
    ("chrome-error://chromewebdata/forged", "unsupported_or_invalid_url"),
    ("about:blank#forged", "unsupported_or_invalid_url"),
])
async def test_inventory_does_not_relax_url_policy_and_redacts_diagnostics(tmp_path, monkeypatch, url, category):
    from webarena_pro_mcp.media_server import MediaPagePolicyError

    engine = http_engine(tmp_path)
    engine.context = object()
    monkeypatch.setattr("webarena_pro_mcp.media_server.resolve_page", AsyncMock(return_value=object()))
    with pytest.raises(MediaPagePolicyError) as failure:
        await engine.discover({"target_id": "fixture", "loader_id": "document", "url": url})
    assert failure.value.category == category
    assert "page_url" in str(failure.value)
    assert "secret" not in str(failure.value) and url not in str(failure.value)


@pytest.mark.parametrize("url,category", [("about:blank", "blank"), ("chrome-error://chromewebdata/", "browser_error")])
async def test_browser_owned_empty_document_requires_verified_identity(tmp_path, monkeypatch, url, category):
    from webarena_pro_mcp.browser_identity import BrowserIdentityError

    engine = http_engine(tmp_path)
    engine.context = object()
    page = object()
    monkeypatch.setattr("webarena_pro_mcp.media_server.resolve_page", AsyncMock(return_value=page))
    verify = AsyncMock()
    monkeypatch.setattr("webarena_pro_mcp.media_server.verify_identity", verify)
    identity = {"target_id": "fixture", "loader_id": "document", "url": url}
    assert await engine.discover(identity) == []
    verify.assert_awaited_once_with(page, identity)
    assert engine.inventory_diagnostic == {"status": "no_media", "stage": "page_url", "url_category": category}
    verify.side_effect = BrowserIdentityError("changed")
    with pytest.raises(BrowserIdentityError):
        await engine.discover(identity)
