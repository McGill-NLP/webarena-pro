"""Async media API: browser I/O stays on its owning event loop.

Blocking HTTP, decoding and transcription run in workers with plain inputs.
Cancellation waits for a worker to finish its bounded operation and clean up;
no background worker is allowed to race cache cleanup after cancellation.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import weakref
from typing import Any

from . import audio, binaries, clips, fetch, video, watch
from .audio import TranscriptionError, audio_bytes_to_base64
from .cache import MAX_BROWSER_SOURCE_BYTES, MediaSource, MediaSourceCache
from .clips import MediaClipError
from .fetch import MediaFetchError

logger = logging.getLogger(__name__)


async def _offload(function, /, *args, **kwargs):
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # The worker owns temporary files/cache state until its finally blocks
        # finish. Preserve cancellation even if the worker itself then fails.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()
        raise


async def ffmpeg_binary() -> str:
    return await _offload(binaries.ffmpeg_binary)


async def ffprobe_binary() -> str:
    return await _offload(binaries.ffprobe_binary)


async def install_audio_capture(page: Any) -> None:
    try:
        await page.evaluate(audio.AUDIO_CAPTURE_INSTALL_JS)
    except Exception as error:
        logger.warning("Failed to install audio capture scripts: %s", error)


async def extract_audio(page: Any, duration: float = 5.0) -> bytes | None:
    await install_audio_capture(page)
    try:
        result = await page.evaluate(audio.AUDIO_CAPTURE_FULL_JS, int(duration * 1000))
    except Exception as error:
        logger.warning("Audio capture failed: %s", error)
        return None
    if isinstance(result, dict) and "audio_base64" in result and "error" not in result:
        return base64.b64decode(result["audio_base64"]) or None
    return None


async def fetch_media_bytes(
    url: str, *, page: Any | None = None, timeout: float = 30.0,
    max_bytes: int | None = None,
) -> bytes | None:
    """Use HTTP, authenticated browser requests, then in-page fetch."""
    if not url:
        return None
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    data = await _offload(fetch.fetch_media_bytes, url, timeout=timeout, max_bytes=max_bytes)
    if data is not None or page is None:
        return data

    def check_size(size):
        if max_bytes is not None and size > max_bytes:
            raise MediaFetchError(f"Media source exceeds the {max_bytes / (1024 * 1024):g} MiB limit.")

    request = getattr(getattr(page, "context", None), "request", None)
    if request is not None:
        try:
            response = await request.get(url, timeout=timeout * 1000)
            try:
                if response.ok:
                    check_size(int((response.headers or {}).get("content-length", 0)))
                    body = bytes(await response.body())
                    check_size(len(body))
                    if fetch._response_body_is_usable(response, body):
                        return body
            finally:
                await response.dispose()
        except MediaFetchError:
            raise
        except Exception as error:
            logger.debug("Playwright request fetch failed for %s: %s", url, error)
    try:
        if max_bytes is not None:
            result = await page.evaluate(fetch._BOUNDED_BROWSER_FETCH_JS, {
                "url": url, "maxBytes": max_bytes, "timeoutMs": timeout * 1000,
            })
            if isinstance(result, dict) and result.get("tooLarge"):
                check_size(max_bytes + 1)
            if isinstance(result, dict) and "base64" in result:
                body = base64.b64decode(result["base64"], validate=True)
                check_size(len(body))
                return body or None
        else:
            result = await page.evaluate(fetch._BROWSER_FETCH_JS, url)
        if isinstance(result, dict) and "data" in result:
            return bytes(result["data"])
    except MediaFetchError:
        raise
    except Exception as error:
        logger.warning("Browser media fetch failed for %s: %s", url, error)
    return None


async def transcribe_audio(audio_bytes: bytes | None, language: str | None = None, use_api: bool = True) -> str:
    return await _offload(audio.transcribe_audio, audio_bytes, language=language, use_api=use_api)


async def transcribe_media(
    url: str, start_seconds: float = 0, end_seconds: float = -1,
    page: Any | None = None, language: str | None = None, use_api: bool = True,
) -> str:
    start, end = audio._validate_range(start_seconds, end_seconds)
    if not url:
        raise TranscriptionError("No media URL was provided for transcription.")
    data = await fetch_media_bytes(url, page=page, timeout=15.0)
    if data is None:
        raise TranscriptionError("Could not fetch media for transcription. Check the URL and browser authentication.")
    return await _offload(audio._transcribe_prepared, data, language, use_api, start, end)


async def extract_video_frames(
    url: str, n_frames: int = 5, start_seconds: float = 0, end_seconds: float = -1,
    page: Any | None = None, width: int = 1280, *, source_bytes: bytes | None = None,
    source: MediaSource | None = None,
) -> list[video.ExtractedFrame]:
    if not url or n_frames <= 0:
        return []
    data = None if source is not None else (source_bytes if source_bytes is not None else await fetch_media_bytes(url, page=page))
    if source is None and data is None:
        return []
    return await _offload(video.extract_video_frames, url, n_frames, start_seconds, end_seconds,
                          width=width, source_bytes=data, source=source)


async def extract_media_clip(
    url: str, start_seconds: float = 0, end_seconds: float = 30, *,
    n_frames: int = 3, page: Any | None = None, source_bytes: bytes | None = None,
    source: MediaSource | None = None,
) -> dict[str, Any]:
    clips._validate_clip_request(url, start_seconds, end_seconds, n_frames)
    try:
        data = None if source is not None else (source_bytes if source_bytes is not None else await fetch_media_bytes(url, page=page, max_bytes=clips.MAX_SOURCE_BYTES))
    except MediaFetchError as error:
        raise MediaClipError(str(error)) from error
    # b"" preserves the sync error without starting another HTTP download.
    return await _offload(clips.extract_media_clip, url, start_seconds, end_seconds,
                          n_frames=n_frames, source_bytes=data or b"", source=source)


class _BrowserFetchRequired(Exception):
    pass


def _browser_fallback(*args, **kwargs):
    raise _BrowserFetchRequired


class _CacheState:
    def __init__(self):
        self.cache = MediaSourceCache()
        self.lock = asyncio.Lock()
        self.loop = weakref.ref(asyncio.get_running_loop())


_CACHES: weakref.WeakSet = weakref.WeakSet()


def _cache_state(page):
    owner = getattr(page, "context", page) if page is not None else asyncio.get_running_loop()
    state = getattr(owner, "_webarena_async_media_cache", None)
    if state is None:
        state = _CacheState()
        setattr(owner, "_webarena_async_media_cache", state)
        _CACHES.add(state)
        try:
            weakref.finalize(owner, state.cache.close)
        except TypeError:
            pass  # Lightweight third-party contexts may not support weak refs.
        if page is not None and hasattr(owner, "on"):
            async def close(*_):
                async with state.lock:
                    await _offload(state.cache.close)
            owner.on("close", close)
    if state.loop() is not asyncio.get_running_loop():
        raise RuntimeError("A media browser context must remain on its owning event loop")
    return state


async def _source(state, url, page):
    cookies = []
    context = getattr(page, "context", None)
    if context is not None and hasattr(context, "cookies"):
        try:
            cookies = await context.cookies([url])
        except Exception:
            pass
    arguments = dict(cookies=cookies, referer=getattr(page, "url", ""), fetch_fallback=_browser_fallback)
    try:
        return await _offload(state.cache.get_with_session, url, **arguments)
    except _BrowserFetchRequired:
        data = await fetch_media_bytes(url, page=page, max_bytes=MAX_BROWSER_SOURCE_BYTES)
        if not data:
            raise MediaFetchError("Could not fetch video; check its URL and browser authentication.")
        return await _offload(state.cache.get_with_session, url, source_bytes=data, **arguments)


async def extract_watch_clip(
    url: str, start_seconds: float = 0, end_seconds: float | None = None, *,
    mode: str = "overview", fps: float = 1, max_frames: int = watch.MAX_OVERVIEW_FRAMES,
    include_audio: bool = False, max_input_tokens: int = watch.DEFAULT_MEDIA_TOKEN_BUDGET,
    page: Any = None, source: MediaSource | None = None,
) -> dict:
    watch._validate_watch_request(mode, start_seconds, end_seconds, fps, max_frames, include_audio, max_input_tokens)
    kwargs = dict(mode=mode, fps=fps, max_frames=max_frames, include_audio=include_audio, max_input_tokens=max_input_tokens)
    if source is not None:
        return await _offload(watch.extract_watch_clip, url, start_seconds, end_seconds, source=source, **kwargs)
    state = _cache_state(page)
    # Hold the lock through decoding: eviction/reset must not remove its input.
    async with state.lock:
        try:
            source = await _source(state, url, page)
        except MediaFetchError as error:
            raise MediaClipError(str(error)) from error
        return await _offload(watch.extract_watch_clip, url, start_seconds, end_seconds, source=source, **kwargs)


async def clear_media_cache(page: Any = None) -> None:
    """Wait for in-flight processing, then clear this context or this loop's caches."""
    if page is not None:
        states = [_cache_state(page)]
    else:
        states = [state for state in list(_CACHES) if state.loop() is asyncio.get_running_loop()]
    for state in states:
        async with state.lock:
            await _offload(state.cache.close)


__all__ = [
    "MediaClipError", "MediaFetchError", "TranscriptionError", "audio_bytes_to_base64",
    "install_audio_capture", "extract_audio", "fetch_media_bytes", "transcribe_audio",
    "transcribe_media", "extract_media_clip", "extract_video_frames", "extract_watch_clip",
    "clear_media_cache", "ffmpeg_binary", "ffprobe_binary",
]
