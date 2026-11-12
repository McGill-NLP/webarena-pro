from pathlib import Path
from types import SimpleNamespace

from scripts import relaunch_errored_experiments
from scripts.relaunch_errored_experiments import (
    ErrorCandidate,
    error_candidates,
    relaunch_candidates,
    reset_exp_args_state,
    reset_candidates_runtime_artifacts,
    reset_task_runtime_artifacts,
)


def _write_runtime_artifacts(exp_dir: Path) -> None:
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "exp_args.pkl").write_text("x")
    (exp_dir / "summary_info.json").write_text("{}")
    (exp_dir / "experiment.log").write_text("log")
    (exp_dir / "dag_trace.html").write_text("<html></html>")
    (exp_dir / "step_0.pkl.gz").write_text("step")


def test_reset_task_runtime_artifacts_removes_matching_task_dirs(tmp_path):
    worker_dir = tmp_path / "workers" / "worker-10"
    target_dir = worker_dir / "2026-05-03_GenericAgent_on_webarena-pro-bgym.100_0"
    archived_dir = worker_dir / "_2026-05-02_GenericAgent_on_webarena-pro-bgym.100_0"
    other_dir = worker_dir / "2026-05-03_GenericAgent_on_webarena-pro-bgym.101_0"
    _write_runtime_artifacts(target_dir)
    _write_runtime_artifacts(archived_dir)
    _write_runtime_artifacts(other_dir)

    removed = reset_task_runtime_artifacts(worker_dir, "100")

    assert removed == [target_dir, archived_dir]
    assert not target_dir.exists()
    assert not archived_dir.exists()
    assert (other_dir / "summary_info.json").exists()
    assert (other_dir / "experiment.log").exists()


def test_reset_candidates_runtime_artifacts_counts_removed_files(tmp_path):
    worker_dir = tmp_path / "workers" / "worker-10"
    exp_dir = worker_dir / "2026-05-03_GenericAgent_on_webarena-pro-bgym.200_0"
    _write_runtime_artifacts(exp_dir)

    removed_count = reset_candidates_runtime_artifacts(
        [
            ErrorCandidate(
                worker_dir=worker_dir,
                task_name="webarena-pro-bgym.200",
                task_id="200",
                status="error",
                sites=("nextcloud",),
            )
        ]
    )

    assert removed_count == 1
    assert not exp_dir.exists()


def test_reset_exp_args_state_clears_error_state():
    exp_args = SimpleNamespace(
        is_dummy=True,
        status="error",
        err_msg="boom",
        stack_trace="trace",
        worker_fatal_error="fatal",
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.200"),
    )

    reset_exp_args_state(exp_args)

    assert exp_args.is_dummy is False
    assert exp_args.status == "incomplete"
    assert exp_args.err_msg is None
    assert exp_args.stack_trace is None
    assert exp_args.worker_fatal_error is None


def test_relaunch_candidates_runs_sequentially_inside_worker(tmp_path, monkeypatch):
    worker_dir = tmp_path / "study"
    exp_args = SimpleNamespace(
        is_dummy=True,
        status="error",
        err_msg="boom",
        stack_trace="trace",
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.203"),
    )
    calls = []

    class DummyStudy:
        avg_step_timeout = 77
        exp_args_list = []

        def _run(self, **kwargs):
            calls.append(("run", kwargs, list(self.exp_args_list), self.avg_step_timeout))

        def get_results(self, suffix):
            calls.append(("get_results", suffix))

    monkeypatch.setattr(
        relaunch_errored_experiments.WebArenaProStudy,
        "load",
        staticmethod(lambda path: DummyStudy()),
    )

    relaunch_candidates(
        [
            ErrorCandidate(
                worker_dir=worker_dir,
                task_name="webarena-pro-bgym.203",
                task_id="203",
                status="error",
                sites=("nextcloud",),
                exp_args=exp_args,
            )
        ],
        jobs=3,
        avg_step_timeout=123,
    )

    assert calls[0][0] == "run"
    assert calls[0][1] == {
        "n_jobs": 1,
        "parallel_backend": "sequential",
        "strict_reproducibility": False,
    }
    assert calls[0][2][0] is exp_args
    assert calls[0][2][0].is_dummy is False
    assert calls[0][2][0].err_msg is None
    assert calls[0][3] == 123
    assert calls[1] == ("get_results", "relaunch")


def test_error_candidates_recovers_missing_tasks_from_study_metadata(tmp_path, monkeypatch):
    study_dir = tmp_path / "study"
    worker_dir = study_dir / "workers" / "worker-12"
    worker_dir.mkdir(parents=True)

    missing_exp_args = SimpleNamespace(
        is_dummy=False,
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.203", task_config=SimpleNamespace(sites=("a",))),
    )
    done_exp_args = SimpleNamespace(
        is_dummy=False,
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.204", task_config=SimpleNamespace(sites=("b",))),
    )
    dummy_study = SimpleNamespace(exp_args_list=[missing_exp_args, done_exp_args])

    monkeypatch.setattr(
        relaunch_errored_experiments.WebArenaProStudy,
        "load",
        staticmethod(lambda path: dummy_study),
    )

    done_result = SimpleNamespace(
        exp_args=done_exp_args,
        status="done",
        exp_dir=tmp_path / "done-exp",
    )
    done_result.exp_dir.mkdir()
    monkeypatch.setattr(
        relaunch_errored_experiments,
        "yield_all_exp_results",
        lambda worker_dir, progress_fn=None: [done_result],
    )

    candidates = error_candidates(study_dir)

    assert len(candidates) == 1
    assert candidates[0].worker_dir == worker_dir
    assert candidates[0].task_name == "webarena-pro-bgym.203"
    assert candidates[0].status == "incomplete"


def test_error_candidates_errors_only_skips_missing_tasks(tmp_path, monkeypatch):
    study_dir = tmp_path / "study"
    worker_dir = study_dir / "workers" / "worker-12"
    worker_dir.mkdir(parents=True)

    missing_exp_args = SimpleNamespace(
        is_dummy=False,
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.203", task_config=SimpleNamespace(sites=("a",))),
    )
    errored_exp_args = SimpleNamespace(
        is_dummy=False,
        env_args=SimpleNamespace(task_name="webarena-pro-bgym.204", task_config=SimpleNamespace(sites=("b",))),
    )
    dummy_study = SimpleNamespace(exp_args_list=[missing_exp_args, errored_exp_args])

    monkeypatch.setattr(
        relaunch_errored_experiments.WebArenaProStudy,
        "load",
        staticmethod(lambda path: dummy_study),
    )

    error_result = SimpleNamespace(
        exp_args=errored_exp_args,
        status="error",
        exp_dir=tmp_path / "error-exp",
    )
    error_result.exp_dir.mkdir()
    monkeypatch.setattr(
        relaunch_errored_experiments,
        "yield_all_exp_results",
        lambda worker_dir, progress_fn=None: [error_result],
    )

    candidates = error_candidates(study_dir, include_incomplete=False)

    assert len(candidates) == 1
    assert candidates[0].task_name == "webarena-pro-bgym.204"
    assert candidates[0].status == "error"
