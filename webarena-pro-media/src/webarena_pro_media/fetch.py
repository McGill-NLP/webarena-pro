"""Framework-neutral media downloading helpers.

The helpers accept an optional synchronous Playwright-compatible page without
importing Playwright at module import time. Authenticated browser sessions can
download protected media without depending on a benchmark or agent framework.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MediaFetchError(RuntimeError):
    """A media download exceeded its configured resource limit."""


_BOUNDED_BROWSER_FETCH_JS = """
async ({url, maxBytes, timeoutMs}) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(url, {credentials: 'include', signal: controller.signal});
        if (!response.ok || (response.headers.get('content-type') || '').includes('text/html'))
            return {error: 'Not a media response'};
        if (Number(response.headers.get('content-length')) > maxBytes) {
            controller.abort();
            return {tooLarge: true};
        }
        const reader = response.body.getReader();
        const chunks = [];
        let size = 0;
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            size += value.length;
            if (size > maxBytes) {
                await reader.cancel();
                return {tooLarge: true};
            }
            chunks.push(value);
        }
        const bytes = new Uint8Array(size);
        let offset = 0;
        for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
        // Base64 avoids serializing every byte as a separate JSON number.
        let binary = '';
        for (let i = 0; i < bytes.length; i += 8192)
            binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
        return {base64: btoa(binary)};
    } catch (error) {
        return {error: error.message};
    } finally {
        clearTimeout(timer);
    }
}
"""

_BROWSER_FETCH_JS = """
async (url) => {
    try {
        const response = await fetch(url, {credentials: 'include'});
        if (!response.ok) return {error: 'status ' + response.status};
        const buffer = await response.arrayBuffer();
        return {data: Array.from(new Uint8Array(buffer))};
    } catch (error) {
        return {error: error.message};
    }
}
"""


def _response_body_is_usable(response: Any, body: bytes) -> bool:
    """Reject common authentication-page responses masquerading as media."""
    headers = getattr(response, "headers", {}) or {}
    content_type = str(headers.get("content-type", "")).lower()
    return bool(body) and "text/html" not in content_type


def fetch_media_bytes(
    url: str,
    *,
    page: Any | None = None,
    timeout: float = 30.0,
    max_bytes: int | None = None,
) -> bytes | None:
    """Fetch media through HTTP, then an authenticated Playwright session.

    A direct HTTP request is the fast path. If it fails and ``page`` is
    provided, the function first tries the page context's request client,
    which shares browser cookies, and finally falls back to ``page.evaluate``.

    Args:
        url: Absolute media URL.
        page: Optional synchronous Playwright-compatible page.
        timeout: Timeout in seconds.
        max_bytes: Optional source byte limit. Oversized sources raise
            MediaFetchError instead of retrying another download strategy.

    Returns:
        Downloaded bytes, or ``None`` when every strategy fails.
    """
    if not url:
        return None
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError("max_bytes must be positive")

    def check_size(size):
        if max_bytes is not None and size > max_bytes:
            raise MediaFetchError(
                f"Media source exceeds the {max_bytes / (1024 * 1024):g} MiB limit."
            )

    try:
        import requests

        response = requests.get(url, timeout=timeout, stream=max_bytes is not None)
        try:
            if response.ok:
                check_size(int(response.headers.get("content-length", 0)))
                if max_bytes is None:
                    body = bytes(response.content)
                else:
                    body = bytearray()
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        check_size(len(body) + len(chunk))
                        body.extend(chunk)
                if _response_body_is_usable(response, body):
                    return bytes(body)
        finally:
            response.close()
    except MediaFetchError:
        raise
    except ImportError:
        logger.debug("requests is not installed; skipping direct media fetch")
    except Exception as error:
        logger.debug("Direct media fetch failed for %s: %s", url, error)

    if page is None:
        logger.warning(
            "Direct media fetch failed and no Playwright page was provided: %s",
            url,
        )
        return None

    request = getattr(getattr(page, "context", None), "request", None)
    if request is not None:
        try:
            response = request.get(url, timeout=timeout * 1000)
            try:
                if response.ok:
                    check_size(
                        int(
                            (getattr(response, "headers", {}) or {}).get(
                                "content-length", 0
                            )
                        )
                    )
                    body = bytes(response.body())
                    check_size(len(body))
                    if _response_body_is_usable(response, body):
                        return body
            finally:
                if hasattr(response, "dispose"):
                    response.dispose()
            logger.debug(
                "Playwright request fetch returned status %s for %s",
                getattr(response, "status", "unknown"),
                url,
            )
        except MediaFetchError:
            raise
        except Exception as error:
            logger.debug("Playwright request fetch failed for %s: %s", url, error)

    try:
        if max_bytes is not None:
            import base64

            result = page.evaluate(
                _BOUNDED_BROWSER_FETCH_JS,
                {
                    "url": url,
                    "maxBytes": max_bytes,
                    "timeoutMs": timeout * 1000,
                },
            )
            if isinstance(result, dict) and result.get("tooLarge"):
                check_size(max_bytes + 1)
            if isinstance(result, dict) and "base64" in result:
                body = base64.b64decode(result["base64"], validate=True)
                check_size(len(body))
                return body or None
        else:
            result = page.evaluate(_BROWSER_FETCH_JS, url)
        if isinstance(result, dict) and "data" in result:
            return bytes(result["data"])
        logger.warning("Browser media fetch failed for %s: %s", url, result)
    except MediaFetchError:
        raise
    except Exception as error:
        logger.warning("Browser media fetch failed for %s: %s", url, error)

    return None
