"""Disk-backed media sources, isolated to an authenticated browser context.

HTTP validators are checked on every use. A source without a validator is
downloaded again and content-addressed, so a mutable URL never silently serves
stale media. Browser-only fallback downloads have a smaller, explicit memory
bound because Playwright's request API buffers responses.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit
import weakref

from .fetch import MediaFetchError, fetch_media_bytes

MAX_VIDEO_SOURCE_BYTES = 512 * 1024 * 1024
MAX_BROWSER_SOURCE_BYTES = 32 * 1024 * 1024
MAX_CACHE_BYTES = 1024 * 1024 * 1024
MAX_CACHE_SOURCES = 8


@dataclass
class MediaSource:
    path: Path
    version: str
    size: int
    headers: dict[str, str]
    cached: bool = False


class MediaSourceCache:
    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="webarena-pro-media-")
        self.root = Path(self._temporary.name)
        self.sources: dict[str, MediaSource] = {}

    def close(self):
        self.sources.clear()
        self._temporary.cleanup()

    def _prune(self, keep: Path | None = None):
        directories = sorted(
            (p for p in self.root.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
        )
        sizes = {p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) for p in directories}
        for directory in directories:
            if len(sizes) <= MAX_CACHE_SOURCES and sum(sizes.values()) <= MAX_CACHE_BYTES:
                break
            if directory == keep:
                continue
            shutil.rmtree(directory)
            sizes.pop(directory)
        self.sources = {k: v for k, v in self.sources.items() if v.path.exists()}

    def get(self, url: str, *, page: Any = None, max_bytes: int = MAX_VIDEO_SOURCE_BYTES) -> MediaSource:
        cookies = []
        context = getattr(page, "context", None)
        if context is not None and hasattr(context, "cookies"):
            try:
                cookies = context.cookies([url])
            except Exception:
                # A blob URL may not be accepted by the cookie API.
                cookies = []
        return self.get_with_session(
            url, cookies=cookies, referer=getattr(page, "url", ""), max_bytes=max_bytes,
            fetch_fallback=lambda url, **kwargs: fetch_media_bytes(url, page=page, **kwargs),
        )

    def get_with_session(
        self, url: str, *, cookies: list, referer: str, fetch_fallback,
        max_bytes: int = MAX_VIDEO_SOURCE_BYTES, source_bytes: bytes | None = None,
    ) -> MediaSource:
        """Download using captured session data; never accesses a browser object.

        Async callers can perform browser fallback on their owning event loop,
        then supply source_bytes to commit that download through the same cache.
        Callers must serialize access through processing and cleanup.
        """
        if not url or urlsplit(url).scheme not in {"http", "https", "blob"}:
            raise MediaFetchError("watch() requires an HTTP(S) or browser blob media URL.")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.root.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(json.dumps([url, cookies], sort_keys=True).encode()).hexdigest()
        previous = self.sources.get(key)
        if previous and (not previous.path.exists() or previous.size > max_bytes):
            previous = None
        request_headers = {}
        if previous:
            if previous.headers.get("etag"):
                request_headers["If-None-Match"] = previous.headers["etag"]
            elif previous.headers.get("last-modified"):
                request_headers["If-Modified-Since"] = previous.headers["last-modified"]
        if referer and referer.startswith(("http://", "https://")):
            request_headers["Referer"] = referer
        staging = self.root / "download.part"
        response_headers = {}
        try:
            if source_bytes is None and urlsplit(url).scheme in {"http", "https"}:
                import requests

                jar = requests.cookies.RequestsCookieJar()
                for cookie in cookies:
                    jar.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ""), path=cookie.get("path", "/"), secure=cookie.get("secure", False))
                try:
                    response = requests.get(url, headers=request_headers, cookies=jar, stream=True, timeout=(10, 30))
                    try:
                        if response.status_code == 304 and previous and request_headers:
                            previous.path.parent.touch()
                            return MediaSource(previous.path, previous.version, previous.size, previous.headers, True)
                        response_headers = {k.lower(): v for k, v in response.headers.items()}
                        if response.ok and "text/html" not in response_headers.get("content-type", "").lower():
                            if int(response_headers.get("content-length", 0)) > max_bytes:
                                raise MediaFetchError(f"Video source exceeds the {max_bytes / 1024**2:g} MiB download limit.")
                            size = 0
                            deadline = time.monotonic() + 180
                            with staging.open("wb") as output:
                                for chunk in response.iter_content(chunk_size=64 * 1024):
                                    if time.monotonic() > deadline:
                                        raise MediaFetchError("Video download exceeded 180 seconds; use a smaller source.")
                                    size += len(chunk)
                                    if size > max_bytes:
                                        raise MediaFetchError(f"Video source exceeds the {max_bytes / 1024**2:g} MiB download limit.")
                                    output.write(chunk)
                    finally:
                        response.close()
                except MediaFetchError:
                    raise
                except (requests.RequestException, ValueError):
                    staging.unlink(missing_ok=True)

            if not staging.exists() or staging.stat().st_size == 0:
                data = source_bytes if source_bytes is not None else fetch_fallback(url, max_bytes=min(max_bytes, MAX_BROWSER_SOURCE_BYTES))
                if data and len(data) > max_bytes:
                    raise MediaFetchError("Video source exceeds the configured download limit.")
                if not data:
                    raise MediaFetchError("Could not fetch video; check its URL and browser authentication.")
                staging.write_bytes(data)
                response_headers = {}
            digest = hashlib.sha256()
            with staging.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            version = digest.hexdigest()
            directory = self.root / f"{key}-{version}"
            directory.mkdir(exist_ok=True)
            path = directory / "source.media"
            reused = path.exists()
            staging.replace(path)
            directory.touch()
            result = MediaSource(path, version, path.stat().st_size, response_headers, reused)
            self.sources[key] = result
            self._prune(keep=directory)
            return result
        finally:
            staging.unlink(missing_ok=True)


_CONTEXT_CACHES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_DEFAULT_CACHE: MediaSourceCache | None = None


def media_source_cache(page: Any = None) -> MediaSourceCache:
    global _DEFAULT_CACHE
    if page is None:
        if _DEFAULT_CACHE is None:
            _DEFAULT_CACHE = MediaSourceCache()
        return _DEFAULT_CACHE
    context = getattr(page, "context", page)
    try:
        cache = _CONTEXT_CACHES.get(context)
    except TypeError:
        # Lightweight test/third-party page objects may not support weak refs.
        cache = getattr(context, "_webarena_media_cache", None)
        if cache is None:
            cache = MediaSourceCache()
            setattr(context, "_webarena_media_cache", cache)
        return cache
    if cache is None:
        cache = MediaSourceCache()
        _CONTEXT_CACHES[context] = cache
        weakref.finalize(context, cache.close)
        if hasattr(context, "on"):
            context.on("close", lambda *args: cache.close())
    return cache


def clear_media_cache(page: Any = None) -> None:
    """Discard a context's media on reset, or all process caches when omitted."""
    global _DEFAULT_CACHE
    if page is None:
        if _DEFAULT_CACHE is not None:
            _DEFAULT_CACHE.close()
            _DEFAULT_CACHE = None
        for cache in list(_CONTEXT_CACHES.values()):
            cache.close()
        _CONTEXT_CACHES.clear()
    else:
        context = getattr(page, "context", page)
        try:
            cache = _CONTEXT_CACHES.pop(context, None)
        except TypeError:
            cache = getattr(context, "_webarena_media_cache", None)
            if cache is not None:
                delattr(context, "_webarena_media_cache")
        if cache is not None:
            cache.close()
