from __future__ import annotations

import json
import os
from types import SimpleNamespace
import pytest

import webarena_pro_bgym.run_tiered_cli as run_tiered

from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark
from webarena_pro_bgym.run_tiered_cli import tiered_task_ids_by_site
from webarena_pro_core.splits import task_ids_for_split


@pytest.mark.parametrize("split,count", [(None, 300), ("dev", 100), ("test", 300)])
def test_list_split_selects_exact_partition(split, count, capsys):
    args = ["--list"] if split is None else ["--split", split, "--list"]
    assert run_tiered.main(args) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == f"total: {count}"
    ids = {tid for line in lines[:-1] for tid in line.split(": ")[1].split(",")}
    assert ids == task_ids_for_split(split or "test")


def test_split_intersects_site_and_task_filters(capsys):
    by_site = tiered_task_ids_by_site(split="dev")
    dev = task_ids_for_split("dev")
    site, selected = next((site, sorted(set(ids) & dev)[0])
                          for site, ids in by_site.items() if set(ids) & dev)
    assert run_tiered.main(["--split", "dev", "--site", site, "--task", selected, "--list"]) == 0
    assert capsys.readouterr().out == f"{site}: {selected}\ntotal: 1\n"
    assert run_tiered.main(["--split", "test", "--task", selected, "--list"]) == 1


def test_dev_only_task_is_discovered_and_loaded_from_its_own_dag(capsys):
    assert run_tiered.main(['--split', 'dev', '--site', 'mattermost', '--task', '421', '--list']) == 0
    assert capsys.readouterr().out == 'mattermost: 421\ntotal: 1\n'
    assert run_tiered.main(['--task', '421', '--list']) == 1
    assert run_tiered.main(['--split', 'test', '--task', '421', '--list']) == 1
    by_site = tiered_task_ids_by_site(split='dev')
    _, tasks = run_tiered._build_tiered_benchmark(
        task_ids_by_site=by_site, selected_sites=list(by_site), max_steps=30, split='dev',
    )
    assert len(tasks) == 100
    task = next(t.task_config for t in tasks if t.task_config.task_id == '421')
    assert task.website == 'mattermost'
    assert task.evaluation['nodes'][0]['eval_config']['rubric'] == 'Correct if the answer is 203.0.113.0/24.'


def test_dev_only_task_dry_run_keeps_split_and_config_directory(monkeypatch):
    calls = []
    monkeypatch.setattr(run_tiered, '_required_api_key_env_var', lambda model: None)
    monkeypatch.setattr(run_tiered, 'ensure_sites_ready', lambda *args: True)
    monkeypatch.setattr(run_tiered, 'dry_run_eval', lambda *args, **kwargs: calls.append((args, kwargs)))
    assert run_tiered.main(['--split', 'dev', '--task', '421', '--dry-run']) == 0
    assert calls == [(('mattermost', [421]), {'split': 'dev', 'config_dir': run_tiered.CONFIG_DIR})]


@pytest.mark.parametrize("steps", [None, 50, 100, "unlimited", -1])
def test_parallel_dev_worker_can_load_a_task_absent_from_site_configs(monkeypatch, tmp_path, steps):
    commands = []
    monkeypatch.setattr(run_tiered, '_required_api_key_env_var', lambda model: None)
    monkeypatch.setattr(run_tiered, 'ensure_docker_running', lambda: True)
    monkeypatch.setattr(run_tiered, '_make_parallel_study', lambda **kwargs: SimpleNamespace(
        dir=tmp_path, get_results=lambda **kwargs: None,
    ))
    monkeypatch.setattr(run_tiered, 'aggregate_parallel_results', lambda **kwargs: None)
    def run_queue(**kwargs):
        assert kwargs['task_sites'] == {421: ['mattermost']}
        assert kwargs['worker_count'] == 2
        commands.append(kwargs['command'])
        return 0
    monkeypatch.setattr(run_tiered, 'run_queue_workers', run_queue)
    extra = [] if steps is None else ['--max-steps', str(steps)]
    assert run_tiered.main(['--split', 'dev', '--task', '421', '--n-jobs', '2', *extra]) == 0
    assert len(commands) == 1
    worker = run_tiered._parse_args(commands[0][2:])
    assert worker.max_steps == (50 if steps is None else -1 if steps == "unlimited" else steps)
    assert worker.split == 'dev' and worker.config_dir == run_tiered.CONFIG_DIR.resolve()
    by_site = tiered_task_ids_by_site(worker.config_dir, split=worker.split)
    by_site = run_tiered._filter_task_ids_by_site(by_site, run_tiered._parse_task_filter(worker.task))
    _, tasks = run_tiered._build_tiered_benchmark(
        task_ids_by_site=by_site, selected_sites=worker.site, max_steps=worker.max_steps,
        split=worker.split, config_dir=worker.config_dir,
    )
    assert [t.task_config.task_id for t in tasks] == ['421']
    assert tasks[0].max_steps == worker.max_steps
    assert tasks[0].task_config.evaluation['nodes']


