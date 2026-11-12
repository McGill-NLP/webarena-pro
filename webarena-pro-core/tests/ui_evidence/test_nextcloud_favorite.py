"""Exercise task 171's actual Tier 1 selector in Chromium.

Requires ``python -m playwright install chromium``.
The DOM fixture follows Nextcloud 32.0.12's FileEntry.vue, FileEntryPreview.vue,
and BreadCrumbs.vue, plus nextcloud-vue 8.38.0's NcButton exact-active class.
"""

import json
from datetime import date
from html import escape
from pathlib import Path

import pytest
import requests

from webarena_pro_core.eval import llm_judge
from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag


from webarena_pro_core.eval.ui_evidence import build_ui_evidence_plan
from webarena_pro_core.ui_evidence.sync_api import collect_ui_evidence

CONFIG = Path(__file__).parents[2] / "src/webarena_pro_core/config"
TASK = next(
    task for task in json.loads((CONFIG / "nextcloud.raw.json").read_text())
    if task["task_id"] == "171"
)


@pytest.fixture(scope="module")
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        if not Path(runtime.chromium.executable_path).exists():
            pytest.skip("Install Chromium with python -m playwright install chromium")
        with runtime.chromium.launch() as instance:
            yield instance


def file_row(name="strategy.md", favorite=True, loading=False, failed=False, hidden=False):
    classes = "files-list__row" + (" files-list__row--loading" if loading else "")
    style = 'style="display: none"' if hidden else ""
    marker = '<span class="files-list__row-icon-favorite">★</span>' if favorite else ""
    failure = '<span class="files-list__row--failed"></span>' if failed else ""
    return f"""<tr data-cy-files-list-row data-cy-files-list-row-name="{escape(name)}"
        class="{classes}" {style}>
        <td class="files-list__row-name">{failure}{marker}{escape(name)}</td>
    </tr>"""


def file_listing(directory="/marketing", current=True, busy="", **row_options):
    active = "router-link-exact-active" if current else ""
    progress = f'<span class="files-list__{busy}-icon"></span>' if busy else ""
    # An ancestor breadcrumb and another favorited file must not satisfy the check.
    return f"""<main data-cy-files-content>
        <nav data-cy-files-content-breadcrumbs>
            <a href="/apps/files/files/100?dir=/marketing">marketing ancestor</a>
            <a class="{active}" href="/apps/files/files/123?dir={escape(directory)}">current folder</a>
        </nav>
        {progress}
        <table><tbody>{file_row(**row_options)}{file_row(name="other.md")}</tbody></table>
    </main>"""


@pytest.mark.parametrize("options,expected", [
    ({}, True),
    ({"directory": "%2Fmarketing"}, True),
    ({"directory": "/Marketing"}, False),
    ({"directory": "/sales"}, False),
    ({"directory": "/marketing/archive"}, False),
    ({"directory": "/archive/marketing"}, False),
    ({"current": False}, False),
    ({"name": "Strategy.md"}, False),
    ({"name": "strategy.md.bak"}, False),
    ({"favorite": False}, False),
    ({"loading": True}, False),
    ({"failed": True}, False),
    ({"hidden": True}, False),
    ({"busy": "loading"}, False),
    ({"busy": "refresh"}, False),
])
def test_favorite_fallback_requires_current_target_ui(browser, monkeypatch, options, expected):
    def send(self, spec, context):
        if spec.get("method") == "PROPFIND":
            raise requests.ConnectionError("Favorite backend unavailable")
        response = requests.Response()
        response.status_code = 200
        response._content = b"date: 27/10/2026"
        return response

    judged = []

    def judge(rubric, context, model):
        judged.append(rubric)
        return "fail", "Scripted fallback verdict"

    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    with browser.new_page() as page:
        page.set_content(file_listing(**options))
        score, results = DAGEvaluator(parse_eval_dag(TASK["eval"])).evaluate(EvalContext(
            ui_evidence=collect_ui_evidence(page, build_ui_evidence_plan(TASK["eval"])), task_config=TASK, task_start_date=date(2026, 10, 27),
            last_action="click('favorite')",
        ))

    assert score == (1 if expected else .75)
    assert results["r4"]["passed"] is expected
    assert "T0:backend_state=INCONCLUSIVE" in results["r4"]["reason"]
    if expected:
        assert "decided_by=T1:ui_state" in results["r4"]["reason"]
        assert not judged
    else:
        assert "decided_by=T2:llm_judge" in results["r4"]["reason"]
        assert "T1:ui_state=FAIL" in results["r4"]["reason"]
        assert judged == ["strategy.md is added to favorites."]


def test_removed_favorite_cannot_pass_from_earlier_action(browser):
    from webarena_pro_core.eval.structural import UIStateEvaluator

    config = TASK["eval"]["nodes"][3]["eval_config"]["strategies"][1]["config"]
    with browser.new_page() as page:
        page.set_content(file_listing())
        context = EvalContext(ui_evidence=collect_ui_evidence(page, build_ui_evidence_plan(TASK["eval"])), last_action="click('favorite')")
        assert UIStateEvaluator().evaluate(config, context).passed
        page.locator('[data-cy-files-list-row-name="strategy.md"] .files-list__row-icon-favorite').evaluate(
            "element => element.remove()"
        )
        context.ui_evidence = collect_ui_evidence(page, build_ui_evidence_plan(TASK["eval"]))
        assert not UIStateEvaluator().evaluate(config, context).passed


@pytest.mark.parametrize("status,favorite,expected_tier,expected_pass", [
    (207, 0, "T0:backend_state", False),
    (404, 1, "T0:backend_state", False),
    (500, 1, "T1:ui_state", True),
])
def test_favorite_ui_cannot_override_definitive_backend_failure(
    browser, monkeypatch, status, favorite, expected_tier, expected_pass
):
    def send(self, spec, context):
        response = requests.Response()
        response.status_code = status if spec.get("method") == "PROPFIND" else 200
        response._content = (
            f"<oc:favorite>{favorite}</oc:favorite>"
            if spec.get("method") == "PROPFIND" else "date: 27/10/2026"
        ).encode()
        return response

    def judge(*args):
        pytest.fail("The backend or UI should decide this rubric")

    monkeypatch.setattr(BackendStateEvaluator, "_send", send)
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    with browser.new_page() as page:
        page.set_content(file_listing())
        _, results = DAGEvaluator(parse_eval_dag(TASK["eval"])).evaluate(EvalContext(
            ui_evidence=collect_ui_evidence(page, build_ui_evidence_plan(TASK["eval"])), task_config=TASK, task_start_date=date(2026, 10, 27),
        ))

    assert results["r4"]["passed"] is expected_pass
    assert f"decided_by={expected_tier}" in results["r4"]["reason"]
