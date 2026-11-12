"""Legacy migration uses real worker processes and no browser/model services."""

from argparse import Namespace
import json
import os
from pathlib import Path
from types import SimpleNamespace

from webarena_pro_bgym import legacy_recovery, queue_runner
from webarena_pro_bgym.parallel import reserve_worker_slot
from webarena_pro_bgym.study import WebArenaProExpArgs, WebArenaProStudy
from webarena_pro_bgym.task_queue import TaskQueue


class LegacyAgentArgs:
    agent_name = "legacy-fixture"

    def prepare(self):
        pass

    def close(self):
        pass


class LegacyBenchmark:
    name = "legacy-fixture"

    def prepare_backends(self):
        # Imported independently in each actual worker subprocess.
        from webarena_pro_bgym import prewarm
        prewarm.cleanup_runtime_containers = lambda **kwargs: None


class LegacyExperiment(WebArenaProExpArgs):
    def run(self):
        task_id = int(self.env_args.task_name.rsplit(".", 1)[-1])
        error = "WebArenaProStepTimeoutError: fixture timed out" if task_id == 1 else None
        self.err_msg = error
        self.worker_fatal_error = error
        (self.exp_dir / "summary_info.json").write_text(json.dumps({
            "err_msg": error, "n_steps": 1, "cum_reward": 0 if error else 1,
        }))


class LegacyStudy(WebArenaProStudy):
    def set_reproducibility_info(self, **kwargs):
        pass

    def get_results(self, **kwargs):
        return None


def _study(tmp_path):
    root = tmp_path / "original"
    root.mkdir()
    study = LegacyStudy.__new__(LegacyStudy)
    study.dir = root
    study.agent_args = [LegacyAgentArgs()]
    study.benchmark = LegacyBenchmark()
    study.exp_args_list = []
    for task_id in range(3):
        exp = LegacyExperiment(agent_args=LegacyAgentArgs(), env_args=SimpleNamespace(
            task_name=f"webarena-pro-bgym.{task_id}", task_seed=0, max_steps=7,
            task_config=SimpleNamespace(sites=("mattermost",), task_id=task_id),
        ))
        exp.prepare(root)
        if task_id < 2:
            (exp.exp_dir / "summary_info.json").write_text(json.dumps({
                "err_msg": "old error" if task_id else None,
                "cum_reward": 0 if task_id else 1, "n_steps": 1,
            }))
        study.exp_args_list.append(exp)
    study.save()
    return study


def _args(**overrides):
    return Namespace(**({"n_jobs": 1, "n_relaunch": 1, "max_steps": None,
                        "max_worker_restarts": 3, "incomplete_only": False,
                        "no_reset_per_task": False} | overrides))


def test_legacy_bootstrap_preserves_all_outcomes_and_original_artifacts(tmp_path):
    study = _study(tmp_path)
    original = {path: path.read_bytes() for path in study.dir.rglob("*") if path.is_file()}
    root = study.dir / "_recovery"
    task_sites = legacy_recovery._bootstrap(
        study, root, command=["python", "legacy.py"], max_steps=9,
        n_jobs=1, max_worker_restarts=3,
    )
    assert list(task_sites) == [0, 1, 2]
    assert [row["state"] for row in TaskQueue.load(root / "queue.jsonl").status()] == [
        "done", "failed", "pending",
    ]
    loaded = WebArenaProStudy.load(root)
    assert all(exp.exp_dir is None and exp.env_args.max_steps == 9 for exp in loaded.exp_args_list)
    assert all(path.read_bytes() == content for path, content in original.items())
    old_trace = study.exp_args_list[0].exp_dir / "summary_info.json"
    linked = root / "workers" / "legacy" / old_trace.parent.name / old_trace.name
    assert old_trace.stat().st_ino == linked.stat().st_ino


def test_legacy_timeout_is_replaced_and_later_task_completes(tmp_path, monkeypatch):
    study = _study(tmp_path)
    original = {path: path.read_bytes() for path in study.dir.rglob("*") if path.is_file()}
    package = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([
        str(package / "src"), str(package.parent / "webarena-pro-core" / "src"),
        str(package), str(Path(__file__).parent), os.environ.get("PYTHONPATH", ""),
    ]))
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
    monkeypatch.delenv("WP_ACTIVE_RUNTIME_SLOT", raising=False)
    monkeypatch.delenv("WP_QUEUE_STANDBY_SLOT", raising=False)
    monkeypatch.setattr("webarena_pro_bgym.run_eval_cli.ensure_docker_running", lambda: True)
    monkeypatch.setattr(queue_runner, "cleanup_runtime_containers", lambda **kwargs: None)
    monkeypatch.setattr(queue_runner, "reserve_worker_slot", lambda *, sites, worker_index=None:
                        reserve_worker_slot(sites=sites, worker_index=worker_index,
                                            lock_root=tmp_path / "slots"))
    assert legacy_recovery.resume_legacy_study(study, _args()) == 1
    root = study.dir / "_recovery"
    rows = TaskQueue.load(root / "queue.jsonl").status()
    assert [row["state"] for row in rows] == ["done", "failed", "done"]
    assert rows[1]["worker_id"] != rows[2]["worker_id"]
    assert rows[0]["worker_id"] == "legacy"
    assert all(exp.exp_dir.is_dir() for exp in study.exp_args_list)
    assert all(path.read_bytes() == content for path, content in original.items())


def test_legacy_skip_errors_still_keeps_them_available_for_later_retry(tmp_path, monkeypatch):
    study = _study(tmp_path)
    monkeypatch.setattr("webarena_pro_bgym.run_eval_cli.ensure_docker_running", lambda: True)
    calls = []
    monkeypatch.setattr(legacy_recovery, "run_queue_workers", lambda **kwargs: calls.append(kwargs) or 1)
    assert legacy_recovery.resume_legacy_study(study, _args(incomplete_only=True)) == 1
    assert calls[0]["resume_mode"] == "incomplete"
    root = study.dir / "_recovery"
    queue = TaskQueue.load(root / "queue.jsonl")
    queue.retry(1, full_retry=True)
    assert [row["state"] for row in queue.status()] == ["done", "pending", "pending"]


def test_legacy_no_reset_refuses_before_docker_or_writes(tmp_path, monkeypatch):
    study = _study(tmp_path)
    monkeypatch.setattr("webarena_pro_bgym.run_eval_cli.ensure_docker_running",
                        lambda: (_ for _ in ()).throw(AssertionError("unexpected Docker call")))
    assert legacy_recovery.resume_legacy_study(study, _args(no_reset_per_task=True)) == 2
    assert not (study.dir / "_recovery").exists()
