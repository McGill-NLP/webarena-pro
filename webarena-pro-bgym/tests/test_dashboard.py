import gzip
import json
import os
import pickle
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

import webarena_pro_bgym.dashboard as dashboard
from webarena_pro_bgym.dashboard import (
    build_run_snapshot,
    find_study_processes,
    list_top_level_studies,
    stop_study_processes,
)


def _write_study_pickle(
    path: Path,
    name: str,
    task_ids: list[int],
    sites_by_task: dict[int, tuple[str, ...]] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exp_args_list = []
    for task_id in task_ids:
        task_config = SimpleNamespace(task_id=task_id)
        if sites_by_task and task_id in sites_by_task:
            task_config.sites = sites_by_task[task_id]
            task_config.website = sites_by_task[task_id][0]
        exp_args_list.append(
            SimpleNamespace(
                env_args=SimpleNamespace(
                    task_name=f"webarena-pro-bgym.{task_id}",
                    task_config=task_config,
                )
            )
        )
    study = SimpleNamespace(name=name, exp_args_list=exp_args_list)
    with gzip.open(path, "wb") as handle:
        pickle.dump(study, handle)


def test_list_top_level_studies_excludes_nested_worker_studies(tmp_path):
    root = tmp_path / "results"
    top_level = root / "study-a"
    nested = top_level / "workers" / "worker-0"
    other = root / "study-b"

    _write_study_pickle(top_level / "study.pkl.gz", "study-a", [200])
    _write_study_pickle(nested / "study.pkl.gz", "worker-0", [200])
    _write_study_pickle(other / "study.pkl.gz", "study-b", [201])

    studies = list_top_level_studies(root, limit=10)

    assert studies == [other, top_level]


def test_build_run_snapshot_tracks_pending_running_and_finished_tasks(tmp_path, monkeypatch):
    study_dir = tmp_path / "mattermost-parallel"
    _write_study_pickle(study_dir / "study.pkl.gz", "mattermost-parent", [200, 201, 202])
    _write_study_pickle(study_dir / "workers" / "worker-0" / "study.pkl.gz", "worker-0", [200, 202])
    _write_study_pickle(study_dir / "workers" / "worker-1" / "study.pkl.gz", "worker-1", [201])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 321,
                "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {path / 'workers' / 'worker-1'}",
            }
        ],
    )

    finished = study_dir / "workers" / "worker-0" / "2026-04-23_GenericAgent_on_webarena-pro-bgym.200_0"
    finished.mkdir(parents=True)
    (finished / "exp_args.pkl").write_text("x")
    (finished / "summary_info.json").write_text('{"cum_reward": 1, "n_steps": 4}')
    (finished / "experiment.log").write_text("done")

    running = study_dir / "workers" / "worker-1" / "2026-04-23_GenericAgent_on_webarena-pro-bgym.201_0"
    running.mkdir(parents=True)
    (running / "exp_args.pkl").write_text("x")
    (running / "experiment.log").write_text("running")
    (running / "step_0.pkl.gz").write_text("step")

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["total_tasks"] == 3
    assert snapshot["study"]["passed_tasks"] == 1
    assert snapshot["study"]["running_tasks"] == 1
    assert snapshot["study"]["pending_tasks"] == 1
    assert snapshot["study"]["error_tasks"] == 0
    assert snapshot["study"]["completed_tasks"] == 1
    assert snapshot["study"]["elapsed_seconds"] is not None

    tasks = {task["task_id"]: task for task in snapshot["tasks"]}
    assert tasks["200"]["status"] == "passed"
    assert tasks["200"]["worker"] == "worker-0"
    assert tasks["200"]["elapsed_seconds"] is not None
    assert tasks["201"]["status"] == "running"
    assert tasks["201"]["observed_steps"] == 1
    assert tasks["201"]["elapsed_seconds"] is not None
    assert tasks["202"]["status"] == "pending"
    assert tasks["202"]["worker"] == "worker-0"
    assert tasks["202"]["elapsed_seconds"] is None

    workers = {worker["worker"]: worker for worker in snapshot["workers"]}
    assert workers["worker-0"]["elapsed_seconds"] is not None
    assert workers["worker-1"]["elapsed_seconds"] is not None
    assert workers["worker-1"]["running_tasks"] == 1