def test_tiered_task_ids_by_site_maps_original_id_and_intent(tmp_path):
    (tmp_path / "demo.raw.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "001",
                    "original_task_id": "old-1",
                    "intent": "Task matched by original id",
                    "website": "demo",
                },
                {
                    "task_id": "002",
                    "intent": "Task matched by copied intent",
                    "website": "demo",
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "demo.tiered.json").write_text(
        json.dumps(
            {
                "_README": "ignored metadata",
                "old-1": {"intent": "Task matched by original id", "nodes": []},
                "old-2": {"intent": "Task matched by copied intent", "nodes": []},
            }
        ),
        encoding="utf-8",
    )

    assert tiered_task_ids_by_site(tmp_path) == {"demo": ["001", "002"]}


def test_packaged_tiered_task_counts():
    task_ids = tiered_task_ids_by_site()

    assert {site: len(ids) for site, ids in task_ids.items()} == {
        "acidwave": 35,
        "erp-next": 16,
        "firefly": 15,
        "flight-search": 17,
        "immich": 14,
        "jobportal": 5,
        "mattermost": 23,
        "metabase": 11,
        "minerva-lite": 12,
        "mydrive": 14,
        "nextcloud": 17,
        "notion": 16,
        "password-manager": 6,
        "penpot": 11,
        "peppermint": 15,
        "pipedrive": 5,
        "thunderbird": 12,
        "travelmap": 9,
        "x-lite": 9,
        "yt-lite": 38
    }
    assert sum(len(ids) for ids in task_ids.values()) == 300


def test_tiered_discovery_uses_embedded_dags_and_primary_sites(tmp_path):
    tasks = [
        {"task_id": "001", "sites": ["nextcloud", "mattermost"], "eval": {"nodes": []}},
        {"task_id": "002", "website": "mattermost", "evaluation": {"nodes": []}},
        {"task_id": "003", "sites": ["nextcloud"], "eval": {"eval_types": ["string_match"]}},
        {"task_id": "004", "sites": ["nextcloud"], "eval": None},
    ]
    (tmp_path / "custom.raw.json").write_text(json.dumps(tasks))

    assert tiered_task_ids_by_site(tmp_path) == {"nextcloud": ["001"], "mattermost": ["002"]}


def test_packaged_tiered_tasks_load_as_dag_evaluations():
    task_ids_by_site = tiered_task_ids_by_site()
    tiered_pairs = {
        (site, task_id)
        for site, task_ids in task_ids_by_site.items()
        for task_id in task_ids
    }
    benchmark = WebArenaProBenchmark(sites=sorted(task_ids_by_site))

    matched = []
    missing_dag = []
    legacy_rubric = []
    for env_args in benchmark.env_args_list:
        task_config = env_args.task_config
        pair = (task_config.website, str(task_config.task_id))
        if pair not in tiered_pairs:
            continue

        matched.append(pair)
        evaluation = task_config.evaluation or {}
        if "nodes" not in evaluation:
            missing_dag.append(pair)
        if "rubric_verifier" in (evaluation.get("eval_types") or []):
            legacy_rubric.append(pair)

    assert len(matched) == 300
    assert missing_dag == []
    assert legacy_rubric == []


@pytest.mark.parametrize("flag", ["--with-rubric-verifier", "--no-rubric-verifier"])
def test_tiered_rejects_removed_rubric_flags(flag):
    with pytest.raises(SystemExit) as error:
        run_tiered.main(["--list", flag])
    assert error.value.code == 2


def test_resume_rejects_split_override():
    with pytest.raises(SystemExit) as error:
        run_tiered.main(["--resume-study", "study", "--split", "dev"])
    assert error.value.code == 2


