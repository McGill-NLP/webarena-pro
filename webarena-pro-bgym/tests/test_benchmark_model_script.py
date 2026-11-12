"""Check wrapper launch/resume arguments without Docker or a model call."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_benchmark_model.sh"


@pytest.fixture
def run_wrapper(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "print(json.dumps(sys.argv[1:]))\n"
        "sys.exit(int(os.environ.get('WRAPPER_TEST_EXIT', '0')))\n"
    )
    uv.chmod(0o755)
    root = tmp_path / "study with spaces"
    env = dict(os.environ)
    env.update(PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
               UV_CACHE_DIR=str(tmp_path / "uv-cache"), BENCHMARK_N_JOBS="4",
               BENCHMARK_MAX_STEPS="50")

    def run(*args, exit_code=0):
        result = subprocess.run(
            ["bash", str(SCRIPT), "model-key", "model-label", str(root), *args],
            env=env | {"WRAPPER_TEST_EXIT": str(exit_code)},
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == exit_code, result.stderr
        return json.loads(result.stdout), result.stderr

    return root, run


def test_all_sites_new_run_keeps_launch_settings(run_wrapper):
    root, run = run_wrapper
    args, _ = run("--split", "dev")
    assert args == ["run", "webarena-pro", "run", "--all", "--n-jobs", "4",
                    "--agent-model", "model-key", "--study-dir", str(root),
                    "--split", "dev", "--max-steps", "50"]


def test_new_run_uses_explicit_worker_count(run_wrapper):
    _, run = run_wrapper
    args, _ = run("--n-jobs", "8")
    assert args.count("--n-jobs") == 1
    assert args[args.index("--n-jobs") + 1] == "8"


@pytest.mark.parametrize("marker", ["study.pkl.gz", "queue.jsonl"])
def test_all_sites_existing_run_resumes_without_overriding_saved_settings(run_wrapper, marker):
    root, run = run_wrapper
    root.mkdir()
    (root / marker).touch()
    args, stderr = run("--split", "dev", "--config-dir", "configs")
    assert args == ["run", "webarena-pro", "run", "--resume-study", str(root)]
    assert "Resuming all-site study" in stderr


def test_filtered_all_sites_resume_preserves_explicit_runtime_overrides(run_wrapper):
    root, run = run_wrapper
    filtered = root / "all_task_1_2"
    filtered.mkdir(parents=True)
    (filtered / "queue.jsonl").touch()
    args, _ = run("--task", "1,2", "--split=dev", "--config-dir=configs",
                  "--n-jobs", "8", "--max-steps=17", "--n-relaunch", "2")
    assert args == ["run", "webarena-pro", "run", "--resume-study", str(filtered),
                    "--n-jobs", "8", "--max-steps=17", "--n-relaunch", "2"]


def test_explicit_resume_does_not_inject_default_step_limit(run_wrapper):
    root, run = run_wrapper
    args, _ = run("--resume-study", str(root))
    assert args == ["run", "webarena-pro", "run", "--agent-model", "model-key",
                    "--resume-study", str(root)]


@pytest.mark.parametrize("target", [[], ["--site", "nextcloud"]])
def test_dry_run_forwards_target_and_does_not_start_workers(run_wrapper, target):
    _, run = run_wrapper
    args, _ = run(*target, "--dry-run", "--task", "172,173")
    assert args == ["run", "webarena-pro", "run", *(target or ["--all"]),
                    "--agent-model", "model-key", "--dry-run", "--task", "172,173",
                    "--max-steps", "50"]


def test_help_is_forwarded_without_default_limits(run_wrapper):
    _, run = run_wrapper
    args, _ = run("--help")
    assert args == ["run", "webarena-pro", "run", "--agent-model", "model-key", "--help"]


@pytest.mark.parametrize("resume", [False, True])
def test_single_site_launch_and_resume_preserve_arguments_and_exit_status(run_wrapper, resume):
    root, run = run_wrapper
    study_dir = root / "nextcloud"
    if resume:
        study_dir.mkdir(parents=True)
        (study_dir / "study.pkl.gz").touch()
    args, _ = run("--site", "nextcloud", "--split", "dev", "--n-jobs", "2", exit_code=7)
    if resume:
        assert args == ["run", "webarena-pro", "run", "--resume-study", str(study_dir),
                        "--n-jobs", "2"]
    else:
        assert args == ["run", "webarena-pro", "run", "--site", "nextcloud",
                        "--agent-model", "model-key", "--study-dir", str(study_dir),
                        "--split", "dev", "--n-jobs", "2", "--max-steps", "50"]


def test_resumed_all_sites_propagates_failure_status(run_wrapper):
    root, run = run_wrapper
    root.mkdir()
    (root / "queue.jsonl").touch()
    args, _ = run(exit_code=1)
    assert "--resume-study" in args


@pytest.mark.parametrize("flags", [
    ("--retry-from-start", "--max-worker-restarts", "0"),
    ("--incomplete-only", "--max-worker-restarts=2"),
])
def test_existing_run_forwards_recovery_policy(run_wrapper, flags):
    root, run = run_wrapper
    root.mkdir()
    (root / "queue.jsonl").touch()
    args, _ = run(*flags)
    assert args == ["run", "webarena-pro", "run", "--resume-study", str(root), *flags]