def test_build_run_snapshot_does_not_time_pending_setup_directories(tmp_path, monkeypatch):
    study_dir = tmp_path / "setup-pending"
    _write_study_pickle(study_dir / "study.pkl.gz", "setup-pending", [200])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    exp_dir = study_dir / "2026-04-23_GenericAgent_on_webarena-pro-bgym.200_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "exp_args.pkl").write_text("prepared but not started")

    snapshot = build_run_snapshot(study_dir)
    task = snapshot["tasks"][0]

    assert task["status"] == "pending"
    assert task["started_at"] is None
    assert task["updated_at"] is None
    assert task["elapsed_seconds"] is None


def test_build_run_snapshot_includes_website_worker_status(tmp_path, monkeypatch):
    study_dir = tmp_path / "resource-parallel"
    _write_study_pickle(study_dir / "study.pkl.gz", "resource-parent", [200, 201])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    status_payload = {
        "source": "scheduler",
        "updated_at": 1_700_000_000,
        "worker_count": 2,
        "pending_tasks": [201],
        "running_tasks": [
            {
                "task_id": 200,
                "sites": ["nextcloud"],
                "assignment": {"nextcloud": 1},
                "log_path": "/tmp/task-200.log",
            }
        ],
        "sites": [
            {
                "site": "nextcloud",
                "remaining_tasks": 2,
                "workers": [
                    {"worker_index": 0, "worker": "nextcloud-w0", "status": "idle"},
                    {
                        "worker_index": 1,
                        "worker": "nextcloud-w1",
                        "status": "busy",
                        "task_id": 200,
                        "log_path": "/tmp/task-200.log",
                    },
                ],
            }
        ],
    }
    (study_dir / dashboard.RESOURCE_SCHEDULER_STATUS_FILE).write_text(
        json.dumps(status_payload)
    )

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["is_parallel"] is True
    website_workers = snapshot["website_workers"]
    assert website_workers["source"] == "scheduler"
    assert website_workers["updated_at"] == "2023-11-14T22:13:20+00:00"
    assert website_workers["worker_count"] == 2
    assert website_workers["running_tasks"][0]["task_id"] == 200
    site = website_workers["sites"][0]
    assert site["site"] == "nextcloud"
    assert site["counts"] == {"running": 2}
    assert site["lifecycle_counts"] == {"running": 2}
    assert site["allocation_counts"] == {"free": 1, "in-use": 1}
    assert site["workers"][1]["lifecycle_status"] == "running"
    assert site["workers"][1]["allocation_status"] == "in-use"
    assert site["workers"][1]["task_id"] == 200


def test_build_run_snapshot_infers_docker_worker_allocation_from_running_tasks(
    tmp_path, monkeypatch
):
    study_dir = tmp_path / "tiered-parallel"
    _write_study_pickle(
        study_dir / "study.pkl.gz",
        "tiered-parent",
        [100, 101],
        sites_by_task={100: ("mattermost",), 101: ("nextcloud",)},
    )
    worker_1 = study_dir / "workers" / "worker-1"
    _write_study_pickle(
        worker_1 / "study.pkl.gz",
        "worker-1",
        [100],
        sites_by_task={100: ("mattermost",)},
    )
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 321,
                "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {worker_1}",
            }
        ],
    )
    monkeypatch.setattr(
        dashboard,
        "_discover_docker_website_workers",
        lambda: dashboard._normalise_website_worker_status(
            {
                "source": "docker",
                "updated_at": 1_700_000_000,
                "sites": [
                    {
                        "site": "mattermost",
                        "workers": [
                            {
                                "worker_index": 1,
                                "worker": "mattermost-w1",
                                "status": "running",
                            }
                        ],
                    },
                    {
                        "site": "nextcloud",
                        "workers": [
                            {
                                "worker_index": 1,
                                "worker": "nextcloud-w1",
                                "status": "running",
                            }
                        ],
                    },
                ],
            }
        ),
    )

    running = worker_1 / "2026-04-23_GenericAgent_on_webarena-pro-bgym.100_0"
    running.mkdir(parents=True)
    (running / "exp_args.pkl").write_text("x")
    (running / "experiment.log").write_text("running")
    (running / "step_0.pkl.gz").write_text("step")

    snapshot = build_run_snapshot(study_dir)

    sites = {
        site["site"]: {worker["worker"]: worker for worker in site["workers"]}
        for site in snapshot["website_workers"]["sites"]
    }
    mattermost = sites["mattermost"]["mattermost-w1"]
    nextcloud = sites["nextcloud"]["nextcloud-w1"]

    assert mattermost["allocation_status"] == "in-use"
    assert mattermost["in_use"] is True
    assert mattermost["task_id"] == "100"
    assert nextcloud["allocation_status"] == "free"
    assert nextcloud["in_use"] is False

    website_sites = {
        site["site"]: site for site in snapshot["website_workers"]["sites"]
    }
    assert website_sites["mattermost"]["allocation_counts"] == {"in-use": 1}
    assert website_sites["nextcloud"]["allocation_counts"] == {"free": 1}


