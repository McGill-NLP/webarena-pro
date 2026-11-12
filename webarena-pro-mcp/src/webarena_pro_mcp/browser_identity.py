"""Private browser-owned target/document identity across independent CDP clients."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class BrowserIdentityError(RuntimeError):
    """The selected target/document changed; recapture within a bounded operation."""


# Only this constant is sent to the private runtime code tool. No caller, task,
# URL, page text or selector is interpolated, and no JavaScript runs in the page.
# The tool remains absent from the public allowlist and session tool schemas.
IDENTITY_PROBE = """async (page) => {
  const session = await page.context().newCDPSession(page);
  try {
    const {targetInfo} = await session.send('Target.getTargetInfo');
    const {frameTree} = await session.send('Page.getFrameTree');
    const frame = frameTree.frame;
    return {target_id: targetInfo.targetId, loader_id: frame.loaderId,
            url: frame.url + (frame.urlFragment || '')};
  } finally { await session.detach(); }
}"""

IDENTITY_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "string", "minLength": 1}
                   for key in ("target_id", "loader_id", "url")},
    "required": ["target_id", "loader_id", "url"],
    "additionalProperties": False,
}


async def page_identity(page):
    session = await page.context.new_cdp_session(page)
    try:
        target = (await session.send("Target.getTargetInfo"))["targetInfo"]
        frame = (await session.send("Page.getFrameTree"))["frameTree"]["frame"]
        return {"target_id": target["targetId"], "loader_id": frame["loaderId"],
                "url": frame["url"] + frame.get("urlFragment", "")}
    finally:
        await session.detach()


async def verify_identity(page, expected):
    try:
        current = await page_identity(page)
    except Exception as exc:
        raise BrowserIdentityError("Selected browser target is no longer available") from exc
    if current != expected:
        raise BrowserIdentityError("Selected browser document changed during capture")


async def resolve_page(context, expected):
    # Page enumeration order is client-local. Never substitute a page with the
    # same URL, and never use the MCP tab index to index another client's list.
    for attempt in range(3):
        for page in context.pages:
            try:
                current = await page_identity(page)
            except Exception:
                continue  # A different tab can close while targets are enumerated.
            if current["target_id"] == expected["target_id"]:
                if current != expected:
                    raise BrowserIdentityError("Selected browser document changed before capture")
                return page
        if attempt < 2:
            await asyncio.sleep(0.025)  # Permit this client's target-created event to arrive.
    raise BrowserIdentityError("Selected browser target is no longer available")


def browser_document_kind(url):
    """Recognize exact browser-owned empty/error documents, never a URL prefix.

    These are observations of an already verified target, not navigable URLs or
    additional permitted task origins. Agent navigation still uses URLPolicy.
    """
    return {"about:blank": "blank", "chrome-error://chromewebdata/": "browser_error"}.get(url)


@asynccontextmanager
async def identity_capture(page, expected):
    """Classify a failed capture as retryable only if its identity changed."""
    try:
        yield
    except Exception:
        await verify_identity(page, expected)
        raise
    await verify_identity(page, expected)