def test_resume_keeps_study_limits_and_delegates(monkeypatch):
    calls = []
    monkeypatch.setattr(run_tiered, "_resume_existing_study", lambda args: calls.append(args) or 0)
    assert run_tiered.main(["--resume-study", "study", "--incomplete-only"]) == 0
    assert calls[0].max_steps is None
    assert calls[0].incomplete_only is True


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("steps", [None, 50, 100, "unlimited", -1])
def test_tiered_main_delegates_n_jobs_to_worker_parallel(monkeypatch, workers, steps):
    calls = []
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: None)
    monkeypatch.setattr(
        run_tiered,
        "run_tiered_parallel",
        lambda **kwargs: calls.append(kwargs) or 0,
    )

    extra = [] if steps is None else ["--max-steps", str(steps)]
    assert run_tiered.main(["--site", "mattermost", "--n-jobs", str(workers), *extra]) == 0
    expected_steps = 50 if steps is None else -1 if steps == "unlimited" else steps
    assert calls[0]["args"].max_steps == expected_steps
    assert all(env_args.max_steps == expected_steps for env_args in calls[0]["filtered"])

    assert calls
    assert calls[0]["args"].n_jobs == workers
    assert calls[0]["selected_sites"] == ["mattermost"]
    assert len(calls[0]["filtered"]) == 23


def test_tiered_queue_worker_dispatch_preserves_owner_and_retries(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: None)
    monkeypatch.setattr(run_tiered, "_build_agent", lambda model: None)
    monkeypatch.setattr(run_tiered, "ensure_sites_ready", lambda *args: True)
    monkeypatch.setattr(run_tiered, "print_eval_results", lambda *args: None)
    monkeypatch.setattr(run_tiered, "WebArenaProStudy", lambda **kwargs: SimpleNamespace(
        dir=tmp_path,
        run_queue=lambda *args, **kwargs: calls.append((args, kwargs)),
    ))
    queue_path = tmp_path / "queue.jsonl"
    assert run_tiered.main([
        "--split", "dev", "--task", "421", "--task-queue", str(queue_path),
        "--queue-worker", "worker-7", "--n-relaunch", "3",
    ]) == 0
    assert calls == [((queue_path, "worker-7"), {"n_relaunch": 3})]


@pytest.mark.parametrize("argv", [
    ["--task-queue", "queue.jsonl"],
    ["--queue-worker", "worker-0"],
    ["--task-queue", "queue.jsonl", "--queue-worker", "worker-0", "--n-jobs", "2"],
    ["--task-queue", "queue.jsonl", "--queue-worker", "worker-0", "--dry-run"],
    ["--task-queue", "queue.jsonl", "--queue-worker", "worker-0", "--resume-study", "study"],
    ["--n-relaunch", "0"],
    ["--n-jobs", "0"],
    ["--max-worker-restarts", "-1"],
    ["--retry-from-start"],
    ["--incomplete-only"],
    ["--no-reset-per-task", "--n-jobs", "2"],
    ["--no-reset-per-task", "--max-worker-restarts", "1"],
])
def test_tiered_rejects_invalid_queue_worker_options(argv):
    with pytest.raises(SystemExit) as error:
        run_tiered._parse_args(argv)
    assert error.value.code == 2


@pytest.mark.parametrize("extra,workers,steps,retries", [([], 4, "17", "4"),
    (["--n-jobs", "8", "--max-steps", "9", "--n-relaunch", "2"], 8, "9", "2"),
    (["--max-steps", "unlimited"], 4, "-1", "4"),
    (["--max-steps", "-1"], 4, "-1", "4")])
def test_resume_queue_preserves_saved_selection_model_and_settings(
    tmp_path, monkeypatch, extra, workers, steps, retries,
):
    from webarena_pro_bgym.task_queue import TaskQueue
    TaskQueue.create(tmp_path / "queue.jsonl", {421: ["mattermost"], 426: ["nextcloud"]})
    original = ["/old/python", "/old/entry.py", "--split", "dev", "--config-dir", str(tmp_path / "configs"),
                "--task", "421,426", "--site", "mattermost", "--site", "nextcloud", "--reset-per-task",
                "--n-jobs", "1", "--max-steps", "17", "--n-relaunch", "4", "--agent-model", run_tiered.DEFAULT_AGENT_MODEL]
    (tmp_path / "queue_run.json").write_text(json.dumps({"command": original, "worker_count": 4, "prewarm": False}))
    (tmp_path / "study.pkl.gz").write_bytes(b"original parent metadata")
    calls = []
    monkeypatch.setattr(run_tiered, "ensure_docker_running", lambda: True)
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: None)
    monkeypatch.setattr(run_tiered, "aggregate_parallel_results", lambda **kwargs: None)
    monkeypatch.setattr(run_tiered, "run_queue_workers", lambda **kwargs: calls.append(kwargs) or 0)
    assert run_tiered.main(["--resume-study", str(tmp_path), *extra]) == 0
    call = calls[0]
    assert call["resume"] is True and call["prewarm"] is False
    assert call["worker_count"] == workers
    assert call["task_sites"] == {421: ["mattermost"], 426: ["nextcloud"]}
    command = call["command"]
    assert command[:2] == [run_tiered.sys.executable, str(run_tiered.Path(run_tiered.__file__).resolve())]
    assert command[command.index("--max-steps") + 1] == steps
    assert command[command.index("--n-relaunch") + 1] == retries
    assert command[command.index("--split") + 1] == "dev"
    assert command[command.index("--config-dir") + 1] == str(tmp_path / "configs")
    assert command[command.index("--agent-model") + 1] == run_tiered.DEFAULT_AGENT_MODEL
    assert (tmp_path / "study.pkl.gz").read_bytes() == b"original parent metadata"


