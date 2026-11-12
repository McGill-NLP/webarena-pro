"""DAG-based evaluation engine for WebArena-Pro.

Tasks are decomposed into a DAG of eval nodes. Each node has a type that
determines its evaluator. The DAG is executed in topological order; nodes
whose dependencies failed are skipped.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .ui_evidence import UIEvidence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class EvalNode:
    """One check in a task's evaluation DAG.

    An eval node names a registered evaluator via ``type`` and passes that
    evaluator a node-specific ``eval_config``. Nodes can depend on earlier
    nodes by id; if any dependency fails, this node is skipped and receives a
    failed result with a dependency reason.

    ``id`` is the stable identifier used in dependencies, traces, and
    serialized results. ``type`` is the registered evaluator type, for example
    ``backend_state``, ``browser_event``, ``ui_state``, ``answer_match``,
    ``file_downloaded``, ``tiered``, or ``llm_judge``. ``intent`` is optional
    human-readable context for logs and traces. Each node contributes equally
    to partial-credit scoring.
    """

    id: str
    type: str  # "browser_event" | "ui_state" | "backend_state" | "llm_judge"
    eval_config: dict
    depends_on: list[str] = field(default_factory=list)
    intent: str = ""


@dataclass
class EvalDAG:
    """Declarative evaluation graph for one task.

    The DAG is executed in topological order by :class:`DAGEvaluator`.
    ``operator`` controls binary scoring semantics, while ``scoring`` controls
    how per-node results are aggregated into the final score.

    ``operator`` is ``"AND"`` or ``"OR"`` for binary scoring. ``scoring`` is
    ``"binary"`` or ``"partial"``.
    """

    operator: str  # "AND" | "OR"
    nodes: list[EvalNode] = field(default_factory=list)
    scoring: str = "binary"  # "binary" | "partial"


@dataclass
class NodeResult:
    """A single node's eval outcome.

    ``passed`` is the pass/fail bit (used by DAG scoring).
    ``reason`` is a short human-readable string explaining *why* — matched
    predicate, mismatch reason, HTTP status, which check failed, etc. Surfaces
    in logs and in ``summary_info.json['dag_results']``.
    ``inconclusive`` signals that the check could not produce a trustworthy
    verdict (probe errored, missing UI evidence, rule not applicable). The DAG itself
    ignores it (uses ``passed`` only), but the tiered resolver reads it to
    decide whether to escalate to the next strategy / the LLM judge.
    """
    passed: bool
    reason: str = ""
    inconclusive: bool = False

    def __bool__(self) -> bool:
        return self.passed


def _coerce_result(raw) -> NodeResult:
    """Normalise anything an evaluator might return into a NodeResult.

    Evaluators may legacy-return a plain bool. Everything else must be a
    NodeResult (or anything bool-castable).
    """
    if isinstance(raw, NodeResult):
        return raw
    if isinstance(raw, bool):
        return NodeResult(passed=raw, reason="")
    return NodeResult(passed=bool(raw), reason=str(raw))


@dataclass
class EvalContext:
    """Runtime state shared with every node evaluator.

    The context intentionally uses runner-neutral Python data. BrowserGym,
    replay scripts, and other runners can populate the fields they have;
    evaluators that require unavailable evidence should return an inconclusive
    :class:`NodeResult` rather than raising.

    Important fields include ``ui_evidence`` for captured browser facts,
    ``trajectory`` and ``last_action`` for action/history checks,
    ``baselines`` for backend snapshot diffs, and ``downloads`` for file
    download checks.
    """
    ui_evidence: UIEvidence | dict | None = None
    evaluation_id: str | None = None
    evaluation_step: int | None = None
    evaluation_tab_id: str | None = None
    trajectory: list = field(default_factory=list)  # list of StepInfo
    last_step_output: dict | None = None
    task_config: dict = field(default_factory=dict)  # raw_task
    # name -> {"baseline": Snapshot, "current": Snapshot, "diff": SnapshotDiff}
    # If either fetch failed, diff is None and "error" explains the missing evidence.
    # Populated by WebArenaProTask.validate() before running eval nodes.
    baselines: dict[str, dict] = field(default_factory=dict)
    # Browsergym-style chat history (role / message dicts). Populated by
    # validate() from the kwarg of the same name.
    chat_messages: list = field(default_factory=list)
    # Browser downloads captured during task.setup() via page.on("download").
    # Each entry: {"path": str, "suggested_filename": str, "url": str}.
    downloads: list = field(default_factory=list)
    # Last environment action string executed for the current step.
    last_action: str | None = None
    # Calendar date captured when this task execution began. Relative-date
    # predicates must use this stable value rather than the grading time.
    task_start_date: date | None = None
    # Unix milliseconds captured by task setup, before agent actions. Reuse for
    # every validation; standalone/legacy grading must not invent a start time.
    task_start_time_ms: int | None = None
    # Default LLM judge records are JSON-ready and captured per node by the
    # DAG engine, including when the judge is nested inside a tiered evaluator.
    judge_audits: list[dict] = field(default_factory=list)
    # Explicit execution ownership: absent for standalone/replay callers.
    judge_cache: Any = None
    judge_node_id: str | None = None
    judge_dag_config: dict = field(default_factory=dict)
    judge_strategy_trace: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Node evaluator base class + registry
# ---------------------------------------------------------------------------

class NodeEvaluator(ABC):
    """Base protocol for registered DAG node evaluators.

    Implementations receive a node's ``eval_config`` and the shared
    :class:`EvalContext`, then return either a :class:`NodeResult` or a legacy
    bool. Returning ``NodeResult(inconclusive=True)`` tells tiered evaluators
    that the check could not observe enough evidence to make a trustworthy
    decision.
    """

    @abstractmethod
    def evaluate(self, eval_config: dict, context: EvalContext) -> bool:
        """Evaluate one DAG node against the current runtime context."""
        ...


_REGISTRY: dict[str, NodeEvaluator] = {}


def register_node_evaluator(node_type: str, evaluator: NodeEvaluator) -> None:
    _REGISTRY[node_type] = evaluator


def get_node_evaluator(node_type: str) -> NodeEvaluator:
    if node_type not in _REGISTRY:
        raise KeyError(f"No evaluator registered for node type '{node_type}'")
    return _REGISTRY[node_type]


# ---------------------------------------------------------------------------
# Lazy evaluator registration (real implementations live in sibling modules;
# imported lazily to avoid circular imports with dag.py).
# ---------------------------------------------------------------------------

def _register_backend_state() -> None:
    from webarena_pro_core.eval.backend_state import BackendStateEvaluator
    register_node_evaluator("backend_state", BackendStateEvaluator())

_register_backend_state()


def _register_mattermost_calls() -> None:
    from webarena_pro_core.eval.mattermost_calls import MattermostCallsEvaluator
    register_node_evaluator("mattermost_calls", MattermostCallsEvaluator())

_register_mattermost_calls()


def _register_nextcloud_saved_state() -> None:
    from webarena_pro_core.eval.nextcloud_saved_state import NextcloudReactionUIEvaluator, NextcloudSavedStateEvaluator
    register_node_evaluator("nextcloud_saved_state", NextcloudSavedStateEvaluator())
    register_node_evaluator("nextcloud_reaction_ui", NextcloudReactionUIEvaluator())

_register_nextcloud_saved_state()


def _register_answer_match() -> None:
    from webarena_pro_core.eval.answer_match import AnswerMatchEvaluator
    register_node_evaluator("answer_match", AnswerMatchEvaluator())

_register_answer_match()


def _register_file_downloaded() -> None:
    from webarena_pro_core.eval.file_downloaded import FileDownloadedEvaluator
    register_node_evaluator("file_downloaded", FileDownloadedEvaluator())

_register_file_downloaded()


def _register_structural() -> None:
    from webarena_pro_core.eval.structural import (
        BrowserEventEvaluator,
        UIStateEvaluator,
    )
    register_node_evaluator("browser_event", BrowserEventEvaluator())
    register_node_evaluator("ui_state", UIStateEvaluator())

_register_structural()


def _register_llm_judge() -> None:
    from webarena_pro_core.eval.llm_judge import LLMJudgeEvaluator
    register_node_evaluator("llm_judge", LLMJudgeEvaluator())

_register_llm_judge()


def _register_tiered() -> None:
    from webarena_pro_core.eval.tiered import TieredRubricEvaluator
    register_node_evaluator("tiered", TieredRubricEvaluator())

_register_tiered()


# ---------------------------------------------------------------------------
# DAG evaluator
# ---------------------------------------------------------------------------

class DAGEvaluator:
    """Execute and score an :class:`EvalDAG`.

    The evaluator resolves dependencies, invokes registered node evaluators,
    records pass/fail reasons, and computes the final task score. It is
    intentionally independent of agent runners; all runner-specific data must
    already be normalized into :class:`EvalContext`.
    """

    def __init__(self, dag: EvalDAG) -> None:
        """Create an evaluator for a parsed evaluation graph."""
        self.dag = dag

    def evaluate(self, context: EvalContext) -> tuple[float, dict[str, dict]]:
        """Run the DAG and return ``(score, node_results)``.

        ``node_results`` is JSON-friendly and maps each node id to a dict with
        ``passed`` and ``reason`` fields. Exceptions inside individual node
        evaluators are converted into failed node results so one bad check does
        not crash the whole evaluation run.
        """

        order = self._topological_sort()
        context.judge_dag_config = asdict(self.dag)
        if context.judge_cache is not None:
            context.judge_cache.observe(context)
        results: dict[str, NodeResult] = {}
        audits: dict[str, list[dict]] = {}

        for node in order:
            context.judge_node_id = node.id
            context.judge_strategy_trace = []
            # Skip if any dependency failed
            failed_deps = [dep for dep in node.depends_on if not results.get(dep, NodeResult(False)).passed]
            if failed_deps:
                if context.judge_cache is not None:
                    context.judge_cache.discard(node.id)
                reason = f"dependency failed: {', '.join(failed_deps)}"
                results[node.id] = NodeResult(passed=False, reason=reason)
                logger.info("Node '%s' [%s] SKIP — %s", node.id, node.type, reason)
                continue

            evaluator = get_node_evaluator(node.type)
            audit_start = len(context.judge_audits)
            try:
                raw = evaluator.evaluate(node.eval_config, context)
                result = _coerce_result(raw)
            except NotImplementedError as e:
                result = NodeResult(passed=False, reason=f"not implemented: {e}")
                logger.warning("Node '%s' [%s] FAIL — %s", node.id, node.type, result.reason)
            except Exception as e:
                result = NodeResult(passed=False, reason=f"exception: {type(e).__name__}: {e}")
                logger.exception("Node '%s' [%s] evaluation raised", node.id, node.type)
            results[node.id] = result
            if len(context.judge_audits) > audit_start:
                audits[node.id] = context.judge_audits[audit_start:]
            elif context.judge_cache is not None:
                context.judge_cache.discard(node.id)

            status = "PASS" if result.passed else "FAIL"
            logger.info(
                "Node '%s' [%s] %s%s%s",
                node.id,
                node.type,
                status,
                f" — {result.reason}" if result.reason else "",
                f"  (intent: {node.intent[:120]})" if node.intent else "",
            )

        score = self._compute_score({nid: r.passed for nid, r in results.items()})

        serialised = {
            nid: {"passed": r.passed, "reason": r.reason}
            for nid, r in results.items()
        }
        for nid, records in audits.items():
            serialised[nid]["judge_audits"] = records
        return score, serialised

    def _topological_sort(self) -> list[EvalNode]:
        """Kahn's algorithm. Raises ValueError on cycles."""
        nodes_by_id = {n.id: n for n in self.dag.nodes}
        in_degree: dict[str, int] = {n.id: 0 for n in self.dag.nodes}
        dependents: dict[str, list[str]] = {n.id: [] for n in self.dag.nodes}

        for n in self.dag.nodes:
            for dep in n.depends_on:
                if dep not in nodes_by_id:
                    raise ValueError(f"Node '{n.id}' depends on unknown node '{dep}'")
                in_degree[n.id] += 1
                dependents[dep].append(n.id)

        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[EvalNode] = []

        while queue:
            nid = queue.popleft()
            order.append(nodes_by_id[nid])
            for child in dependents[nid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.dag.nodes):
            raise ValueError("Cycle detected in eval DAG")

        return order

    def _compute_score(self, results: dict[str, bool]) -> float:
        if not results:
            return 0.0

        scoring = self.dag.scoring
        operator = self.dag.operator

        if scoring == "binary":
            if operator == "AND":
                return 1.0 if all(results.values()) else 0.0
            else:  # OR
                return 1.0 if any(results.values()) else 0.0

        elif scoring == "partial":
            return sum(results.values()) / len(results)

        else:
            raise ValueError(f"Unknown scoring mode: '{scoring}'")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def parse_eval_dag(eval_config: dict) -> EvalDAG:
    """Parse a raw task ``eval`` dictionary into an :class:`EvalDAG`.

    Missing optional node fields are filled with conservative defaults so older
    task files continue to load.
    """

    raw_nodes = eval_config.get("nodes", [])
    nodes = []
    for raw in raw_nodes:
        nodes.append(EvalNode(
            id=raw["id"],
            type=raw["type"],
            eval_config=raw.get("eval_config", {}),
            depends_on=raw.get("depends_on", []),
            intent=raw.get("intent", ""),
        ))
    return EvalDAG(
        operator=eval_config.get("operator", "AND"),
        nodes=nodes,
        scoring=eval_config.get("scoring", "binary"),
    )