def test_build_run_snapshot_overlays_resetting_worker_event(tmp_path, monkeypatch):
    study_dir = tmp_path / "resource-resetting"
    _write_study_pickle(study_dir / "study.pkl.gz", "resource-parent", [200])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    (study_dir / dashboard.RESOURCE_SCHEDULER_STATUS_FILE).write_text(
        json.dumps(
            {
                "source": "scheduler",
                "updated_at": 1_700_000_000,
                "worker_count": 1,
                "running_tasks": [
                    {
                        "task_id": 200,
                        "sites": ["nextcloud"],
                        "assignment": {"nextcloud": 0},
                        "log_path": "/tmp/task-200.log",
                    }
                ],
                "sites": [
                    {
                        "site": "nextcloud",
                        "remaining_tasks": 1,
                        "workers": [
                            {
                                "worker_index": 0,
                                "worker": "nextcloud-w0",
                                "lifecycle_status": "running",
                                "allocation_status": "in-use",
                                "task_id": 200,
                            }
                        ],
                    }
                ],
            }
        )
    )
    events_dir = study_dir / dashboard.RESOURCE_SCHEDULER_EVENTS_DIR
    events_dir.mkdir()
    (events_dir / "nextcloud-w0.json").write_text(
        json.dumps(
            {
                "site": "nextcloud",
                "worker_index": 0,
                "task_id": 200,
                "lifecycle_status": "resetting",
                "updated_at": 1_700_000_001,
            }
        )
    )

    snapshot = build_run_snapshot(study_dir)

    site = snapshot["website_workers"]["sites"][0]
    assert site["lifecycle_counts"] == {"resetting": 1}
    assert site["allocation_counts"] == {"in-use": 1}
    assert site["workers"][0]["lifecycle_status"] == "resetting"
    assert site["workers"][0]["allocation_status"] == "in-use"


def test_build_run_snapshot_reports_errored_tasks_separately_from_failed(tmp_path, monkeypatch):
    study_dir = tmp_path / "qwen-parallel"
    _write_study_pickle(study_dir / "study.pkl.gz", "qwen-parent", [100, 101])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    errored = study_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.100_0"
    errored.mkdir(parents=True)
    (errored / "exp_args.pkl").write_text("x")
    (errored / "summary_info.json").write_text(
        '{"cum_reward": 0, "n_steps": 0, "err_msg": "RuntimeError: no running event loop"}'
    )

    failed = study_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.101_0"
    failed.mkdir(parents=True)
    (failed / "exp_args.pkl").write_text("x")
    (failed / "summary_info.json").write_text('{"cum_reward": 0, "n_steps": 5}')

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["completed_tasks"] == 2
    assert snapshot["study"]["error_tasks"] == 1
    assert snapshot["study"]["failed_tasks"] == 1
    assert snapshot["study"]["avg_reward"] == 0.0

    tasks = {task["task_id"]: task for task in snapshot["tasks"]}
    assert tasks["100"]["status"] == "error"
    assert tasks["100"]["err_msg"] == "RuntimeError: no running event loop"
    assert tasks["101"]["status"] == "failed"


