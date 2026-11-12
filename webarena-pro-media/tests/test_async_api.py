import asyncio
import inspect
import io
import shutil
import subprocess
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from webarena_pro_media import async_api, sync_api, audio, fetch, watch
from webarena_pro_media.cache import MediaSource


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(16000)
        sound.writeframes(b"\x01\x00" * 32000)
    return output.getvalue()


@pytest.fixture
def website():
    payload = wav_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_GET(self):
            if self.path == "/private.wav":
                if "session=fixture" not in self.headers.get("Cookie", ""):
                    self.send_response(403)
                    self.end_headers()
                    return
                body, kind = payload, "audio/wav"
            else:
                body, kind = b"<main>media fixture</main>", "text/html"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", '"fixture"')
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}", payload
    server.shutdown()
    server.server_close()
    worker.join()


def test_both_apis_have_matching_parameters_and_defaults():
    assert set(sync_api.__all__) == set(async_api.__all__)
    for name in sync_api.__all__:
        sync, asynchronous = getattr(sync_api, name), getattr(async_api, name)
        if inspect.isclass(sync) or name == "audio_bytes_to_base64":
            assert sync is asynchronous
            continue
        assert inspect.iscoroutinefunction(asynchronous), name
        a, b = inspect.signature(sync).parameters, inspect.signature(asynchronous).parameters
        assert set(a) == set(b), name
        for param in a:
            assert a[param].default == b[param].default, (name, param)
            assert a[param].kind == b[param].kind, (name, param)


async def test_capture_and_browser_fallback_remain_on_the_event_loop(monkeypatch):
    owner = threading.get_ident()
    async def evaluate(script, *args):
        assert threading.get_ident() == owner
        return {"audio_base64": "YWJj"} if args else True
    page = SimpleNamespace(evaluate=evaluate)
    assert await async_api.extract_audio(page, 0.25) == b"abc"
    monkeypatch.setattr(fetch, "fetch_media_bytes", lambda *args, **kwargs: None)
    async def bounded(script, argument):
        assert threading.get_ident() == owner
        assert argument["maxBytes"] == 3
        return {"base64": "YWJj"}
    page.evaluate = bounded
    assert await async_api.fetch_media_bytes("blob:fixture", page=page, max_bytes=3) == b"abc"
    page.evaluate = AsyncMock(return_value={"tooLarge": True})
    with pytest.raises(async_api.MediaFetchError, match="limit"):
        await async_api.fetch_media_bytes("blob:fixture", page=page, max_bytes=3)


async def test_authenticated_async_playwright_requests(website):
    url, payload = website
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch()
        try:
            context = await browser.new_context()
            await context.add_cookies([{"name": "session", "value": "fixture", "url": url}])
            page = await context.new_page()
            await page.goto(url)
            assert await async_api.fetch_media_bytes(url + "/private.wav", page=page) == payload
            with pytest.raises(async_api.MediaFetchError):
                await async_api.fetch_media_bytes(url + "/private.wav", page=page, max_bytes=10)
            state = async_api._cache_state(page)
            source = await async_api._source(state, url + "/private.wav", page)
            assert source.path.read_bytes() == payload
            await async_api.clear_media_cache(page)
            assert not source.path.exists()
        finally:
            await browser.close()


async def test_response_is_disposed_after_limit_failure(monkeypatch):
    monkeypatch.setattr(fetch, "fetch_media_bytes", lambda *args, **kwargs: None)
    response = SimpleNamespace(ok=True, headers={"content-length": "20"}, body=AsyncMock(), dispose=AsyncMock())
    page = SimpleNamespace(context=SimpleNamespace(request=SimpleNamespace(get=AsyncMock(return_value=response))))
    with pytest.raises(async_api.MediaFetchError):
        await async_api.fetch_media_bytes("http://fixture/a", page=page, max_bytes=10)
    response.dispose.assert_awaited_once()
    response.body.assert_not_awaited()


async def test_workers_do_not_block_loop_and_finish_cleanup_before_cancellation():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    owner = threading.get_ident()
    def work():
        assert threading.get_ident() != owner
        entered.set()
        assert release.wait(5)
        finished.set()
    task = asyncio.create_task(async_api._offload(work))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done() and not finished.is_set()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


