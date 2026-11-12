"""DAG node evaluator: match the agent's final answer against reference strings.

Reads the agent's action and normalizes it for matching:
- strips XML-like tags such as ``<action>...</action>``
- only ``send_msg_to_user(...)`` is treated as an answer; all other actions
  resolve to an empty string

Then applies ``must_include`` / ``must_include_any`` / ``exact_match`` rules. The helpers mirror
``webarena.evaluation_harness.evaluators.StringEvaluator`` - inlined here so
importing this module does not pull webarena's env-var-gated module tree.
"""

from __future__ import annotations

import ast
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webarena_pro_core.eval.dag import EvalContext

logger = logging.getLogger(__name__)


def _clean_answer(answer: str) -> str:
    answer = (answer or "").strip()
    if len(answer) >= 2 and answer[0] == answer[-1] and answer[0] in ("'", '"'):
        answer = answer[1:-1]
    return answer.lower()


def _exact_match(ref: str, pred: str) -> bool:
    return _clean_answer(pred) == _clean_answer(ref)


def _must_include(ref: str, pred: str, tokenize: bool = False) -> bool:
    clean_ref = _clean_answer(ref)
    clean_pred = _clean_answer(pred)
    if tokenize and len(clean_ref) == 1:
        return clean_ref in clean_pred.split()
    return clean_ref in clean_pred


def _step_field(step: object, field: str):
    if isinstance(step, dict):
        return step.get(field)
    return getattr(step, field, None)


def _strip_xml_like_tags(text: str) -> str:
    return re.sub(r"</?[^>]+>", "", text or "").strip()


def _unwrap_quoted(text: str) -> str:
    s = (text or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _extract_answer_from_action(action: str) -> str:
    raw = _strip_xml_like_tags(action)
    if not raw:
        return ""

    m = re.search(r"send_msg_to_user\s*\((.*)\)\s*$", raw, flags=re.DOTALL)
    if not m:
        return ""

    arg = (m.group(1) or "").strip()
    if not arg:
        return ""

    try:
        parsed = ast.literal_eval(arg)
        if isinstance(parsed, str):
            return parsed.strip()
    except Exception:
        logger.debug(
            "ast.literal_eval failed for action arg %r; falling back to quote-strip",
            arg,
        )

    return _unwrap_quoted(arg)


def _extract_agent_answer(context: "EvalContext") -> str:
    # Best source for current-step answer: the action being validated now.
    if context.last_action:
        return _extract_answer_from_action(context.last_action)

    # Fallback: most recent non-empty step action from trajectory.
    episode_info = (
        context.trajectory or (context.last_step_output or {}).get("episode_info") or []
    )
    for step in reversed(episode_info):
        action = _step_field(step, "action")
        if isinstance(action, str) and action.strip():
            from_action = _extract_answer_from_action(action)
            if from_action:
                return from_action
    return ""


class AnswerMatchEvaluator:
    """Evaluate whether the agent's final answer matches reference text.

    This evaluator is used for tasks where success is represented by the
    agent sending a final answer to the user rather than mutating backend
    state. It extracts the latest ``send_msg_to_user(...)`` action from
    :class:`~webarena_pro_core.eval.dag.EvalContext`, normalizes casing and
    quoting, then applies ``exact_match``, ``must_include``, and
    ``must_include_any`` checks from ``eval_config``.
    """

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult

        answer = _extract_agent_answer(context)
        if not answer:
            return NodeResult(passed=False, reason="no action found to match")

        pred = _clean_answer(answer)
        truncated = (pred[:100] + "...") if len(pred) > 100 else pred

        if "exact_match" in eval_config:
            ref = str(eval_config["exact_match"])
            if not _exact_match(ref=ref, pred=pred):
                return NodeResult(
                    passed=False,
                    reason=f"exact_match failed: expected={ref!r}, got={truncated!r}",
                )

        if "must_include" in eval_config:
            refs = eval_config["must_include"] or []
            if not isinstance(refs, list):
                raise ValueError("answer_match.must_include must be a list")
            tokenize = len(refs) == 1
            missing = [
                str(r)
                for r in refs
                if not _must_include(ref=str(r), pred=pred, tokenize=tokenize)
            ]
            if missing:
                return NodeResult(
                    passed=False,
                    reason=f"must_include missing {missing} in answer={truncated!r}",
                )

        if "must_include_any" in eval_config:
            refs = eval_config["must_include_any"] or []
            if not isinstance(refs, list):
                raise ValueError("answer_match.must_include_any must be a list")
            if not refs:
                raise ValueError("answer_match.must_include_any cannot be empty")
            tokenize = len(refs) == 1
            matched = any(
                _must_include(ref=str(r), pred=pred, tokenize=tokenize) for r in refs
            )
            if not matched:
                return NodeResult(
                    passed=False,
                    reason=f"must_include_any failed: expected one of {refs} in answer={truncated!r}",
                )

        return NodeResult(passed=True, reason=f"matched; answer={truncated!r}")
