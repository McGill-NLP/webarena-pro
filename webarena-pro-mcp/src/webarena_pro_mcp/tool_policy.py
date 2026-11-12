"""Fail-closed policy for the agent's only environment action channel."""

from __future__ import annotations

import copy
import math
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator

COORDINATE_TOOLS = frozenset(
    {
        "browser_mouse_click_xy",
        "browser_mouse_drag_xy",
        "browser_mouse_move_xy",
        "browser_mouse_down",
        "browser_mouse_up",
    }
)
COORDINATE_KEYS = {"x", "y", "startX", "startY", "endX", "endY"}

ALLOWED_TOOLS = frozenset(
    {
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_find",
        "browser_navigate",
        "browser_navigate_back",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_select_option",
        "browser_press_key",
        "browser_hover",
        "browser_drag",
        "browser_tabs",
        "browser_handle_dialog",
        "browser_wait_for",
        "browser_file_upload",
    }
) | COORDINATE_TOOLS
REF_KEYS = {"ref", "target", "startRef", "endRef", "startTarget", "endTarget"}
PRIVATE_PATH = re.compile(r"(?:^|/)(?:eval(?:uation)?(?:[_-].*)?|reset(?:[_-].*)?|benchmark)(?:/|\.|$)", re.I)


class PolicyError(ValueError):
    pass