async def test_async_processors_match_sync_results(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("real media comparison requires ffmpeg and ffprobe")
    raw = wav_bytes()
    expected = await asyncio.to_thread(sync_api.extract_media_clip, "http://metadata/audio", 0, 1, n_frames=0, source_bytes=raw)
    actual = await async_api.extract_media_clip("http://metadata/audio", 0, 1, n_frames=0, source_bytes=raw)
    assert actual == expected
    monkeypatch.setattr(audio, "_transcribe_api", lambda data, language: "fixture transcript")
    assert await async_api.transcribe_audio(raw) == "fixture transcript"
    monkeypatch.setattr(async_api, "fetch_media_bytes", AsyncMock(return_value=raw))
    assert await async_api.transcribe_media("http://metadata/audio", 0, 1) == "fixture transcript"
    path = tmp_path / "video.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x48:r=10:d=2", "-c:v", "mpeg4", str(path)], check=True)
    data = path.read_bytes()
    expected_frames = await asyncio.to_thread(sync_api.extract_video_frames, "http://metadata/video", 2, source_bytes=data)
    assert await async_api.extract_video_frames("http://metadata/video", 2, source_bytes=data) == expected_frames
    source = MediaSource(path, "fixture", len(data), {})
    fetcher = AsyncMock(side_effect=AssertionError("Validated disk sources must not fetch"))
    monkeypatch.setattr(async_api, "fetch_media_bytes", fetcher)
    assert await async_api.extract_video_frames("http://metadata/video", 2, source=source) == expected_frames
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(raw)
    audio_source = MediaSource(audio_path, "audio", len(raw), {})
    assert await async_api.extract_media_clip("http://metadata/audio", 0, 1, n_frames=0, source=audio_source) == expected
    fetcher.assert_not_awaited()
    kwargs = dict(mode="overview", source=source)
    expected_watch = await asyncio.to_thread(sync_api.extract_watch_clip, "http://metadata/video", **kwargs)
    actual_watch = await async_api.extract_watch_clip("http://metadata/video", **kwargs)
    # The second call may reuse the derived clip cache, preserving the evidence.
    assert actual_watch["frames"] == expected_watch["frames"]
    assert actual_watch["source_version"] == "fixture"


async def test_invalid_requests_fail_before_fetch(monkeypatch):
    fetcher = AsyncMock(side_effect=AssertionError("Invalid requests must not fetch"))
    monkeypatch.setattr(async_api, "fetch_media_bytes", fetcher)
    with pytest.raises(async_api.MediaClipError):
        await async_api.extract_media_clip("http://fixture", -1, 100)
    with pytest.raises(async_api.MediaClipError):
        await async_api.extract_watch_clip("http://fixture", fps=100)
    with pytest.raises(async_api.TranscriptionError):
        await async_api.transcribe_media("http://fixture", 10, 5)
    fetcher.assert_not_awaited()


async def test_cache_clear_waits_for_processing(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    state = async_api._cache_state(None)
    path = state.cache.root / "source.media"
    path.write_bytes(b"fixture")
    monkeypatch.setattr(async_api, "_source", AsyncMock(return_value=MediaSource(path, "x", 7, {})))
    def process(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        assert path.exists()
        return {"done": True}
    monkeypatch.setattr(watch, "extract_watch_clip", process)
    task = asyncio.create_task(async_api.extract_watch_clip("http://fixture"))
    assert await asyncio.to_thread(entered.wait, 5)
    clearing = asyncio.create_task(async_api.clear_media_cache())
    await asyncio.sleep(0)
    assert not clearing.done()
    release.set()
    assert await task == {"done": True}
    await clearing
    assert not path.exists()


def test_media_imports_without_core_or_agent_frameworks():
    import sys
    subprocess.run([sys.executable, "-c", '''
import importlib.abc
import sys
class NoBenchmarkPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'webarena_pro_core', 'browsergym', 'agentlab'}:
            raise ImportError('benchmark package intentionally unavailable: ' + fullname)
sys.meta_path.insert(0, NoBenchmarkPackages())
from webarena_pro_media import sync_api, async_api
assert sync_api.audio_bytes_to_base64(b'abc') == 'YWJj'
assert async_api.MediaClipError is sync_api.MediaClipError
'''], check=True)