def test_build_run_snapshot_average_reward_is_binary_success_rate(tmp_path, monkeypatch):
    study_dir = tmp_path / "tiered-parallel"
    _write_study_pickle(study_dir / "study.pkl.gz", "tiered-parent", [100, 101, 102])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    passed = study_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.100_0"
    passed.mkdir(parents=True)
    (passed / "exp_args.pkl").write_text("x")
    (passed / "summary_info.json").write_text('{"cum_reward": 12.7, "n_steps": 8}')

    partial = study_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.101_0"
    partial.mkdir(parents=True)
    (partial / "exp_args.pkl").write_text("x")
    (partial / "summary_info.json").write_text('{"cum_reward": 0.5, "n_steps": 4}')

    errored = study_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.102_0"
    errored.mkdir(parents=True)
    (errored / "exp_args.pkl").write_text("x")
    (errored / "summary_info.json").write_text(
        '{"cum_reward": 0, "n_steps": 0, "err_msg": "boom"}'
    )

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["completed_tasks"] == 3
    assert snapshot["study"]["passed_tasks"] == 1
    assert snapshot["study"]["partial_tasks"] == 1
    assert snapshot["study"]["error_tasks"] == 1
    assert snapshot["study"]["avg_reward"] == 0.333


def test_build_run_snapshot_marks_incomplete_run_without_live_process_as_stopped(tmp_path, monkeypatch):
    study_dir = tmp_path / "metabase-worker"
    _write_study_pickle(study_dir / "study.pkl.gz", "metabase-worker", [300])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    exp_dir = study_dir / "2026-04-24_GenericAgent_on_webarena-pro-bgym.300_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "exp_args.pkl").write_text("x")
    (exp_dir / "experiment.log").write_text("stopped")
    (exp_dir / "step_0.pkl.gz").write_text("step")
    old = 1_700_000_000
    for path in [exp_dir / "exp_args.pkl", exp_dir / "experiment.log", exp_dir / "step_0.pkl.gz"]:
        os.utime(path, (old, old))
    os.utime(exp_dir, (old, old))

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["running_tasks"] == 0
    assert snapshot["study"]["stopped_tasks"] == 1
    assert snapshot["tasks"][0]["status"] == "stopped"
    task_elapsed = snapshot["tasks"][0]["elapsed_seconds"]
    worker_elapsed = snapshot["workers"][0]["elapsed_seconds"]
    study_elapsed = snapshot["study"]["elapsed_seconds"]
    assert task_elapsed is not None
    assert worker_elapsed is not None
    assert study_elapsed is not None
    assert abs(task_elapsed - worker_elapsed) < 0.01
    assert abs(worker_elapsed - study_elapsed) < 0.01


def test_build_run_snapshot_marks_recent_incomplete_run_as_running_without_live_process(
    tmp_path, monkeypatch
):
    study_dir = tmp_path / "gemma-recent"
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [300])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    exp_dir = study_dir / "2026-05-06_GenericAgent_on_webarena-pro-bgym.300_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "exp_args.pkl").write_text("x")
    (exp_dir / "experiment.log").write_text("running")
    (exp_dir / "step_0.pkl.gz").write_text("step")

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["running_tasks"] == 1
    assert snapshot["study"]["stopped_tasks"] == 0
    assert snapshot["tasks"][0]["status"] == "running"


