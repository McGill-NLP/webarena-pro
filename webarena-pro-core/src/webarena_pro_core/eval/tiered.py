"""Tiered rubric resolver — the deterministic-first / LLM-fallback policy.

A ``tiered`` DAG node grades ONE rubric by trying *strategies* in their
configured list order, normally cheapest and most trustworthy first. Numeric
tier labels do not reorder strategies; the trust policy controls escalation.

The key correctness rule (see doc/rfcs and the design proposal): **do NOT
escalate to the LLM merely because a deterministic check returned FAIL.** A
confident deterministic FAIL (e.g. "the saved file does not exist on the
backend") is authoritative and must stand — otherwise the LLM dependency we are
trying to remove comes right back, and a hallucinated PASS could override hard
evidence. Each strategy resolves to one of three values. INCONCLUSIVE and
untrusted failures escalate unless the strategy is terminal.

Strategy verdict mapping (from the sub-evaluator's NodeResult):
    inconclusive=True            -> INCONCLUSIVE  (escalate unless terminal)
    passed=True                  -> PASS
    passed=False                 -> FAIL

Per-strategy ``trust`` policy:
    "both"       Tier 0 ground truth (backend_state / answer_match /
                 file_downloaded): PASS and FAIL are both authoritative; stop.
    "pass_only"  Tier 1 structural heuristic (ui_state / browser_event): trust
                 a PASS, but a FAIL escalates (brittle selectors get a second
                 look).
    "terminal"   Tier 2 (llm_judge): whatever it says is final.

If ``trust`` is omitted it defaults by node type. After all strategies, if
nothing resolved authoritatively, the last concrete verdict is used (an
exhausted INCONCLUSIVE counts as FAIL — conservative).

Config shape::

    {
      "rubric": "A file named 'Client Meeting Update' exists",
      "strategies": [
        {"tier": 0, "type": "backend_state", "config": {...}},
        {"tier": 1, "type": "ui_state",      "config": {...}, "trust": "pass_only"},
        {"tier": 2, "type": "llm_judge",     "config": {"rubric": "..."}}
      ]
    }

The returned ``NodeResult.reason`` records which tier decided and whether the
node escalated, so ``dag_results`` stays auditable.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webarena_pro_core.eval.dag import EvalContext

logger = logging.getLogger(__name__)

PASS = "PASS"
FAIL = "FAIL"
INCONCLUSIVE = "INCONCLUSIVE"

# Default trust by strategy type when not explicitly set.
_DEFAULT_TRUST = {
    "backend_state": "both",
    "answer_match": "both",
    "file_downloaded": "both",
    "ui_state": "pass_only",
    "browser_event": "pass_only",
    "llm_judge": "terminal",
}


class TieredRubricEvaluator:
    """Resolve one rubric using deterministic checks before LLM fallback.

    A tiered node contains strategies such as ``backend_state``, ``ui_state``,
    and ``llm_judge``. The evaluator runs them in their configured list order,
    usually cheapest-first, and stops according to the strategy's trust policy.
    This keeps ground-truth failures from being overwritten by a later LLM
    guess while still allowing brittle structural checks to escalate.
    """

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult, get_node_evaluator

        rubric = eval_config.get("rubric", "")
        strategies = eval_config.get("strategies", [])
        if not strategies:
            return NodeResult(passed=False, reason="tiered node has no strategies")

        trail: list[str] = []
        last_concrete: tuple[str, str] | None = None  # (verdict, reason)

        for strat in strategies:
            stype = strat.get("type")
            tier = strat.get("tier", "?")
            trust = strat.get("trust") or _DEFAULT_TRUST.get(stype, "pass_only")
            trust_source = "explicit" if strat.get("trust") else "default"
            trust_detail = f" [trust={trust}, source={trust_source}]"
            sub_config = strat.get("config", {})

            try:
                evaluator = get_node_evaluator(stype)
            except KeyError:
                trail.append(f"T{tier}:{stype}=UNKNOWN_TYPE{trust_detail}")
                continue

            try:
                # Current probe outcomes are part of the fallback conditions.
                context.judge_strategy_trace = list(trail)
                raw = evaluator.evaluate(sub_config, context)
            except Exception as e:  # a crashing strategy is inconclusive
                logger.exception("tiered strategy %s errored", stype)
                trail.append(f"T{tier}:{stype}=ERR({type(e).__name__})->escalate{trust_detail}")
                continue

            verdict = self._classify(raw)
            reason = getattr(raw, "reason", "")
            # Preserve the reason for escalation even when a later judge
            # supplies the final verdict (including pass-only HTTP failures).
            escalates = verdict == INCONCLUSIVE or (verdict == FAIL and trust == "pass_only")
            detail = f"({reason})" if escalates and reason else ""
            trail.append(f"T{tier}:{stype}={verdict}{detail}{trust_detail}")

            if verdict != INCONCLUSIVE:
                last_concrete = (verdict, reason)

            # Decide based on verdict + trust policy.
            if trust == "terminal":
                return self._finish(verdict, tier, stype, trail, reason, escalated=len(trail) > 1)

            if verdict == PASS:
                # PASS is trusted under both "both" and "pass_only".
                return self._finish(PASS, tier, stype, trail, reason, escalated=len(trail) > 1)

            if verdict == FAIL and trust == "both":
                # Authoritative ground-truth FAIL — do NOT escalate.
                return self._finish(FAIL, tier, stype, trail, reason, escalated=len(trail) > 1)

            # Otherwise (FAIL under pass_only, or INCONCLUSIVE): escalate.
            continue

        # Strategies exhausted with no authoritative resolution.
        if last_concrete is not None:
            verdict, reason = last_concrete
            return self._finish(
                verdict, "exhausted", "fallback", trail, reason, escalated=True
            )
        # Everything was inconclusive → conservative FAIL.
        return self._finish(
            FAIL, "exhausted", "none", trail, "all strategies inconclusive", escalated=True
        )

    @staticmethod
    def _classify(raw) -> str:
        if getattr(raw, "inconclusive", False):
            return INCONCLUSIVE
        passed = raw.passed if hasattr(raw, "passed") else bool(raw)
        return PASS if passed else FAIL

    @staticmethod
    def _finish(verdict, tier, stype, trail, reason, escalated):
        from webarena_pro_core.eval.dag import NodeResult

        decided_by = f"T{tier}:{stype}"
        flag = " [escalated]" if escalated else ""
        msg = f"decided_by={decided_by}{flag} | {reason} | trail={' -> '.join(trail)}"
        return NodeResult(passed=(verdict == PASS), reason=msg)