def test_new_run_refuses_existing_study_before_overwriting_metadata(tmp_path, caplog):
    path = tmp_path / "study.pkl.gz"
    path.write_bytes(b"original")
    assert run_tiered.main(["--study-dir", str(tmp_path), "--n-jobs", "4"]) == 1
    assert path.read_bytes() == b"original"
    assert "--resume-study" in caplog.text


def test_resume_queue_reports_corrupt_metadata_without_traceback(tmp_path, caplog):
    (tmp_path / "queue.jsonl").write_text("{}\n")
    (tmp_path / "queue_run.json").write_text("broken")
    assert run_tiered.main(["--resume-study", str(tmp_path)]) == 1
    assert "Cannot resume queued study" in caplog.text


@pytest.mark.parametrize("state,status", [("done", 0), ("failed", 1), ("started", 1)])
def test_resume_terminal_queue_needs_no_docker_or_api_key(tmp_path, monkeypatch, state, status):
    from webarena_pro_bgym.task_queue import TaskQueue
    queue = TaskQueue.create(tmp_path / "queue.jsonl", {421: ["mattermost"]})
    queue.claim("old")
    queue.started(421, "old")
    if state == "done":
        queue.complete(421, "old")
    elif state == "failed":
        queue.fail(421, "old", "Previous failure")
    (tmp_path / "queue_run.json").write_text(json.dumps({
        "command": ["old-python", "old-script", "--max-steps", "17", "--n-relaunch", "2"],
        "worker_count": 4, "prewarm": False,
    }))
    monkeypatch.setattr(run_tiered, "ensure_docker_running", lambda: pytest.fail("No runtime required"))
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: pytest.fail("No model required"))
    monkeypatch.setattr(run_tiered, "aggregate_parallel_results", lambda **kwargs: None)
    assert run_tiered.main(["--resume-study", str(tmp_path), "--incomplete-only"]) == status
    expected = "interrupted" if state == "started" else state
    assert TaskQueue.load(queue.path).status()[0]["state"] == expected


@pytest.mark.parametrize("flags,mode", [([], "continue"), (["--retry-from-start"], "fresh"),
                                       (["--incomplete-only"], "incomplete"),
                                       (["--incomplete-only", "--retry-from-start"], "incomplete")])
@pytest.mark.parametrize("state", ["failed", "interrupted"])
def test_resume_modes_select_failed_and_interrupted_work(tmp_path, monkeypatch, flags, mode, state):
    from webarena_pro_bgym.task_queue import TaskQueue

    queue = TaskQueue.create(tmp_path / "queue.jsonl", {421: ["mattermost"]})
    queue.claim("old")
    queue.started(421, "old")
    if state == "failed":
        queue.fail(421, "old", "Step timed out")
    else:
        queue.abandon_worker("old", "Worker crashed")
    (tmp_path / "queue_run.json").write_text(json.dumps({
        "command": ["old-python", "old-script", "--max-steps", "17", "--n-relaunch", "2"],
        "worker_count": 4, "prewarm": False, "max_worker_restarts": 7,
    }))
    calls = []
    runtime = []
    monkeypatch.setattr(run_tiered, "ensure_docker_running", lambda: runtime.append("docker") or True)
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: None)
    monkeypatch.setattr(run_tiered, "aggregate_parallel_results", lambda **kwargs: None)
    monkeypatch.setattr(run_tiered, "run_queue_workers", lambda **kwargs: calls.append(kwargs) or 0)
    assert run_tiered.main(["--resume-study", str(tmp_path), *flags]) == 0
    assert calls[0]["resume_mode"] == mode
    assert calls[0]["max_worker_restarts"] == 7
    assert runtime == ([] if mode == "incomplete" else ["docker"])