def test_build_run_snapshot_does_not_confuse_worker_path_prefixes(tmp_path, monkeypatch):
    study_dir = tmp_path / "gemma-prefix-workers"
    worker_1 = study_dir / "workers" / "worker-1"
    worker_10 = study_dir / "workers" / "worker-10"
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [100, 101])
    _write_study_pickle(worker_1 / "study.pkl.gz", "worker-1", [100])
    _write_study_pickle(worker_10 / "study.pkl.gz", "worker-10", [101])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 999,
                "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {worker_10}",
            }
        ],
    )

    worker_1_exp = worker_1 / "2026-05-05_GenericAgent_on_webarena-pro-bgym.100_0"
    worker_1_exp.mkdir(parents=True)
    (worker_1_exp / "exp_args.pkl").write_text("x")
    (worker_1_exp / "experiment.log").write_text("stopped")
    old = 1_700_000_000
    for path in [worker_1_exp / "exp_args.pkl", worker_1_exp / "experiment.log"]:
        os.utime(path, (old, old))
    os.utime(worker_1_exp, (old, old))

    worker_10_exp = worker_10 / "2026-05-05_GenericAgent_on_webarena-pro-bgym.101_0"
    worker_10_exp.mkdir(parents=True)
    (worker_10_exp / "exp_args.pkl").write_text("x")
    (worker_10_exp / "experiment.log").write_text("running")

    snapshot = build_run_snapshot(study_dir)

    tasks = {task["task_id"]: task for task in snapshot["tasks"]}
    assert tasks["100"]["status"] == "stopped"
    assert tasks["101"]["status"] == "running"


def test_build_run_snapshot_marks_relaunching_errored_task_as_running(tmp_path, monkeypatch):
    study_dir = tmp_path / "gemma-relaunch"
    worker_dir = study_dir / "workers" / "worker-10"
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [100])
    _write_study_pickle(worker_dir / "study.pkl.gz", "worker-10", [100])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 999,
                "command": (
                    "python scripts/relaunch_errored_experiments.py --run-one "
                    f"--worker-dir {worker_dir} --task-name webarena-pro-bgym.100"
                ),
            }
        ],
    )

    exp_dir = worker_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.100_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "exp_args.pkl").write_text("x")
    (exp_dir / "experiment.log").write_text("running")
    (exp_dir / "summary_info.json").write_text(
        '{"cum_reward": 0, "n_steps": 0, "err_msg": "RetryError: Error 524"}'
    )

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["running_tasks"] == 1
    assert snapshot["study"]["error_tasks"] == 0
    assert snapshot["study"]["completed_tasks"] == 0
    assert snapshot["study"]["can_stop"] is True
    assert snapshot["tasks"][0]["status"] == "running"
    assert snapshot["tasks"][0]["worker"] == "worker-10"


def test_build_run_snapshot_marks_relaunching_task_as_running_without_existing_exp_dir(
    tmp_path, monkeypatch
):
    study_dir = tmp_path / "gemma-relaunch-fresh"
    worker_dir = study_dir / "workers" / "worker-10"
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [100])
    _write_study_pickle(worker_dir / "study.pkl.gz", "worker-10", [100])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 999,
                "command": (
                    "python scripts/relaunch_errored_experiments.py --run-one "
                    f"--worker-dir {worker_dir} --task-name webarena-pro-bgym.100"
                ),
            }
        ],
    )

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["running_tasks"] == 1
    assert snapshot["study"]["completed_tasks"] == 0
    assert snapshot["study"]["error_tasks"] == 0
    assert snapshot["tasks"][0]["status"] == "running"
    assert snapshot["tasks"][0]["worker"] == "worker-10"
    assert snapshot["tasks"][0]["elapsed_seconds"] == 0.0


def test_build_run_snapshot_marks_generic_run_one_task_as_running_from_exp_args_path(
    tmp_path, monkeypatch
):
    study_dir = tmp_path / "gemma-added"
    worker_dir = study_dir / "workers" / "worker-10"
    exp_args_path = tmp_path / ".exp_args" / "worker-10-100.pkl"
    exp_args_path.parent.mkdir()
    exp_args_path.write_text("not a real pickle")
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [100])
    _write_study_pickle(worker_dir / "study.pkl.gz", "worker-10", [100])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {
                "pid": 999,
                "command": (
                    "python /tmp/run_gemma31b_added_tasks.py --run-one "
                    f"--worker-dir {worker_dir} --exp-args-path {exp_args_path}"
                ),
            }
        ],
    )

    exp_dir = worker_dir / "2026-05-06_GenericAgent_on_webarena-pro-bgym.100_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "exp_args.pkl").write_text("x")
    (exp_dir / "experiment.log").write_text("running")

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["running_tasks"] == 1
    assert snapshot["study"]["stopped_tasks"] == 0
    assert snapshot["tasks"][0]["status"] == "running"
    assert snapshot["tasks"][0]["worker"] == "worker-10"


