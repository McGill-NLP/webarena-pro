"""Serializable, viewer-friendly traces for per-step DAG evaluations."""

from __future__ import annotations

from typing import Any, Mapping


def build_dag_trace(
    evaluation: Mapping[str, Any],
    *,
    score: float,
    results: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Combine the static DAG definition with one step's node results."""
    nodes: list[dict[str, Any]] = []
    for node in evaluation.get("nodes") or []:
        if not isinstance(node, Mapping):
            continue
        node_id = str(node.get("id", ""))
        result = results.get(node_id) or {}
        reason = str(result.get("reason", ""))
        passed = bool(result.get("passed", False))
        status = "PASS" if passed else "SKIP" if reason.startswith("dependency failed:") else "FAIL"
        nodes.append(
            {
                "id": node_id,
                "type": str(node.get("type", "")),
                "intent": str(node.get("intent", "")),
                "depends_on": [str(value) for value in node.get("depends_on") or []],
                "status": status,
                "passed": passed,
                "reason": reason,
                "inconclusive": bool(result.get("inconclusive", False)),
            }
        )
    return {
        "operator": str(evaluation.get("operator", "AND")),
        "scoring": str(evaluation.get("scoring", "binary")),
        "score": float(score),
        "nodes": nodes,
    }


def render_dag_trace_markdown(trace: Mapping[str, Any] | None) -> str:
    """Render one DAG trace as compact Markdown for either XRay viewer."""
    if not trace:
        return "*No DAG evaluation was recorded for this step.*"

    score = float(trace.get("score", 0.0))
    operator = _cell(trace.get("operator", "AND"))
    scoring = _cell(trace.get("scoring", "binary"))
    lines = [
        f"**Score:** `{score:g}` &nbsp; **Operator:** `{operator}` &nbsp; **Scoring:** `{scoring}`",
        "",
        "| Status | Node | Type | Depends on | Intent | Decision / evidence |",
        "|---|---|---|---|---|---|",
    ]
    nodes = trace.get("nodes") or []
    if not nodes:
        lines.append("| — | — | — | — | — | No DAG nodes recorded |")
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        status = str(node.get("status", "FAIL"))
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}.get(status, "•")
        dependencies = ", ".join(str(value) for value in node.get("depends_on") or []) or "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{icon} {_cell(status)}",
                    f"`{_cell(node.get('id', ''))}`",
                    f"`{_cell(node.get('type', ''))}`",
                    _cell(dependencies),
                    _cell(node.get("intent", "")) or "—",
                    _cell(node.get("reason", "")) or "—",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
