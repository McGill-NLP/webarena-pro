from unittest.mock import AsyncMock

import pytest
from webarena_pro_mcp.mcp_client import MCPBrowser
from webarena_pro_mcp.tool_policy import COORDINATE_TOOLS, PolicyError, ToolPolicy, URLPolicy


def schemas():
    def tool(name, props, required=()):
        return {"name": name, "inputSchema": {"type": "object", "properties": props, "required": list(required)}}

    return [
        tool("browser_snapshot", {"filename": {"type": "string"}}),
        tool("browser_take_screenshot", {"filename": {"type": "string"}, "scale": {"type": "string"}, "fullPage": {"type": "boolean"}}),
        tool("browser_navigate", {"url": {"type": "string"}}, ["url"]),
        tool("browser_click", {"target": {"type": "string"}}, ["target"]),
        tool(
            "browser_tabs",
            {"action": {"type": "string"}, "url": {"type": "string"}, "isolatedContext": {"type": "string"}},
        ),
        tool("browser_file_upload", {"paths": {"type": "array", "items": {"type": "string"}}}),
        tool("browser_press_key", {"key": {"type": "string"}}, ["key"]),
        tool("browser_wait_for", {"time": {"type": "number"}}),
        tool("browser_mouse_click_xy", {
            "x": {"type": "number"}, "y": {"type": "number"},
            "button": {"enum": ["left", "right", "middle"]},
            "clickCount": {"type": "number"}, "delay": {"type": "number"},
        }, ["x", "y"]),
        tool("browser_mouse_drag_xy", {
            key: {"type": "number"} for key in ("startX", "startY", "endX", "endY")
        }, ["startX", "startY", "endX", "endY"]),
        tool("browser_mouse_move_xy", {"x": {"type": "number"}, "y": {"type": "number"}}, ["x", "y"]),
        *[tool(name, {"button": {"enum": ["left", "right", "middle"]}})
          for name in ("browser_mouse_down", "browser_mouse_up")],
        tool("browser_evaluate", {"function": {"type": "string"}}),
        tool("browser_run_code_unsafe", {"code": {"type": "string"}}),
    ]


@pytest.fixture
def policy():
    p = ToolPolicy(["http://example.test"])
    p.expose(schemas())
    p.observe('- button "Save" [ref=e1]')
    return p


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/",
        "http://other.test",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://example.test@other.test/",
        "http://user:pass@example.test/",
        "http://example.test:81",
        "http://example.test/api/eval/state",
        "http://example.test/%2572eset",
        "http://example.test/x/../reset",
        "http://example.test/reset;anything",
        "http://example.test/api/dev/reset",
        "http://example.test/eval_state.php",
        "http://example.test/\\reset",
        "http://example.test/\nreset",
        "http://example.test/api/users",
    ],
)
def test_navigation_rejected(policy, url):
    with pytest.raises(PolicyError):
        policy.validate("browser_navigate", {"url": url})


def test_application_requests_allowed_but_private_routes_blocked():
    p = URLPolicy(["http://example.test"], ["/custom-private"])
    p.check("http://example.test/api/users")
    for path in ("/custom-private", "/custom-private/more", "/api/reset", "/api/eval/state"):
        with pytest.raises(PolicyError):
            p.check("http://example.test" + path)


def test_expose_and_dispatch_restrictions(policy):
    exposed = policy.expose(schemas())
    assert "browser_evaluate" not in {t["name"] for t in exposed}
    from mcp.types import Tool

    assert all(Tool.model_validate(tool).input_schema == policy.schemas[tool["name"]] for tool in exposed)
    for name, args in [
        ("browser_run_code_unsafe", {"code": "process.env"}),
        ("browser_evaluate", {"function": "() => document.cookie"}),
        ("unknown", {}),
        ("browser_snapshot", {"filename": "/tmp/secret"}),
        ("browser_click", {"target": "body"}),
        ("browser_click", {"target": "e9"}),
        ("browser_tabs", {"action": "new", "isolatedContext": "unguarded"}),
        ("browser_tabs", {"action": "new", "url": "http://outside.test"}),
        ("browser_press_key", {"key": "Control+Shift+J"}),
        ("browser_wait_for", {"time": 600}),
    ]:
        with pytest.raises(PolicyError):
            policy.validate(name, args)
    assert policy.validate("browser_click", {"target": "e1"}) == {"target": "e1"}


def test_upload_paths_and_symlinks(tmp_path):
    staged = tmp_path / "staged.txt"
    staged.write_text("input")
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    policy = ToolPolicy(["http://example.test"], [staged])
    policy.expose(schemas())
    policy.validate("browser_file_upload", {"paths": [str(staged)]})
    staged.unlink()
    staged.symlink_to(secret)
    for path in (str(secret), str(staged), "relative.txt"):
        with pytest.raises(PolicyError):
            policy.validate("browser_file_upload", {"paths": [path]})


async def test_validation_at_transport_boundary(policy):
    client = AsyncMock()
    browser = MCPBrowser(client, policy, 1)
    with pytest.raises(PolicyError):
        await browser.call("browser_evaluate", {"function": "() => 1"})
    client.call_tool.assert_not_called()


@pytest.mark.parametrize("modifier", ["Control", "Meta"])
@pytest.mark.parametrize("key", ["g", "G", "Shift+g", "c", "C", "v", "V", "x", "X"])
def test_canvas_editing_shortcuts(policy, modifier, key):
    args = {"key": f"{modifier}+{key}"}
    assert policy.validate("browser_press_key", args) == args


@pytest.mark.parametrize("key", ["Control+l", "Meta+q", "Control+Shift+J", "Meta+Alt+i"])
def test_browser_and_os_shortcuts_remain_blocked(policy, key):
    with pytest.raises(PolicyError):
        policy.validate("browser_press_key", {"key": key})


@pytest.mark.parametrize("args", [
    {"x": -1, "y": 1}, {"x": float("nan"), "y": 1},
    {"x": 1, "y": float("inf")}, {"x": True, "y": 1},
    {"x": 1, "y": 1, "clickCount": 1000}, {"x": 1, "y": 1, "clickCount": 1.5},
    {"x": 1, "y": 1, "delay": -1}, {"x": 1, "y": 1, "delay": 1001},
    {"x": 1, "y": 1, "delay": float("nan")}, {"x": 1, "y": 1, "button": "back"},
    {"x": 1, "y": 1, "selector": "body"},
])
async def test_invalid_coordinates_never_reach_browser(policy, args):
    client = AsyncMock()
    with pytest.raises(PolicyError):
        await MCPBrowser(client, policy, 1).call("browser_mouse_click_xy", args)
    client.call_tool.assert_not_called()


def test_coordinate_actions_do_not_require_element_refs(policy):
    assert COORDINATE_TOOLS <= policy.schemas.keys()
    policy.refs.clear()
    for name, args in [
        ("browser_mouse_click_xy", {"x": 42.5, "y": 100, "clickCount": 2}),
        ("browser_mouse_drag_xy", {"startX": 10, "startY": 20, "endX": 100, "endY": 80}),
        ("browser_mouse_move_xy", {"x": 42, "y": 100}),
        ("browser_mouse_down", {}), ("browser_mouse_up", {"button": "left"}),
    ]:
        assert policy.validate(name, args) == args