def test_build_run_snapshot_prefers_latest_non_archived_exp_dir(tmp_path, monkeypatch):
    study_dir = tmp_path / "gemma-rerun"
    worker_dir = study_dir / "workers" / "worker-12"
    _write_study_pickle(study_dir / "study.pkl.gz", "gemma-parent", [100])
    _write_study_pickle(worker_dir / "study.pkl.gz", "worker-12", [100])
    monkeypatch.setattr(dashboard, "find_study_processes", lambda path: [])

    archived = worker_dir / "_2026-05-03_GenericAgent_on_webarena-pro-bgym.100_0"
    archived.mkdir(parents=True)
    (archived / "exp_args.pkl").write_text("x")
    (archived / "summary_info.json").write_text(
        '{"cum_reward": 0, "n_steps": 0, "err_msg": "old archived error"}'
    )

    fresh = worker_dir / "2026-05-04_GenericAgent_on_webarena-pro-bgym.100_0"
    fresh.mkdir(parents=True)
    (fresh / "exp_args.pkl").write_text("x")
    (fresh / "summary_info.json").write_text('{"cum_reward": 1, "n_steps": 3}')

    snapshot = build_run_snapshot(study_dir)

    task = snapshot["tasks"][0]
    assert task["status"] == "passed"
    assert task["err_msg"] is None
    assert task["exp_relative_dir"] == str(fresh.relative_to(study_dir))


def test_find_study_processes_matches_selected_study_and_workers(tmp_path):
    study_dir = tmp_path / "metabase-worker"
    worker_dir = study_dir / "workers" / "worker-0"
    ps_output = "\n".join(
        [
            f"111 python -m webarena_pro_bgym.run_eval_cli --study-dir {study_dir}",
            f"222 python /tmp/run_eval_cli.py --study-dir {worker_dir}",
            f"333 python -m something_else --study-dir {tmp_path / 'other-study'}",
        ]
    )

    processes = find_study_processes(study_dir, ps_output=ps_output)

    assert [process["pid"] for process in processes] == [111, 222]


@pytest.mark.parametrize("dashboard_command", [
    "uv run webarena-pro run dashboard",
    "python /tmp/.venv/bin/webarena-pro run dashboard",
    "python -m webarena_pro_core.cli run dashboard",
    "python -m webarena_pro_bgym.run_cli dashboard",
    "python -m webarena_pro_bgym.run_dashboard_cli",
])
def test_find_study_processes_ignores_dashboard_process(tmp_path, dashboard_command):
    study_dir = tmp_path / "active-study"
    ps_output = "\n".join(
        [
            f"111 {dashboard_command} --study-dir {study_dir}",
            f"222 python -m webarena_pro_bgym.run_cli --study-dir {study_dir}",
        ]
    )

    processes = find_study_processes(study_dir, ps_output=ps_output)

    assert [process["pid"] for process in processes] == [222]


def test_find_study_processes_does_not_walk_unrelated_tmux_panes(tmp_path):
    study_dir = tmp_path / "active-study"
    ps_output = "\n".join(
        [
            f"111 1 tmux new-session -d webarena-pro run --study-dir {study_dir}",
            f"222 111 webarena-pro run --study-dir {study_dir}",
            f"333 111 webarena-pro run dashboard --study-dir {study_dir}",
            "444 333 browser-helper",
        ]
    )

    processes = find_study_processes(study_dir, ps_output=ps_output)

    assert [process["pid"] for process in processes] == [222]


def test_find_study_processes_matches_relaunch_coordinator_and_run_one_children(tmp_path):
    study_dir = tmp_path / "gemma-worker"
    worker_dir = study_dir / "workers" / "worker-10"
    ps_output = "\n".join(
        [
            f"111 1 python scripts/relaunch_errored_experiments.py --study-dir {study_dir}",
            f"222 111 python scripts/relaunch_errored_experiments.py --run-one --worker-dir {worker_dir} --task-name webarena-pro-bgym.100",
            "333 222 python child-helper.py",
            f"444 1 python -m something_else --study-dir {tmp_path / 'other-study'}",
        ]
    )

    processes = find_study_processes(study_dir, ps_output=ps_output)

    assert [process["pid"] for process in processes] == [111, 222, 333]


