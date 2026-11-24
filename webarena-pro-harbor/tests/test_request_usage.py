import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from jsonschema import validate
from webarena_pro_core.atif_usage import HarborRequestUsage, export_job

from webarena_pro_harbor.cli import main


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def trajectory(steps, **fields):
    return {"schema_version": "ATIF-v1.7", "agent": {"model_name": "fixture"}, "steps": steps, **fields}


def test_export_existing_job(tmp_path, monkeypatch):
    agent = tmp_path / "trial/agent"
    metrics = {"prompt_tokens": 1000, "completion_tokens": 10, "cached_tokens": 400, "extra": {
        "cache_write_input_tokens": 25,
        "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 1000}],
        "cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 400}],
    }}
    one = {"step_id": 1, "source": "agent", "llm_call_count": 1, "metrics": metrics}
    child = trajectory([one], trajectory_id="child")
    root = trajectory([
        {"step_id": 1, "source": "user"},
        dict(one, step_id=2, observation={"results": [{"subagent_trajectory_ref": [
            {"trajectory_id": "child"}, {"trajectory_path": "leaf.json"},
        ]}]}),
        dict(one, step_id=3, llm_call_count=2),
        {"step_id": 4, "source": "agent", "llm_call_count": 0},
        {"step_id": 5, "source": "agent"},
        dict(one, step_id=6, is_copied_context=True),
    ], subagent_trajectories=[child], continued_trajectory_ref="next.json")
    write_json(agent / "trajectory.json", root)
    write_json(agent / "leaf.json", trajectory([dict(one, metrics={"prompt_tokens": 500})]))
    write_json(agent / "next.json", trajectory([dict(one, metrics={"completion_tokens": 0})],
                                               continued_trajectory_ref="leaf.json"))
    write_json(tmp_path / "trial/result.json", {"id": str(uuid4())})
    write_json(tmp_path / "unavailable/result.json", {"id": str(uuid4())})
    monkeypatch.setattr("sys.argv", ["webarena-pro-harbor", "export-usage", str(tmp_path)])
    main()
    saved = json.loads((tmp_path / "model_requests.json").read_text())
    validate(saved, json.loads((tmp_path / "model_requests.schema.json").read_text()))
    assert saved["runner"] == "harbor" and saved["run_id"] == tmp_path.name
    rows = saved["requests"]
    assert len({r["call_id"] for r in rows}) == len(rows) == 4
    first = rows[0]
    assert first["step_id"] == 2 and first["model_requested"] == "fixture"
    assert first["usage"]["input_tokens"] == {
        "total": 1000, "regular": 600, "cached": 400, "cache_write": 25,
        "by_modality": {"text": {"total": 1000, "regular": 600, "cached": 400}},
    }
    assert [r["usage"]["output_tokens"]["total"] for r in rows] == [10, 10, None, 0]
    assert rows[2]["usage"]["input_tokens"]["cached"] is None
    assert {g["reason"] for g in saved["coverage_gaps"]} == {
        "aggregated_calls", "unknown_call_count", "unreadable_trajectory",
    }


def test_plugin_keeps_replaced_trials_and_resume_is_idempotent(tmp_path):
    trial = tmp_path / "task"
    path = trial / "agent/trajectory.json"
    job = SimpleNamespace(job_dir=tmp_path)
    job.on_trial_ended = lambda callback: setattr(job, "ended", callback)
    plugin = HarborRequestUsage()

    async def run():
        await plugin.on_job_start(job)
        for total in (1, 2):
            trial_id = uuid4()
            write_json(path, trajectory([{"step_id": 1, "source": "agent", "llm_call_count": 1,
                                          "metrics": {"prompt_tokens": total, "cached_tokens": 0}}]))
            write_json(trial / "result.json", {"id": str(trial_id)})
            result = SimpleNamespace(exception_info="failed" if total == 1 else None)
            await job.ended(SimpleNamespace(trial_name=trial.name, trial_id=trial_id, result=result))
        await plugin.on_job_end(None)

    asyncio.run(run())
    first = (tmp_path / "model_requests.json").read_bytes()
    saved = export_job(tmp_path)
    assert (tmp_path / "model_requests.json").read_bytes() == first
    assert not saved.coverage_gaps
    assert sorted(row.usage.input_tokens.regular for row in saved.requests) == [1, 2]
    assert len({row.episode_id for row in saved.requests}) == 2


def test_malformed_metrics_preserve_the_inference(tmp_path):
    path = tmp_path / "task/agent/trajectory.json"
    write_json(path, trajectory([{"step_id": 1, "source": "agent", "llm_call_count": 1,
                                  "metrics": {"prompt_tokens": 1, "cached_tokens": 2}}]))
    saved = export_job(tmp_path)
    assert len(saved.requests) == 1 and saved.requests[0].usage.input_tokens.total is None
    assert [g.reason for g in saved.coverage_gaps] == ["invalid_metrics"]