def origin(url: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise PolicyError("Only HTTP(S) task URLs without embedded credentials are allowed")
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError as exc:
        raise PolicyError("Invalid or unauthorized URL") from exc


def canonical_path(url: str) -> str:
    value = urlsplit(url).path
    # Validate the wire representation before decoding. A percent introduced by
    # a valid %25 escape is an application identifier character, not a malformed
    # escape (for example ERPNext's "80% per wafer" document name).
    if re.search(r"%(?![0-9a-fA-F]{2})", value):
        raise PolicyError("Ambiguous URL path")
    for _ in range(8):
        try:
            decoded = unquote(value, errors="strict")
        except UnicodeDecodeError as exc:
            raise PolicyError("Ambiguous URL path") from exc
        if decoded == value:
            break
        value = decoded
    # Still decode nested valid escapes before private-path checks. Only literal
    # percent signs may remain; an escape beyond the depth limit fails closed.
    if re.search(r"%[0-9a-fA-F]{2}", value) or "\\" in value or any(ord(c) < 32 for c in value):
        raise PolicyError("Ambiguous URL path")
    # Treat parameters conservatively; proxies/frameworks may remove them.
    value = "/".join(segment.split(";", 1)[0] for segment in value.split("/"))
    return "/" + posixpath.normpath("/" + value.lstrip("/")).lstrip("/")


class URLPolicy:
    def __init__(self, urls: list[str], blocked_paths: list[str] = ()):
        self.origins = {origin(url) for url in urls}
        self.blocked_paths = {canonical_path(path) for path in blocked_paths}

    def check(self, url: str, *, navigation: bool = False) -> None:
        if any(ord(c) < 33 for c in url) or "\\" in url:
            raise PolicyError("Malformed URL")
        if origin(url) not in self.origins:
            raise PolicyError("URL is outside the selected task websites")
        path = canonical_path(url)
        if PRIVATE_PATH.search(path) or any(
            path == p or path.startswith(p + "/") for p in self.blocked_paths
        ):
            raise PolicyError("Reset/evaluator endpoint is private")
        if navigation and re.match(r"^/(?:api|graphql)(?:/|$)", path, re.I):
            raise PolicyError("Direct navigation to application APIs is not a UI action")


class ToolPolicy:
    def __init__(
        self, urls: list[str], uploads: list[Path] = (), blocked_paths: list[str] = (), *, media=None
    ):
        self.urls = URLPolicy(urls, blocked_paths)
        self.site_urls, self.blocked_paths, self.media = list(urls), list(blocked_paths), media
        self.uploads = {str(p.resolve()) for p in uploads}
        self.schemas: dict[str, dict] = {}
        self.refs: set[str] = set()

    def expose(self, tools: list[dict]) -> list[dict]:
        self.schemas.clear()
        exposed = []
        for tool in tools:
            if tool["name"] not in ALLOWED_TOOLS:
                continue
            schema = copy.deepcopy(tool["inputSchema"])
            # File-producing variants are intentionally unavailable. Screenshot
            # output is automatically named by MCP inside the episode workspace.
            props = schema.setdefault("properties", {})
            for key in ("filename", "isolatedContext", "selector"):
                props.pop(key, None)
            if tool["name"] in COORDINATE_TOOLS:
                for key in COORDINATE_KEYS & props.keys():
                    props[key]["minimum"] = 0
                if "clickCount" in props:
                    props["clickCount"].update(type="integer", minimum=1, maximum=3)
                if "delay" in props:
                    props["delay"].update(minimum=0, maximum=1000)
            schema["additionalProperties"] = False
            self.schemas[tool["name"]] = schema
            exposed.append(
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "inputSchema": schema,
                }
            )
        if not {"browser_snapshot", "browser_navigate", "browser_take_screenshot"} <= self.schemas.keys():
            raise PolicyError("MCP runtime is missing required UI tools")
        return exposed

    def observe(self, text: str) -> None:
        refs = set(re.findall(r"\[ref=([\w-]+)\]", text))
        if refs:
            self.refs = refs

    def validate(self, name: str, args: dict) -> dict:
        if name not in ALLOWED_TOOLS or name not in self.schemas:
            raise PolicyError("Tool is not in the UI allowlist")
        errors = list(Draft202012Validator(self.schemas[name]).iter_errors(args))
        if errors:
            raise PolicyError("Tool arguments do not match the exposed schema")
        if name in COORDINATE_TOOLS and any(
            not math.isfinite(value)
            for key, value in args.items()
            if key in COORDINATE_KEYS | {"delay", "clickCount"}
        ):
            raise PolicyError("Mouse coordinates and click options must be finite")
        if name == "browser_navigate":
            self.urls.check(args["url"], navigation=True)
        if name == "browser_tabs":
            if args.get("action") not in {"list", "new", "close", "select"}:
                raise PolicyError("Unsupported tab operation")
            if args.get("url"):
                self.urls.check(args["url"], navigation=True)
        if name == "browser_file_upload":
            for path in args.get("paths", []):
                p = Path(path)
                if not p.is_absolute() or str(p.resolve()) not in self.uploads or not p.is_file():
                    raise PolicyError("Upload is not a staged episode input")
        if name == "browser_wait_for" and not 0 <= args.get("time", 0) <= 30:
            raise PolicyError("Wait must be between 0 and 30 seconds")
        if name == "browser_press_key":
            key = args["key"]
            plain = {
                "Enter",
                "Tab",
                "Escape",
                "Backspace",
                "Delete",
                "Space",
                "Home",
                "End",
                "ArrowUp",
                "ArrowDown",
                "ArrowLeft",
                "ArrowRight",
                "PageUp",
                "PageDown",
            }
            modified = {
                "Shift+Tab",
                "Shift+Enter",
                "Control+a",
                "Meta+a",
                "Control+z",
                "Meta+z",
                "Control+y",
                "Meta+Shift+z",
            }
            # Canvas editors use these ordinary editing shortcuts without an
            # ARIA target. Do not enable arbitrary modifier combinations.
            modified.update(
                f"{modifier}+{key}"
                for modifier in ("Control", "Meta")
                for key in ("g", "G", "c", "C", "x", "X", "v", "V", "Shift+g", "Shift+G")
            )
            if key not in plain | modified and not (len(key) == 1 and key.isprintable()):
                raise PolicyError("Browser/OS shortcuts are not allowed")

        def check_refs(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in REF_KEYS and item not in self.refs:
                        raise PolicyError("Use a reference from the latest browser observation")
                    check_refs(item)
            elif isinstance(value, list):
                for item in value:
                    check_refs(item)

        check_refs(args)
        return copy.deepcopy(args)
