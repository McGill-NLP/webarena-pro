from browsergym.core.action.highlevel import HighLevelActionSet
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from webarena_pro_bgym.benchmark.benchmark import _DEFAULT_WEBARENA_PRO_ACTION_SET_ARGS

import webarena_pro_bgym  # noqa: F401  # import triggers action-space extension


def test_done_action_is_available_in_webarena_subset():
    action_set = HighLevelActionSet(subsets=["webarena"], multiaction=False, strict=False)

    assert "done" in action_set.action_set


def test_done_action_is_available_in_bid_subset():
    action_set = HighLevelActionSet(subsets=["bid"], multiaction=False, strict=False)

    assert "done" in action_set.action_set


@pytest.mark.parametrize("scale", [1, 2])
def test_default_actions_draw_continuous_stroke_and_closed_path(scale):
    actions = _DEFAULT_WEBARENA_PRO_ACTION_SET_ARGS.make_action_set()
    for name in ("click", "fill", "mouse_down", "mouse_move", "mouse_up",
                 "mouse_click", "mouse_drag_and_drop"):
        assert name in actions.action_set
        assert name in actions.describe()
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Chromium is not installed; run playwright install chromium")
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 400, "height": 300})
            playwright.selectors.set_test_id_attribute("bid")
            page._bgym_scale_factor = scale
            page.set_content("""
                <style>body{margin:0}svg{display:block;width:400px;height:250px}</style>
                <button bid="1" onclick="mode='path'">Path</button>
                <svg id="canvas"></svg>
                <script>
                  window.mode='pencil'; window.stroke=[]; window.vertices=[];
                  window.released=false; window.pathClosed=false;
                  let pressed=false;
                  canvas.onmousedown=e=>{pressed=true; if(mode==='pencil')stroke.push([e.clientX,e.clientY]);};
                  canvas.onmousemove=e=>{if(pressed&&mode==='pencil')stroke.push([e.clientX,e.clientY]);};
                  canvas.onmouseup=e=>{pressed=false; released=true;};
                  canvas.onclick=e=>{if(mode==='path'){
                    const point=[e.clientX,e.clientY];
                    pathClosed=vertices.length>=3&&JSON.stringify(point)===JSON.stringify(vertices[0]);
                    vertices.push(point);
                  }};
                </script>
            """)

            def execute(action):
                exec(actions.to_python_code(action), {"page": page})

            for name, x, y in (("mouse_down", 40, 60), ("mouse_move", 90, 80),
                               ("mouse_move", 120, 140), ("mouse_up", 160, 170)):
                execute(f"{name}({x * scale}, {y * scale})")
            assert page.evaluate("stroke") == [[40, 60], [90, 80], [120, 140], [160, 170]]
            assert page.evaluate("released") is True
            execute("click('1')")
            for x, y in ((40, 60), (90, 80), (120, 140), (40, 60)):
                execute(f"mouse_click({x * scale}, {y * scale})")
            assert page.evaluate("vertices") == [[40, 60], [90, 80], [120, 140], [40, 60]]
            assert page.evaluate("pathClosed") is True
            page.evaluate("mode='pencil';stroke=[];released=false")
            execute(f"mouse_drag_and_drop({40 * scale}, {60 * scale}, {120 * scale}, {140 * scale})")
            assert page.evaluate("stroke") == [[40, 60], [120, 140]]
            assert page.evaluate("released") is True
        finally:
            browser.close()
