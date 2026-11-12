"""Core DAG adaptation using captured facts, and score provenance."""

from __future__ import annotations

import asyncio
import time
from datetime import date

from .mcp_client import text_content
from .browser_identity import BrowserIdentityError

from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag
from webarena_pro_core.eval.dag_trace import build_dag_trace
from webarena_pro_core.eval.judge_cache import JudgeVerdictCache
from webarena_pro_core.eval.providers import get_provider
from webarena_pro_core.eval.snapshot import Snapshot, build_snapshot_bundle


class CoreEvaluator:
    def __init__(self, task, start_date: date, start_time_ms: int):
        self.task = task
        self.start_date, self.start_time_ms = start_date, start_time_ms
        self.cache = JudgeVerdictCache()
        self.baselines: dict = {}
        self.specs = (task.evaluation or {}).get("baseline", [])

    def _fetch(self, spec):
        try:
            return get_provider(spec["provider"]).fetch(self.task.website, spec.get("params") or {})
        except Exception as exc:
            # Preserve missing evidence, rather than turning it into an empty
            # baseline that could make preservation checks pass accidentally.
            return Snapshot(error=f"{type(exc).__name__}: snapshot unavailable")

    def capture_baselines(self):
        for spec in self.specs:
            self.baselines[spec["name"]] = self._fetch(spec)
        return {name: snapshot.to_json() for name, snapshot in self.baselines.items()}

    def evaluate(
        self, *, ui_evidence, trajectory, observation, downloads, last_action,
        evaluation_id=None, evaluation_step=None, evaluation_tab_id=None,
    ):
        config = self.task.evaluation
        if not config or not config.get("nodes"):
            raise ValueError("Task has no supported Core DAG evaluation")
        context = EvalContext(
            ui_evidence=ui_evidence,
            evaluation_id=evaluation_id,
            evaluation_step=evaluation_step,
            evaluation_tab_id=evaluation_tab_id,
            task_config=self.task.raw_task or {},
            trajectory=trajectory,
            last_step_output={"obs": observation},
            downloads=downloads,
            last_action=last_action,
            task_start_date=self.start_date,
            task_start_time_ms=self.start_time_ms,
            judge_cache=self.cache,
            baselines={
                spec["name"]: build_snapshot_bundle(
                    self.baselines[spec["name"]],
                    self._fetch(spec),
                )
                for spec in self.specs
            },
        )
        score, details = DAGEvaluator(parse_eval_dag(config)).evaluate(context)
        return {
            "score": score,
            "success": score == 1.0,
            "dag_results": details,
            "dag_trace": build_dag_trace(config, score=score, results=details),
            "judge_audits": context.judge_audits,
            "ui_evidence": ui_evidence,
            "baseline_evidence": {
                name: {key: value.to_json() if hasattr(value, "to_json") else value for key, value in bundle.items()}
                for name, bundle in context.baselines.items()
            },
        }


class ScoreBook:
    def __init__(self, max_steps: int):
        self.max_steps = max_steps
        self.cutoffs = [n for n in (50, 100) if max_steps == -1 or n <= max_steps]
        self.scores: dict[str, dict] = {}
        self.last_grade: tuple[int, dict] | None = None
        self.terminal: dict | None = None

    def record(self, step: int, grade: dict, *, terminal: bool = False):
        self.last_grade = (step, grade)
        entry = {"status": "available", "score": grade["score"], "success": grade["success"], "evaluated_at_step": step}
        if step in self.cutoffs:
            self.scores[str(step)] = dict(entry)
        if terminal:
            self.terminal = dict(entry)
            for cutoff in self.cutoffs:
                if step <= cutoff:
                    self.scores.setdefault(str(cutoff), dict(entry))
            if self.max_steps == -1:
                self.scores["unlimited"] = dict(entry)

    def finish(self, reason: str) -> dict:
        for cutoff in [str(n) for n in self.cutoffs] + (["unlimited"] if self.max_steps == -1 else []):
            self.scores.setdefault(
                cutoff,
                {
                    "status": "unavailable",
                    "score": None,
                    "success": None,
                    "evaluated_at_step": None,
                    "reason": reason,
                    "last_evaluated_at_step": self.last_grade[0] if self.last_grade else None,
                },
            )
        return {
            "max_steps": self.max_steps,
            "step_budget_scores": self.scores,
            "terminal_evaluation": self.terminal,
            "success": self.terminal["success"] if self.terminal else None,
            "score": self.terminal["score"] if self.terminal else None,
        }


async def grade(browser, supervisor, trajectory, last_action, timeout, *, artifacts=None):
    # Identity brackets the snapshot and private capture. Retry only identity
    # races, never a failed evaluator/model call or arbitrary browser failure.
    deadline = time.monotonic() + timeout
    async with asyncio.timeout(timeout):
        for attempt in range(3):
            try:
                identity = await browser.identity()
                snapshot = await browser.call("browser_snapshot", {})
                if snapshot.get("isError"):
                    raise RuntimeError("Browser evidence is unavailable for evaluation")
                if await browser.identity() != identity:
                    raise BrowserIdentityError("Browser document changed during snapshot")
                if artifacts is not None:
                    step = trajectory[-1]["step"] if trajectory else 0
                    artifacts.write(f"evaluation-{step}-input.json", {
                        "snapshot": snapshot, "identity": identity, "attempt": attempt + 1,
                    })
                result = await supervisor.call(
                    "evaluate", timeout=max(0, deadline - time.monotonic()), identity=identity,
                    snapshot=text_content(snapshot), trajectory=trajectory, last_action=last_action,
                )
                return result, snapshot
            except BrowserIdentityError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.025)