def test_resume_can_override_saved_worker_restart_budget(tmp_path, monkeypatch):
    from webarena_pro_bgym.task_queue import TaskQueue

    queue = TaskQueue.create(tmp_path / "queue.jsonl", {421: ["mattermost"]})
    queue.claim("old")
    queue.started(421, "old")
    queue.complete(421, "old")
    (tmp_path / "queue_run.json").write_text(json.dumps({
        "command": ["python", "script"], "worker_count": 1, "max_worker_restarts": 7,
    }))
    calls = []
    monkeypatch.setattr(run_tiered, "aggregate_parallel_results", lambda **kwargs: None)
    monkeypatch.setattr(run_tiered, "run_queue_workers", lambda **kwargs: calls.append(kwargs) or 0)
    assert run_tiered.main(["--resume-study", str(tmp_path), "--max-worker-restarts", "0"]) == 0
    assert calls[0]["max_worker_restarts"] == 0


def test_no_reset_uses_existing_in_process_runtime(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: None)
    monkeypatch.setattr(run_tiered, "_build_agent", lambda model: None)
    monkeypatch.setattr(run_tiered, "ensure_sites_ready", lambda sites, args: calls.append("preflight") or True)
    monkeypatch.setattr(run_tiered, "ensure_docker_running", lambda: pytest.fail("Existing remote sites need no Docker"))
    monkeypatch.setattr(run_tiered, "print_eval_results", lambda *args: None)
    monkeypatch.setattr(run_tiered, "WebArenaProStudy", lambda **kwargs: SimpleNamespace(
        dir=tmp_path, run=lambda **kwargs: calls.append(kwargs),
    ))
    assert run_tiered.main(["--split", "dev", "--task", "421", "--no-reset-per-task", "--no-autostart"]) == 0
    assert calls == ["preflight", {"n_jobs": 1, "parallel_backend": "sequential", "n_relaunch": 1}]


def test_queue_resume_requires_isolated_reset(tmp_path, caplog):
    (tmp_path / "queue.jsonl").touch()
    assert run_tiered.main(["--resume-study", str(tmp_path), "--no-reset-per-task"]) == 2
    assert "per-task reset" in caplog.text


def test_resume_legacy_source_routes_to_existing_recovery_queue(tmp_path, monkeypatch):
    from webarena_pro_bgym.task_queue import TaskQueue

    recovery = tmp_path / "_recovery"
    TaskQueue.create(recovery / "queue.jsonl", {421: ["mattermost"]})
    (recovery / "queue_run.json").write_text(json.dumps({
        "command": ["old-python", "old-legacy.py", "--source-study", str(recovery), "--n-relaunch", "2"],
        "worker_count": 2,
    }))
    calls = []
    monkeypatch.setattr(run_tiered, "ensure_docker_running", lambda: True)
    monkeypatch.setattr(run_tiered, "_required_api_key_env_var", lambda model: pytest.fail("Keep serialized model"))
    monkeypatch.setattr(run_tiered, "aggregate_parallel_results", lambda **kwargs: None)
    monkeypatch.setattr(run_tiered, "run_queue_workers", lambda **kwargs: calls.append(kwargs) or 0)
    assert run_tiered.main(["--resume-study", str(tmp_path), "--max-steps", "25"]) == 0
    call = calls[0]
    assert call["root_dir"] == recovery.resolve()
    assert call["worker_count"] == 2
    assert call["command"] == [run_tiered.sys.executable,
                               str(run_tiered.Path(run_tiered.__file__).with_name("legacy_recovery.py").resolve()),
                               "--source-study", str(recovery), "--n-relaunch", "2", "--max-steps", "25"]


@pytest.mark.parametrize("value", ["0", "-2", "bad", "1.5"])
def test_invalid_step_budget(value):
    with pytest.raises(SystemExit) as error:
        run_tiered._parse_args(["--max-steps", value])
    assert error.value.code == 2


@pytest.mark.parametrize("value", ["-1", "unlimited"])
def test_resume_can_explicitly_override_saved_limit_with_unlimited(monkeypatch, value):
    calls = []
    monkeypatch.setattr(run_tiered, "_resume_existing_study", lambda args: calls.append(args) or 0)
    assert run_tiered.main(["--resume-study", "study", "--max-steps", value]) == 0
    assert calls[0].max_steps == -1
