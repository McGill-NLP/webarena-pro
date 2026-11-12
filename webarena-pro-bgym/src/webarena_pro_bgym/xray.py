"""WebArena-Pro AgentLab XRay with a per-step DAG evaluator tab."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import gradio as gr

from webarena_pro_core.eval.dag_trace import build_dag_trace, render_dag_trace_markdown


def render_step_dag(step_info: Any, evaluation: dict[str, Any] | None = None) -> str:
    task_info = getattr(step_info, "task_info", None)
    trace = task_info.get("dag_trace") if isinstance(task_info, dict) else None
    if not trace and isinstance(task_info, dict) and isinstance(task_info.get("dag_results"), dict):
        results = task_info["dag_results"]
        if evaluation and isinstance(evaluation.get("nodes"), list):
            trace = build_dag_trace(
                evaluation,
                score=float(task_info.get("score", 0.0)),
                results=results,
            )
        else:
            trace = {
                "score": task_info.get("score", 0.0),
                "operator": "unknown (legacy trace)",
                "scoring": "unknown (legacy trace)",
                "nodes": [
                    {
                        "id": node_id,
                        "type": "—",
                        "depends_on": [],
                        "intent": "",
                        "status": (
                            "PASS"
                            if result.get("passed")
                            else "SKIP"
                            if str(result.get("reason", "")).startswith("dependency failed:")
                            else "FAIL"
                        ),
                        "reason": result.get("reason", ""),
                    }
                    for node_id, result in results.items()
                    if isinstance(result, dict)
                ],
            }
    return "## DAG evaluator\n\n" + render_dag_trace_markdown(trace)


def run(results_dir: Path) -> None:
    from agentlab.analyze import agent_xray

    original_tab = agent_xray.gr.Tab
    original_task_error = agent_xray.update_task_error

    def dag_tab(*args, **kwargs):
        args = list(args)
        if args and args[0] == "Task Error":
            args[0] = "DAG Evaluator"
        elif kwargs.get("label") == "Task Error":
            kwargs["label"] = "DAG Evaluator"
        return original_tab(*args, **kwargs)

    def update_dag_tab():
        state = agent_xray.info
        if state.exp_result is None or not state.exp_result.steps_info:
            return "## DAG evaluator\n\n*No step selected.*"
        step = min(state.step or 0, len(state.exp_result.steps_info) - 1)
        env_args = getattr(state.exp_result.exp_args, "env_args", None)
        task_config = getattr(env_args, "task_config", None)
        evaluation = getattr(task_config, "evaluation", None)
        rendered = render_step_dag(state.exp_result.steps_info[step], evaluation)
        error = original_task_error()
        if error and "No task error" not in str(error):
            rendered += "\n\n---\n\n## Task error\n\n" + str(error)
        return rendered

    def tab_select(evt: gr.SelectData):
        agent_xray.info.active_tab = "Task Error" if evt.value == "DAG Evaluator" else evt.value

    agent_xray.gr.Tab = dag_tab
    agent_xray.update_task_error = update_dag_tab
    agent_xray.tab_select = tab_select
    agent_xray.run_gradio(results_dir)


def main() -> None:
    from agentlab.experiments.exp_utils import RESULTS_DIR

    parser = argparse.ArgumentParser(description="WebArena-Pro AgentLab XRay")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(os.getenv("AGENTLAB_RESULTS_DIR", str(RESULTS_DIR))),
    )
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    if args.port is not None:
        os.environ["AGENTXRAY_APP_PORT"] = str(args.port)
    run(args.results_dir)


if __name__ == "__main__":
    main()
