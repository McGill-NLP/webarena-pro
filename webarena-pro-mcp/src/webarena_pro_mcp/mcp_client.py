"""Typed MCP transport with validation at the actual dispatch boundary."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from mcp import Client, StdioServerParameters

from .artifacts import atomic_json
from .browser_identity import BrowserIdentityError, IDENTITY_PROBE, IDENTITY_SCHEMA, browser_document_kind
from .observations import active_tab
from .media_policy import MAX_ATTACHMENT_BYTES, MEDIA_TOOLS
from .media_policy import schemas as media_schemas
from .media_policy import validate as validate_media
from .runtime import server_path
from .tool_policy import PolicyError, ToolPolicy


class UnsupportedObservationError(RuntimeError):
    pass


def result_content(result) -> dict:
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    content = payload.get("content", [])
    if any(part.get("type") not in {"text", "image"} for part in content):
        raise UnsupportedObservationError(
            "Unsupported MCP observation content; refusing to fetch arbitrary resources"
        )
    # Console logs are a developer observation channel. Download notifications
    # remain useful UI evidence; never resolve links in either kind of output.
    for part in content:
        if part["type"] == "text":
            part["text"] = re.sub(r"^- New console entries:.*\n?", "", part["text"], flags=re.M)
    return {"content": content, "isError": payload.get("isError", False)}


def text_content(result: dict) -> str:
    return "\n".join(part["text"] for part in result["content"] if part["type"] == "text")


def media_content(result, *, server="webarena-pro"):
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    size = 0
    for part in payload.get("content", []):
        kind = part["type"]
        if kind == "text":
            continue
        if kind in {"image", "audio"}:
            allowed = {"image/jpeg", "image/png"} if kind == "image" else {"audio/wav"}
            if part["mimeType"] not in allowed:
                raise UnsupportedObservationError("Unexpected media MIME type")
            encoded = part["data"]
        elif kind == "resource" and part["resource"].get("mimeType") == "video/mp4":
            encoded = part["resource"].get("blob", "")
        else:
            raise UnsupportedObservationError("Only inline media from the WebArena server is supported")
        if len(encoded) > (MAX_ATTACHMENT_BYTES + 2) // 3 * 4:
            raise UnsupportedObservationError("Media attachment too large")
        blob = base64.b64decode(encoded, validate=True)
        size += len(blob)
        if (
            kind == "resource"
            and part["resource"]["uri"] != "webarena-media://clip/" + hashlib.sha256(blob).hexdigest()
        ):
            raise UnsupportedObservationError("Video resource identity mismatch")
    if size > MAX_ATTACHMENT_BYTES:
        raise UnsupportedObservationError("Media result exceeds 8 MiB")
    return {
        "content": payload.get("content", []),
        "isError": payload.get("isError", False),
        "structuredContent": payload.get("structuredContent", {}),
        "server": server,
    }


class MCPBrowser:
    def __init__(self, client, policy: ToolPolicy, timeout: float, media_client=None):
        self.client, self.policy, self.timeout = client, policy, timeout
        self.media_client = media_client
        self.tools: list[dict] = []
        self.inventory_diagnostic = None

    async def current_url(self):
        """Read a validated active URL from browser state, never page text."""
        result = result_content(await self.client.call_tool(
            "browser_tabs", {"action": "list"}, read_timeout_seconds=self.timeout
        ))
        if result["isError"]:
            raise RuntimeError("Current browser URL is unavailable")
        _, url = active_tab(text_content(result))
        if not browser_document_kind(url):
            self.policy.urls.check(url)
        return url

    async def initialize(self):
        tools, cursor = [], None
        while True:
            result = await self.client.list_tools(cursor=cursor)
            tools.extend(
                tool.model_dump(mode="json", by_alias=True, exclude_none=True) for tool in result.tools
            )
            cursor = result.next_cursor
            if not cursor:
                break
        self.tools = self.policy.expose(tools)
        if self.media_client is not None:
            available = await self.media_client.list_tools()
            definitions = {
                tool.name: tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in available.tools
            }
            for name, definition in media_schemas(self.policy.media).items():
                if name not in definitions or definitions[name]["inputSchema"] != definition["inputSchema"]:
                    raise PolicyError("Media MCP schemas do not match the configured capabilities")
                self.tools.append(definition)

    async def identity(self):
        """Read selected target/document metadata through a fixed private probe."""
        from jsonschema import validate

        result = result_content(await self.client.call_tool(
            "browser_run_code_unsafe", {"code": IDENTITY_PROBE}, read_timeout_seconds=self.timeout
        ))
        if result["isError"]:
            raise BrowserIdentityError("Selected browser identity is unavailable")
        text = text_content(result)
        if not text.startswith("### Result\n"):
            raise BrowserIdentityError("Invalid private browser identity response")
        try:
            identity, _ = json.JSONDecoder().raw_decode(text[len("### Result\n"):])
            validate(identity, IDENTITY_SCHEMA)
        except Exception as exc:
            raise BrowserIdentityError("Invalid private browser identity response") from exc
        return identity

    async def inventory(self):
        async with asyncio.timeout(self.timeout):
            return await self._inventory()

    async def _inventory(self):
        self.inventory_diagnostic = None
        if self.media_client is None:
            return []
        for attempt in range(3):
            try:
                identity = await self.identity()
                result = media_content(
                    await self.media_client.call_tool(
                        "media_inventory", {"identity": identity}, read_timeout_seconds=self.timeout
                    ),
                    server=self.policy.media.server_name,
                )
                if result["isError"]:
                    if result["structuredContent"].get("error_code") == "browser_identity_changed":
                        raise BrowserIdentityError("Media/browser document changed during inventory")
                    raise RuntimeError("Media discovery failed: " + text_content(result))
                if await self.identity() != identity:
                    raise BrowserIdentityError("Media/browser document changed after inventory")
                self.inventory_diagnostic = result["structuredContent"].get("diagnostic")
                return result["structuredContent"]["sources"]
            except BrowserIdentityError:
                if attempt == 2:
                    raise BrowserIdentityError("Media/browser identity did not stabilize after 3 attempts")
                await asyncio.sleep(0.025)

    async def call(self, name: str, arguments: dict) -> dict:
        if name in MEDIA_TOOLS:
            if self.media_client is None:
                raise PolicyError("WebArena media MCP is disabled")
            arguments = validate_media(name, arguments, self.policy.media)
            sources = await self.inventory()
            if arguments["ref"] not in {source["ref"] for source in sources}:
                raise PolicyError("Use a media reference from the current page")
            return media_content(
                await self.media_client.call_tool(
                    name, arguments, read_timeout_seconds=self.policy.media.timeout_for(name)
                ),
                server=self.policy.media.server_name,
            )
        # Internal snapshot/tab queries pass through exactly the same boundary.
        arguments = self.policy.validate(name, arguments)
        if name == "browser_tabs" and arguments.get("action") == "close":
            # Chromium's persistent context exits when its last window closes.
            # Keep the evaluator's browser alive rather than accepting an action
            # that permanently disconnects CDP for the rest of the episode.
            listing = result_content(
                await self.client.call_tool(
                    "browser_tabs", {"action": "list"}, read_timeout_seconds=self.timeout
                )
            )
            from .observations import active_tab

            if listing["isError"]:
                raise RuntimeError("Cannot verify browser tabs before closing one")
            text = text_content(listing)
            active_tab(text)
            tabs = set(re.findall(r"^- (\d+):\s*(?:\(current\)\s*)?\[.*\]\(.*\)\s*$", text, re.MULTILINE))
            if len(tabs) < 2:
                raise PolicyError("The last browser tab must stay open; navigate it instead")
        result = result_content(
            await self.client.call_tool(
                name,
                arguments,
                read_timeout_seconds=self.timeout,
            )
        )
        # The pinned runtime fails stale refs while resolving a locator, before
        # issuing the action. Other upstream errors may follow a partial action
        # and conservatively remain counted.
        if result["isError"] and re.search(
            r"^(?:Error: )?Ref [\w-]+ not found in the current page snapshot\. Try capturing new snapshot\.$",
            text_content(result), re.MULTILINE,
        ):
            result["rejected_before_action"] = True
        # This pinned MCP version puts automatic snapshots in .yml files.
        # Request an explicit inline snapshot through MCP instead of granting
        # file access or interpreting arbitrary Markdown links as read requests.
        needs_snapshot = name not in {"browser_snapshot", "browser_find", "browser_take_screenshot"}
        if name == "browser_tabs" and arguments.get("action") == "list":
            needs_snapshot = False
        if needs_snapshot:
            snapshot_args = self.policy.validate("browser_snapshot", {})
            snapshot = result_content(
                await self.client.call_tool(
                    "browser_snapshot",
                    snapshot_args,
                    read_timeout_seconds=self.timeout,
                )
            )
            result["automatic_observation"] = snapshot
            result["content"].extend(snapshot["content"])
            self.policy.refs.clear()
        self.policy.observe(text_content(result))
        result["server"] = "playwright"
        if self.media_client is not None:
            sources = await self.inventory()
            if self.inventory_diagnostic:
                result["media_inventory"] = self.inventory_diagnostic
                if self.inventory_diagnostic["url_category"] == "browser_error":
                    result["content"].append({"type": "text", "text":
                        "Media inventory: the selected tab is a browser error page with no eligible media. "
                        "Navigate to a task website or use browser_navigate_back to recover."})
            if sources:
                listing = {
                    "type": "text",
                    "text": "Page media (" + self.policy.media.server_name + " MCP):\n"
                    + "\n".join(
                        f"[media {s['kind']} ref={s['ref']}] "
                        + json.dumps({k: v for k, v in s.items() if k not in {"ref", "kind"}})
                        for s in sources
                    ),
                }
                result["content"].append(listing)
                if "automatic_observation" in result:
                    result["automatic_observation"]["content"].append(listing)
        return result


@asynccontextmanager
async def connect(endpoint: str, workspace: Path, policy: ToolPolicy, timeout: float = 60):
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Do not forward model/evaluator credentials or the caller's MCP configuration.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    params = StdioServerParameters(
        command=sys.executable if os.name == "posix" else "node",
        cwd=workspace,
        env=env,
        args=[
            *([str(Path(__file__).with_name("process_guard.py")), "node"] if os.name == "posix" else []),
            str(server_path()),
            "--cdp-endpoint",
            endpoint,
            "--no-webmcp",
            "--caps",
            "vision",
            "--ignore-roots",
            "--codegen",
            "none",
            "--image-responses",
            "allow",
            "--snapshot-mode",
            "full",
            "--output-dir",
            str(workspace),
            "--timeout-action",
            str(int(min(timeout * 1000 / 2, 15000))),
            "--timeout-navigation",
            str(int(timeout * 1000 / 2)),
        ],
    )
    async with AsyncExitStack() as stack:
        client = await stack.enter_async_context(Client(params, read_timeout_seconds=timeout))
        media_client = None
        if policy.media is not None and policy.media.enabled:
            directory = workspace.parent / "media"
            directory.mkdir(exist_ok=True, mode=0o700)
            config = directory / "server.json"
            atomic_json(
                config,
                {
                    "endpoint": endpoint,
                    "urls": policy.site_urls,
                    "blocked_paths": policy.blocked_paths,
                    "directory": str(directory),
                    "settings": policy.media.as_dict(),
                },
            )
            media_env = dict(env)
            # Only the transcription credential reaches this server; no agent or judge keys.
            for key in (
                "WEBARENA_PRO_ASR_API_KEY",
                "WEBARENA_PRO_ASR_BASE_URL",
                "WEBARENA_PRO_WHISPER_MODEL",
            ):
                if key in os.environ:
                    media_env[key] = os.environ[key]
            media_params = StdioServerParameters(
                command=sys.executable,
                cwd=directory,
                env=media_env,
                args=[
                    *(
                        [str(Path(__file__).with_name("process_guard.py")), sys.executable]
                        if os.name == "posix"
                        else []
                    ),
                    "-m",
                    "webarena_pro_mcp.media_omni_server"
                    if policy.media.profile == "omni"
                    else "webarena_pro_mcp.media_server",
                    str(config),
                ],
            )
            media_client = await stack.enter_async_context(
                Client(media_params, read_timeout_seconds=policy.media.timeout)
            )
        browser = MCPBrowser(client, policy, timeout, media_client)
        await browser.initialize()
        servers = {"playwright": {"tools": list(policy.schemas)}}
        if media_client:
            servers[policy.media.server_name] = {
                "profile": policy.media.profile,
                "tools": list(media_schemas(policy.media)),
            }
        atomic_json(workspace.parent / "mcp_servers.json", servers)
        yield browser
