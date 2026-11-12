import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from webarena_pro_bgym import run_eval_cli
from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_core.eval import providers
from webarena_pro_core.eval.snapshot import Snapshot
from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig


@pytest.fixture
def config():
    return WebArenaProTaskConfig(
        task_id="402",
        intent="Update files",
        sites=("nextcloud",),
        start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        container_name="snapshot-test",
        evaluation={
            "baseline": [{"name": "files", "provider": "test_files"}],
            "operator": "AND",
            "nodes": [
                {
                    "id": "files",
                    "type": "backend_state",
                    "eval_config": {"baseline_ref": "files", "checks": []},
                }
            ],
        },
    )


@pytest.mark.parametrize(
    "baseline_failed,current_failed,check",
    [
        (True, False, "snapshot_diff_added"),
        (False, True, "snapshot_diff_removed"),
        (True, True, "snapshot_diff_empty"),
    ],
)
def test_fetch_failures_do_not_credit_task(
    monkeypatch, config, baseline_failed, current_failed, check
):
    provider = Mock()
    provider.fetch.side_effect = [
        ConnectionError("baseline offline")
        if baseline_failed
        else Snapshot(entries={"file.txt": {}}),
        ConnectionError("current offline")
        if current_failed
        else Snapshot(entries={"file.txt": {}}),
    ]
    monkeypatch.setitem(providers._REGISTRY, "test_files", provider)
    config.evaluation["nodes"][0]["eval_config"]["checks"] = [{"type": check}]
    task = WebArenaProTask(seed=0, config=config)

    task._fetch_baselines()
    score, done, _, info = task.validate(
        SimpleNamespace(), [], last_action="done()"
    )

    assert score == 0.0
    assert done is True
    result = info["dag_results"]["files"]
    assert result["passed"] is False
    assert "snapshot unavailable" in result["reason"]
    assert "ConnectionError" in result["reason"]


@pytest.mark.parametrize("baseline_failed", [False, True])
def test_current_retry_never_replaces_original_baseline(
    monkeypatch, config, baseline_failed
):
    provider = Mock()
    provider.fetch.side_effect = [
        ConnectionError("baseline offline") if baseline_failed else Snapshot(),
        ConnectionError("current offline"),
        Snapshot(entries={"new.txt": {}}),
    ]
    monkeypatch.setitem(providers._REGISTRY, "test_files", provider)
    task = WebArenaProTask(seed=0, config=config)
    task._fetch_baselines()
    baseline = task.baselines["files"]

    assert task._compute_current_diffs()["files"]["diff"] is None
    recovered = task._compute_current_diffs()["files"]

    assert recovered["baseline"] is baseline
    if baseline_failed:
        assert recovered["diff"] is None
        assert "baseline offline" in recovered["error"]
    else:
        assert recovered["diff"].added == ["new.txt"]


@pytest.mark.parametrize("fail_call", [1, 2])
def test_dry_run_does_not_report_unchanged_state_on_fetch_failure(
    monkeypatch, config, caplog, fail_call
):
    provider = Mock()
    responses = [Snapshot(), Snapshot()]
    responses[fail_call - 1] = ConnectionError("offline")
    provider.fetch.side_effect = responses
    monkeypatch.setitem(providers._REGISTRY, "test_files", provider)
    config.evaluation["nodes"][0]["eval_config"]["checks"] = [
        {"type": "snapshot_diff_empty"}
    ]
    monkeypatch.setattr(
        run_eval_cli,
        "WebArenaProBenchmark",
        lambda **kwargs: SimpleNamespace(
            env_args_list=[SimpleNamespace(task_config=config)]
        ),
    )

    with caplog.at_level(logging.INFO):
        run_eval_cli.dry_run_eval("nextcloud", [402])

    assert "[FAIL] files" in caplog.text
    assert "snapshot unavailable" in caplog.text
    assert "Score: 0.00" in caplog.text
