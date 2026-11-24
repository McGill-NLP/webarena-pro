"""Export the native Harbor ATIF v1 trajectory into the shared run format."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

from .model_requests import (
    CoverageGap, InputTokens, ModelRequest, OutputTokens, RunRequests, Usage, atomic_text, normalize_usage,
)

# Harbor removes trial directories when retrying, and directories without trial
# results when resuming. Keep failed attempt snapshots as files at job level.
_SNAPSHOT_PREFIX = ".request-usage-"


def _usage(metrics):
    extra = metrics.get("extra") or {}
    outputs = extra.get("output_tokens_details") or {}
    cache_write = extra.get("cache_creation_input_tokens",
                            extra.get("cache_write_input_tokens", extra.get("cache_write_tokens")))
    reasoning = outputs.get("thinking_tokens", extra.get("reasoning_output_tokens",
                            extra.get("reasoning_tokens", extra.get("thoughts_tokens"))))
    inputs = InputTokens.from_total(metrics.get("prompt_tokens"), metrics.get("cached_tokens"), cache_write=cache_write)
    # ATIF has no standard modality fields. Some producers retain native
    # provider fields in metrics.extra. Apply the same mapping as BrowserGym.
    if extra.get("promptTokensDetails") or extra.get("cacheTokensDetails"):
        details = {**extra, "promptTokenCount": inputs.total, "cachedContentTokenCount": inputs.cached}
        inputs.by_modality = normalize_usage("gemini", {"usageMetadata": details}).input_tokens.by_modality
    elif extra.get("prompt_tokens_details"):
        inputs.by_modality = normalize_usage("chat", {"usage": extra}).input_tokens.by_modality
    return Usage(
        input_tokens=inputs,
        output_tokens=OutputTokens(total=metrics.get("completion_tokens"), reasoning=reasoning,
                                   text=outputs.get("text_tokens"), tool_calls=outputs.get("tool_call_tokens")),
    )


def trial_requests(job, trial, trial_id):
    """Emit individual inferences where the native producer identifies them."""
    result = RunRequests(runner="harbor", run_id=job.name, requests=[])
    episode = f"{trial.name}/{trial_id}"
    visited = set()

    def gap(source, reason, **fields):
        result.coverage_gaps.append(CoverageGap(
            episode_id=episode, source_path=source, reason=reason, **fields,
        ))

    def read(path, agent_root):
        source = path.relative_to(job).as_posix()
        resolved = path.resolve()
        if not resolved.is_relative_to(agent_root) or not resolved.is_relative_to(job):
            gap(source, "external_trajectory")
            return
        if resolved in visited:
            return
        visited.add(resolved)
        try:
            trajectory = json.loads(path.read_bytes())
        except (OSError, ValueError):
            gap(source, "unreadable_trajectory")
            return
        visit(trajectory, path, source, agent_root)

    def visit(document, path, source, agent_root):
        if not isinstance(document, dict) or not str(document.get("schema_version")).startswith("ATIF-v1."):
            gap(source, "unsupported_trajectory")
            return
        steps = document.get("steps")
        if not isinstance(steps, list):
            gap(source, "invalid_trajectory")
            return
        children = document.get("subagent_trajectories") or []
        child_ids = {child.get("trajectory_id") for child in children if isinstance(child, dict)}
        references = []
        for index, step in enumerate(steps):
            try:
                if step.get("is_copied_context"):
                    continue
                step_id = step["step_id"]
                for obs in (step.get("observation") or {}).get("results") or []:
                    for ref in obs.get("subagent_trajectory_ref") or []:
                        if ref.get("trajectory_id") and ref["trajectory_id"] in child_ids:
                            continue
                        if ref.get("trajectory_path"):
                            references.append(ref["trajectory_path"])
                        else:
                            gap(source, "missing_subagent_trajectory", step_id=step_id)
                count = step.get("llm_call_count")
                if step.get("source") != "agent" or count == 0:
                    continue
                if count != 1:
                    gap(source, "unknown_call_count" if count is None else "aggregated_calls",
                        step_id=step_id, llm_call_count=count)
                    continue
                try:
                    usage = _usage(step.get("metrics") or {})
                except (AttributeError, TypeError, ValueError):
                    gap(source, "invalid_metrics", step_id=step_id)
                    usage = Usage()
                result.requests.append(ModelRequest(
                    episode_id=episode, step_id=step_id, call_id=f"{trial_id}/{source}/steps/{index}",
                    attempt=None, status=None, provider=None,
                    model_requested=step.get("model_name") or (document.get("agent") or {}).get("model_name"),
                    usage=usage,
                ))
            except (AttributeError, KeyError, TypeError, ValueError):
                gap(f"{source}/steps/{index}", "invalid_step")
        for index, child in enumerate(children):
            visit(child, path, f"{source}/subagent_trajectories/{index}", agent_root)
        if continuation := document.get("continued_trajectory_ref"):
            references.append(continuation)
        for ref in references:
            if not isinstance(ref, str) or "://" in ref or Path(ref).is_absolute():
                gap(source, "external_trajectory")
            else:
                read(path.parent / ref, agent_root)

    roots = sorted(trial.glob("steps/*/agent/trajectory.json"))
    root = trial / "agent/trajectory.json"
    if root.is_file() or not roots:
        roots.append(root)
    for path in roots:
        read(path, path.parent.resolve())
    return result


def export_job(job):
    """Join retained trial attempts and existing native trajectories. Safe to rerun."""
    job = Path(job).resolve()
    if not job.is_dir():
        raise ValueError(f"No Harbor job directory at {job}")
    run = RunRequests(runner="harbor", run_id=job.name, requests=[])
    snapshots = {path.stem.removeprefix(_SNAPSHOT_PREFIX): path
                 for path in job.glob(f"{_SNAPSHOT_PREFIX}*.json")}
    trials = {path.parent for name in ("config.json", "result.json") for path in job.glob(f"*/{name}")}
    trials.update(path.parents[1] for path in job.glob("*/agent/trajectory.json"))
    trials.update(path.parents[3] for path in job.glob("*/steps/*/agent/trajectory.json"))
    for trial in sorted(trials):
        trial_id = trial.name
        result_path = trial / "result.json"
        if result_path.exists():
            try:
                value = json.loads(result_path.read_bytes())["id"]
                if not isinstance(value, str) or not value:
                    raise ValueError("Invalid trial ID")
                trial_id = value
            except (OSError, ValueError, KeyError, TypeError):
                run.coverage_gaps.append(CoverageGap(episode_id=trial.name, reason="unreadable_trial_id",
                                                     source_path=result_path.relative_to(job).as_posix()))
        if trial_id in snapshots:
            continue
        part = trial_requests(job, trial, trial_id)
        run.requests.extend(part.requests)
        run.coverage_gaps.extend(part.coverage_gaps)
    for path in sorted(snapshots.values()):
        part = RunRequests.model_validate_json(path.read_bytes())
        run.requests.extend(part.requests)
        run.coverage_gaps.extend(part.coverage_gaps)
    run.save(job)
    return run


class HarborRequestUsage:
    """Native Harbor job plugin. Read ATIF on the job host at each trial end."""

    async def on_job_start(self, job):
        self.directory = Path(job.job_dir).resolve()
        job.on_trial_ended(self.on_trial_end)

    async def on_trial_end(self, event):
        # Successful trials remain available in their native format at job end.
        if event.result.exception_info is None:
            return
        trial = self.directory / event.trial_name
        await asyncio.to_thread(self._save_attempt, trial, event.trial_id)

    def _save_attempt(self, trial, trial_id):
        trial_id = str(UUID(str(trial_id)))
        part = trial_requests(self.directory, trial, trial_id)
        with atomic_text(self.directory / f"{_SNAPSHOT_PREFIX}{trial_id}.json") as out:
            out.write(part.model_dump_json())

    async def on_job_end(self, job_result):
        await asyncio.to_thread(export_job, self.directory)
