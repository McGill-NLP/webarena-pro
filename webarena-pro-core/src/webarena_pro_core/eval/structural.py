"""Structural (Tier-1) DAG node evaluators: ``browser_event`` and ``ui_state``.

These are *heuristic* deterministic checks — they approximate a rubric by
inspecting the agent's trajectory (browser_event) or captured DOM facts (ui_state)
without an LLM. They are cheaper and reproducible, but brittle: a too-strict
selector or an unrecognised action phrasing can produce a false ``FAIL``.

For that reason a tiered resolver is expected to *trust a PASS but escalate a
FAIL* from these nodes (``trust="pass_only"``). When an evaluator genuinely
cannot observe what it needs (no trajectory recorded, no captured UI evidence), it returns
``inconclusive=True`` so the resolver falls through to the next strategy.

Config shapes
-------------
browser_event::

    {"match": {"action_contains": "send_msg_to_user"}}
    {"match": {"action_regex": "fill\\\\(.+poll.+\\\\)"}}
    {"match": {"url_contains": "/settings/user"}}
    {"match": {"url_regex": "apps/calendar"}}
    {"match": {"any": [ {"action_contains": "x"}, {"url_contains": "y"} ]}}

ui_state::

    {"checks": [
        {"method": "element_exists", "selector": "html.dark", "min_count": 1},
        {"method": "text_contains", "selector": "body", "text": "Project Alpha"}
    ]}
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from webarena_pro_core.eval.dag import EvalContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trajectory extraction helpers
# ---------------------------------------------------------------------------

def _step_field(step: Any, field: str) -> Any:
    if isinstance(step, dict):
        return step.get(field)
    return getattr(step, field, None)


def _collect_actions(context: "EvalContext") -> list[str]:
    actions: list[str] = []
    if context.last_action:
        actions.append(str(context.last_action))
    episode = context.trajectory or (
        (context.last_step_output or {}).get("episode_info") or []
    )
    for step in episode:
        action = _step_field(step, "action")
        if isinstance(action, str) and action.strip():
            actions.append(action)
    return actions


def _collect_urls(context: "EvalContext") -> list[str]:
    urls: list[str] = []
    episode = context.trajectory or (
        (context.last_step_output or {}).get("episode_info") or []
    )
    for step in episode:
        obs = _step_field(step, "obs")
        if isinstance(obs, dict):
            if isinstance(obs.get("url"), str):
                urls.append(obs["url"])
            open_urls = obs.get("open_pages_urls")
            if isinstance(open_urls, (list, tuple)):
                urls.extend(u for u in open_urls if isinstance(u, str))
    from webarena_pro_core.eval.ui_evidence import EvidenceUnavailable, require_ui_evidence

    try:
        urls.append(require_ui_evidence(context).url)
    except EvidenceUnavailable:
        # Saved observations can provide a current URL even on legacy traces
        # without DOM evidence. Never reconstruct DOM facts from those traces.
        obs = (context.last_step_output or {}).get("obs") or {}
        if isinstance(obs, dict) and isinstance(obs.get("url"), str):
            urls.append(obs["url"])
    return urls


# ---------------------------------------------------------------------------
# browser_event
# ---------------------------------------------------------------------------

class BrowserEventEvaluator:
    """Look for evidence of an action/navigation in the recorded trajectory."""

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult

        match = eval_config.get("match", {})
        actions = _collect_actions(context)
        urls = _collect_urls(context)

        # Nothing observed at all → we cannot judge; let the resolver escalate.
        if not actions and not urls:
            return NodeResult(
                passed=False,
                reason="no trajectory actions or urls observed",
                inconclusive=True,
            )

        ok, reason = self._match(match, actions, urls)
        return NodeResult(passed=ok, reason=reason)

    def _match(self, match: dict, actions: list[str], urls: list[str]) -> tuple[bool, str]:
        if not match:
            return False, "empty match spec"

        if "any" in match:
            for sub in match["any"]:
                ok, reason = self._match(sub, actions, urls)
                if ok:
                    return True, f"any matched: {reason}"
            return False, "none of 'any' sub-matches found"
        if "all" in match:
            reasons = []
            for sub in match["all"]:
                ok, reason = self._match(sub, actions, urls)
                if not ok:
                    return False, f"all failed: {reason}"
                reasons.append(reason)
            return True, "; ".join(reasons)

        for key, expected in match.items():
            ok, reason = self._match_one(key, expected, actions, urls)
            if not ok:
                return False, reason
        return True, "matched " + ", ".join(match.keys())

    def _match_one(self, key, expected, actions, urls) -> tuple[bool, str]:
        haystack_action = "\n".join(actions)
        haystack_url = "\n".join(urls)
        match key:
            case "action_contains":
                hit = expected in haystack_action
                return hit, f"action_contains {expected!r}: {'found' if hit else 'absent'}"
            case "action_regex":
                hit = re.search(expected, haystack_action) is not None
                return hit, f"action_regex {expected!r}: {'found' if hit else 'absent'}"
            case "url_contains":
                hit = expected in haystack_url
                return hit, f"url_contains {expected!r}: {'found' if hit else 'absent'}"
            case "url_regex":
                hit = re.search(expected, haystack_url) is not None
                return hit, f"url_regex {expected!r}: {'found' if hit else 'absent'}"
            case _:
                return False, f"unknown match key {key!r}"


# ---------------------------------------------------------------------------
# ui_state
# ---------------------------------------------------------------------------

class UIStateEvaluator:
    """Apply task predicates to trusted captured UI facts."""

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult
        from webarena_pro_core.eval.ui_evidence import EvidenceUnavailable, require_ui_evidence

        try:
            evidence = require_ui_evidence(context)
        except EvidenceUnavailable as error:
            return NodeResult(passed=False, reason=str(error), inconclusive=True)

        checks = eval_config.get("checks", [])
        reasons: list[str] = []
        for check in checks:
            try:
                ok, reason = self._run_check(check, evidence)
            except Exception as e:  # a flaky DOM probe is inconclusive, not a fail
                logger.exception("ui_state check errored")
                return NodeResult(
                    passed=False,
                    reason=f"check {check.get('method','?')} errored: {type(e).__name__}: {e}",
                    inconclusive=True,
                )
            reasons.append(f"{check.get('method','?')}={'ok' if ok else 'FAIL'}: {reason}")
            if not ok:
                return NodeResult(passed=False, reason="; ".join(reasons))
        return NodeResult(passed=True, reason="; ".join(reasons) or "no checks")

    def _run_check(self, check: dict, evidence) -> tuple[bool, str]:
        from webarena_pro_core.eval.ui_evidence import probe_for_check

        method = check.get("method", "")
        match method:
            case "element_exists":
                selector = check["selector"]
                min_count = check.get("min_count", 1)
                count = evidence.result(probe_for_check(check)).count
                return count >= min_count, f"{selector!r} count={count} (need >= {min_count})"
            case "text_contains":
                selector = check.get("selector", "body")
                text = check["text"]
                content = evidence.result(probe_for_check(check)).text
                hit = text in content
                return hit, f"{text!r} {'found' if hit else 'absent'} in {selector!r}"
            case _:
                return False, f"unknown ui_state method {method!r}"