def test_find_study_processes_matches_generic_run_one_workers(tmp_path):
    study_dir = tmp_path / "gemma-added"
    worker_dir = study_dir / "workers" / "worker-10"
    ps_output = "\n".join(
        [
            f"111 1 python /tmp/run_gemma31b_added_tasks.py --run-one --worker-dir {worker_dir} --exp-args-path /tmp/worker-10-100.pkl",
            "222 111 python child-helper.py",
            f"333 1 python /tmp/run_gemma31b_added_tasks.py --run-one --worker-dir {tmp_path / 'other' / 'workers' / 'worker-10'} --exp-args-path /tmp/worker-10-100.pkl",
        ]
    )

    processes = find_study_processes(study_dir, ps_output=ps_output)

    assert [process["pid"] for process in processes] == [111, 222]


def test_stop_study_processes_signals_matching_pids(tmp_path, monkeypatch):
    study_dir = tmp_path / "mattermost-worker"
    signal_calls = []
    alive = {101, 202}

    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {"pid": 101, "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {path}"},
            {"pid": 202, "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {path / 'workers' / 'worker-0'}"},
        ],
    )
    monkeypatch.setattr(dashboard.time, "sleep", lambda _: None)

    def fake_kill(pid, sig):
        signal_calls.append((pid, sig))
        if sig == 0:
            if pid in alive:
                return None
            raise ProcessLookupError(pid)
        if sig == signal.SIGTERM:
            alive.discard(pid)
            return None
        if sig == signal.SIGKILL:
            alive.discard(pid)
            return None
        raise AssertionError(f"Unexpected signal {sig}")

    monkeypatch.setattr(dashboard.os, "kill", fake_kill)

    result = stop_study_processes(study_dir)

    assert result["matched_pids"] == [101, 202]
    assert result["stopped_pids"] == [101, 202]
    assert result["escalated_pids"] == []
    assert signal_calls[:2] == [(101, signal.SIGTERM), (202, signal.SIGTERM)]


def test_stop_study_processes_waits_for_graceful_exit_before_sigkill(tmp_path, monkeypatch):
    study_dir = tmp_path / "cross-site-worker"
    signal_calls = []
    alive = {404}
    now = {"value": 0.0}

    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [
            {"pid": 404, "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {path}"}
        ],
    )

    def fake_sleep(interval):
        now["value"] += interval
        alive.clear()

    def fake_time():
        return now["value"]

    def fake_kill(pid, sig):
        signal_calls.append((pid, sig))
        if sig == 0:
            if pid in alive:
                return None
            raise ProcessLookupError(pid)
        if sig == signal.SIGTERM:
            return None
        if sig == signal.SIGKILL:
            raise AssertionError("SIGKILL should not be needed when the process exits during the grace period")
        raise AssertionError(f"Unexpected signal {sig}")

    monkeypatch.setattr(dashboard.time, "sleep", fake_sleep)
    monkeypatch.setattr(dashboard.time, "time", fake_time)
    monkeypatch.setattr(dashboard.os, "kill", fake_kill)

    result = stop_study_processes(study_dir)

    assert result["matched_pids"] == [404]
    assert result["stopped_pids"] == [404]
    assert result["escalated_pids"] == []
    assert signal_calls[0] == (404, signal.SIGTERM)


def test_build_run_snapshot_reports_stoppable_study(tmp_path, monkeypatch):
    study_dir = tmp_path / "notion-worker"
    _write_study_pickle(study_dir / "study.pkl.gz", "notion-worker", [200])
    monkeypatch.setattr(
        dashboard,
        "find_study_processes",
        lambda path: [{"pid": 999, "command": f"python -m webarena_pro_bgym.run_eval_cli --study-dir {path}"}],
    )

    snapshot = build_run_snapshot(study_dir)

    assert snapshot["study"]["can_stop"] is True
    assert snapshot["study"]["running_pids"] == [999]
