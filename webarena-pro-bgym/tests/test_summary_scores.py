"""Historical checkpoint credit must not become an ungraded episode success."""

import gzip
import json
import pickle
from types import SimpleNamespace

import pandas as pd
import pytest

from webarena_pro_bgym import dashboard, run_eval_cli
from webarena_pro_bgym.study import WebArenaProExpArgs, WebArenaProStepInfo, WebArenaProStudy
from webarena_pro_bgym.submissions import _summary_metadata
from webarena_pro_bgym.utils import normalized_task_score


def test_unknown_native_cost_does_not_become_zero(tmp_path):
    episode = [WebArenaProStepInfo(step=0, agent_info={"stats": {
        "cost": float("nan"), "native_cost_unavailable": 1,
    }}), WebArenaProStepInfo(step=1, terminated=True)]
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = SimpleNamespace(max_steps=30)
    exp.save_summary_info(episode, tmp_path, None, None)
    summary = json.loads((tmp_path / "summary_info.json").read_text())
    assert summary["cost_available"] is False
    assert summary["stats.cum_cost"] is None
    assert summary["stats.max_cost"] is None


@pytest.fixture
def ungraded_episode(tmp_path):
    exp_dir = tmp_path / "GenericAgent_on_webarena-pro-bgym.100_0"
    exp_dir.mkdir()
    episode = [
        WebArenaProStepInfo(step=0),
        WebArenaProStepInfo(step=50, task_info={
            "dag_evaluated": True, "score": 1.0, "evaluation_trigger": "budget_checkpoint",
        }),
        # GenericAgent can return None without exhausting its budget, e.g.
        # after parsing retries. There is no exception or terminal DAG grade.
        WebArenaProStepInfo(step=60, truncated=True, task_info={}),
    ]
    exp = WebArenaProExpArgs.__new__(WebArenaProExpArgs)
    exp.env_args = SimpleNamespace(max_steps=100)
    exp.save_summary_info(episode, exp_dir, None, None)
    path = exp_dir / "summary_info.json"
    summary = json.loads(path.read_text())
    assert summary["err_msg"] is None
    assert summary["cum_reward"] == 1.0
    assert summary["score_provenance"]["status"] == "last_evaluation"
    assert summary["step_budget_scores"]["50"]["score"] == 1.0
    assert summary["step_budget_scores"]["100"]["score"] is None
    return path, summary


@pytest.mark.parametrize("parallel", [False, True])
def test_cli_does_not_count_ungraded_checkpoint_credit_as_success(ungraded_episode, capsys, parallel):
    path, _ = ungraded_episode
    if parallel:
        assert run_eval_cli.aggregate_parallel_results("fixture", root_dir=path.parent.parent) == (0, 1)
    else:
        run_eval_cli.print_eval_results(path.parent.parent, "fixture")
    output = capsys.readouterr().out
    assert "UNGRADED (last evaluated score=1.00)" in output
    assert "Total: 0/1 passed, avg_reward=0.000" in output


def test_dashboard_does_not_count_ungraded_checkpoint_credit_as_success(ungraded_episode, monkeypatch):
    path, summary = ungraded_episode
    root = path.parent.parent
    args = SimpleNamespace(env_args=SimpleNamespace(
        task_name="webarena-pro-bgym.100", task_config=SimpleNamespace(task_id=100),
    ))
    with gzip.open(root / "study.pkl.gz", "wb") as saved:
        pickle.dump(SimpleNamespace(name="fixture", exp_args_list=[args]), saved)
    (path.parent / "exp_args.pkl").write_bytes(pickle.dumps(args))
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])
    snapshot = dashboard.build_run_snapshot(root)
    assert snapshot["study"]["passed_tasks"] == 0
    assert snapshot["study"]["avg_reward"] == 0.0
    assert snapshot["tasks"][0]["status"] == "failed"
    assert json.loads(path.read_text()) == summary


def test_study_aggregate_excludes_ungraded_score_but_keeps_raw_evidence(ungraded_episode, monkeypatch):
    path, summary = ungraded_episode
    raw = pd.DataFrame([summary], index=pd.MultiIndex.from_tuples(
        [("webarena-pro-bgym.100", "fixture")], names=["env.task_name", "agent.agent_name"],
    ))
    monkeypatch.setattr("webarena_pro_bgym.study.inspect_results.load_result_df", lambda paths: raw)
    monkeypatch.setattr("webarena_pro_bgym.study.inspect_results.error_report", lambda *a, **kw: "")
    study = WebArenaProStudy.__new__(WebArenaProStudy)
    study.dir = path.parent.parent
    results, aggregate, _ = study.get_results(also_save=False)
    assert results["cum_reward"].iloc[0] == 1.0
    assert aggregate["avg_reward"].iloc[0] == 0.0
    assert aggregate["n_err"].iloc[0] == 0
    assert json.loads(path.read_text()) == summary


def test_other_score_consumers_preserve_evidence_without_passing_ungraded_episode(ungraded_episode):
    path, summary = ungraded_episode
    assert _summary_metadata(path) == (1.0, "failed")
    assert normalized_task_score(summary) == 0.0
    # Existing summaries and actual completed grades retain their meaning.
    assert normalized_task_score({"cum_reward": 1.0}) == 1.0
    assert normalized_task_score({"cum_reward": 1.0, "score_provenance": {"status": "terminal"}}) == 1.0
