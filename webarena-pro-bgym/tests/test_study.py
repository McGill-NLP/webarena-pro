import gzip
import logging
import os
import pickle
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from webarena_pro_bgym.study import (
    WebArenaProExpArgs,
    WebArenaProFatalWorkerError,
    WebArenaProStepTimeoutError,
    WebArenaProStudy,
    _SequentialContainerPipeline,
    _run_experiments_sequential_stop_on_fatal,
    _wall_clock_timeout,
    is_fatal_worker_error,
)


def _make_exp_args(*, sites=("nextcloud",), website="nextcloud"):
    task_config = SimpleNamespace(sites=sites, website=website)
    env_args = SimpleNamespace(task_config=task_config, task_name="webarena-pro-bgym.199")
    return WebArenaProExpArgs(
        agent_args=SimpleNamespace(),
        env_args=env_args,
    )


def _make_study_for_run(exp_args, tmp_path):
    study = WebArenaProStudy.__new__(WebArenaProStudy)
    study.exp_args_list = [exp_args]
    study.benchmark = SimpleNamespace(prepare_backends=lambda: None)
    study.dir = tmp_path
    study.avg_step_timeout = 60
    return study


def test_completed_experiment_can_be_saved_and_prepared_for_retry(tmp_path):
    exp_args = _make_exp_args()
    exp_args.agent_args.agent_name = "fixture"
    exp_args.env_args.task_seed = 0
    exp_args.prepare(tmp_path)
    study = _make_study_for_run(exp_args, tmp_path)
    study.benchmark = SimpleNamespace()
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    try:
        exp_args._set_logger()
        handler = exp_args.logging_file_handler
        exp_args._unset_logger()
        # Real Study.save pickles completed experiments on the next queue claim.
        # AgentLab leaves a FileHandler/RLock on the experiment after a run.
        study.save()
        with gzip.open(tmp_path / "study.pkl.gz", "rb") as saved:
            restored = pickle.load(saved)
        assert restored.exp_args_list[0].exp_dir == exp_args.exp_dir
        assert handler.stream is None
        assert not hasattr(exp_args, "logging_file_handler")
        # Task-local retries pickle the same experiment again in prepare().
        exp_args.prepare(tmp_path)
        with (exp_args.exp_dir / "exp_args.pkl").open("rb") as saved:
            assert pickle.load(saved).exp_id == exp_args.exp_id
    finally:
        for handler in root_logger.handlers[:]:
            if handler not in original_handlers:
                root_logger.removeHandler(handler)
                handler.close()
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)


def test_termination_cleanup_handler_stops_all_cross_site_containers(monkeypatch):
    exp_args = _make_exp_args(sites=("nextcloud", "mattermost"))
    closed = []
    stopped_sites = []
    reason = {}

    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.container_reset.reset_enabled",
        lambda: True,
    )
    monkeypatch.setenv("WP_RESET_BACKEND", "container")
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.stop_site_container",
        lambda site: stopped_sites.append(site),
    )

    env = SimpleNamespace(close=lambda: closed.append("closed"))
    previous_sigterm_handler = signal.getsignal(signal.SIGTERM)

    with pytest.raises(KeyboardInterrupt, match="Received SIGTERM"):
        with exp_args._termination_cleanup_handler(
            env_getter=lambda: env,
            reason_setter=lambda value: reason.update(value=value),
        ):
            handler = signal.getsignal(signal.SIGTERM)
            handler(signal.SIGTERM, None)

    assert closed == ["closed"]
    assert stopped_sites == ["nextcloud", "mattermost"]
    assert reason["value"] == "Received SIGTERM"
    assert signal.getsignal(signal.SIGTERM) is previous_sigterm_handler


def test_is_fatal_worker_error_matches_timeout_and_playwright_loop_errors():
    assert is_fatal_worker_error("WebArenaProStepTimeoutError: timed out")
    assert is_fatal_worker_error("RuntimeError: no running event loop")
    assert not is_fatal_worker_error("ValueError: invalid action")


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="requires SIGALRM")
def test_step_alarm_during_http_read_escapes_openai_retries(monkeypatch):
    import httpx
    from httpcore._backends.sync import SyncStream
    from openai import OpenAI

    requests = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            requests.append(self.path)
            if len(requests) == 1:
                # Keep the first response pending past the operation deadline.
                # A swallowed alarm would let the SDK retry and get HTTP 200.
                release.wait(5)
            body = b'{"id":"fixture","choices":[{"message":{"role":"assistant","content":"retried"}}]}'
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    previous_handler = signal.getsignal(signal.SIGALRM)
    read = SyncStream.read
    first_read = True

    def read_with_deadline(self, *args, **kwargs):
        nonlocal first_read
        if first_read:
            first_read = False
            # Arm at the actual socket read, after the SDK's lazy imports, so
            # the alarm exercises HTTPcore's timeout translation reliably.
            with _wall_clock_timeout(0.5, "provider read"):
                return read(self, *args, **kwargs)
        return read(self, *args, **kwargs)

    monkeypatch.setattr(SyncStream, "read", read_with_deadline)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with OpenAI(
            api_key="fixture",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            http_client=httpx.Client(timeout=2, trust_env=False),
            max_retries=1,
        ) as client:
            with pytest.raises(WebArenaProStepTimeoutError, match="provider read timed out"):
                try:
                    client.chat.completions.create(
                        model="fixture", messages=[{"role": "user", "content": "hello"}],
                    )
                except Exception as error:
                    pytest.fail(f"Operation deadline reached a generic retry handler: {error!r}")
        assert requests == ["/v1/chat/completions"]
        assert signal.getsignal(signal.SIGALRM) is previous_handler
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_result_summary_handles_close_error_without_discarding_saved_grade(tmp_path, monkeypatch):
    import pandas as pd

    raw = pd.DataFrame({
        "cum_reward": [1.0], "err_msg": ["Environment close timed out"],
        "terminated": [True], "truncated": [False], "n_steps": [3],
    }, index=pd.MultiIndex.from_tuples([("webarena-pro-bgym.1", "fixture")],
                                       names=["env.task_name", "agent.agent_name"]))
    monkeypatch.setattr("webarena_pro_bgym.study.inspect_results.load_result_df", lambda paths: raw)
    monkeypatch.setattr("webarena_pro_bgym.study.inspect_results.error_report", lambda *args, **kwargs: "error")
    study = WebArenaProStudy.__new__(WebArenaProStudy)
    study.dir = tmp_path
    results, summary, _ = study.get_results(also_save=False)
    assert results["cum_reward"].iloc[0] == 1
    assert summary["avg_reward"].iloc[0] == 0
    assert summary["n_err"].iloc[0] == 1


def test_sequential_runner_stops_after_fatal_worker_error(tmp_path):
    events = []

    class AgentArgs:
        def __init__(self, name):
            self.name = name

        def prepare(self):
            events.append(f"prepare-agent-{self.name}")

        def close(self):
            events.append(f"close-agent-{self.name}")

    class ExpArgs:
        def __init__(self, name, err_msg=None):
            self.agent_args = AgentArgs(name)
            self.env_args = SimpleNamespace(task_name=name)
            self.err_msg = None
            self.stack_trace = None
            self._err_msg = err_msg

        def prepare(self, exp_root):
            events.append(f"prepare-{self.env_args.task_name}")

        def run(self):
            events.append(f"run-{self.env_args.task_name}")
            if self._err_msg:
                self.err_msg = self._err_msg

    exp_args = [
        ExpArgs("webarena-pro-bgym.1", "RuntimeError: no running event loop"),
        ExpArgs("webarena-pro-bgym.2"),
    ]

    with pytest.raises(WebArenaProFatalWorkerError):
        _run_experiments_sequential_stop_on_fatal(exp_args, tmp_path, avg_step_timeout=60)

    assert "run-webarena-pro-bgym.1" in events
    assert "run-webarena-pro-bgym.2" not in events
    assert "close-agent-webarena-pro-bgym.1" in events
    assert "close-agent-webarena-pro-bgym.2" in events


def test_sequential_runner_prewarms_one_task_ahead_and_alternates_slots(
    monkeypatch, tmp_path
):
    from webarena_pro_bgym.parallel import build_worker_environment

    events = []
    monkeypatch.setenv("WP_ACTIVE_RUNTIME_SLOT", "0")
    base_env = build_worker_environment(
        sites=["mattermost"], worker_index=0, base_env=dict(os.environ)
    )
    base_env.pop("WP_PARALLEL_WORKER_INDEX", None)
    base_env["WP_ASSIGNED_RUN_SLOT"] = "0"
    for key, value in base_env.items():
        monkeypatch.setenv(key, value)

    class Slot:
        worker_index = 1

        def release(self):
            events.append("release-standby")

    class Job:
        def __init__(self, task_id):
            self.task_id = task_id

        def wait(self):
            events.append(f"wait-{self.task_id}")
            return True

        def cancel(self):
            events.append(f"cancel-{self.task_id}")

    class AgentArgs:
        def prepare(self):
            pass

        def close(self):
            pass

    class ExpArgs:
        def __init__(self, task_id):
            self.agent_args = AgentArgs()
            self.env_args = SimpleNamespace(
                task_name=f"webarena-pro-bgym.{task_id}",
                task_config=SimpleNamespace(
                    task_id=str(task_id),
                    sites=("mattermost",),
                    website="mattermost",
                ),
            )
            self.err_msg = None
            self.stack_trace = None

        def prepare(self, exp_root):
            pass

        def run(self):
            events.append(
                (
                    f"run-{self.env_args.task_config.task_id}",
                    os.environ.get("WP_ACTIVE_RUNTIME_SLOT"),
                    os.environ.get("WP_PREWARMED_TASK_ID"),
                )
            )

    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.container_reset.reset_enabled", lambda: True
    )
    monkeypatch.setattr(
        "webarena_pro_bgym.parallel.reserve_worker_slot", lambda **kwargs: Slot()
    )

    def launch(**kwargs):
        events.append(
            f"launch-{kwargs['task_id']}-slot{kwargs['runtime_slot']}"
        )
        return Job(kwargs["task_id"])

    monkeypatch.setattr(
        "webarena_pro_bgym.prewarm.launch_container_prewarm", launch
    )
    monkeypatch.setattr(
        "webarena_pro_bgym.prewarm.cleanup_runtime_containers",
        lambda **kwargs: events.append(
            f"cleanup-slot{kwargs['env']['WP_ACTIVE_RUNTIME_SLOT']}"
        ),
    )

    _run_experiments_sequential_stop_on_fatal(
        [ExpArgs("1"), ExpArgs("2"), ExpArgs("3")],
        tmp_path,
        avg_step_timeout=60,
    )

    assert events[:7] == [
        "launch-2-slot1",
        ("run-1", "0", None),
        "wait-2",
        "launch-3-slot0",
        ("run-2", "1", "2"),
        "wait-3",
        ("run-3", "0", "3"),
    ]
    assert events[-3:] == [
        "cleanup-slot0",
        "cleanup-slot1",
        "release-standby",
    ]


def test_container_pipeline_owns_and_restores_slots_without_cli_assignment(
    monkeypatch
):
    released = []

    class Slot:
        def __init__(self, worker_index):
            self.worker_index = worker_index

        def release(self):
            released.append(self.worker_index)

    slots = iter((Slot(2), Slot(5)))
    monkeypatch.delenv("WP_ACTIVE_RUNTIME_SLOT", raising=False)
    monkeypatch.delenv("WP_ASSIGNED_RUN_SLOT", raising=False)
    monkeypatch.delenv("WP_PARALLEL_WORKER_INDEX", raising=False)
    monkeypatch.delenv("WP_MATTERMOST_URL", raising=False)
    monkeypatch.delenv("WP_MATTERMOST_CONTAINER_NAME", raising=False)
    monkeypatch.delenv("WP_MATTERMOST_HOST_PORT", raising=False)
    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.container_reset.reset_enabled", lambda: True
    )
    monkeypatch.setattr(
        "webarena_pro_bgym.parallel.reserve_worker_slot",
        lambda **kwargs: next(slots),
    )
    monkeypatch.setattr(
        "webarena_pro_bgym.prewarm.cleanup_runtime_containers", lambda **kwargs: None
    )

    class Job:
        def cancel(self):
            pass

    monkeypatch.setattr(
        "webarena_pro_bgym.prewarm.launch_container_prewarm",
        lambda **kwargs: Job(),
    )

    exp_args = [
        SimpleNamespace(
            env_args=SimpleNamespace(
                task_name=f"webarena-pro-bgym.{task_id}",
                task_config=SimpleNamespace(
                    task_id=task_id,
                    sites=("mattermost",),
                    website="mattermost",
                ),
            )
        )
        for task_id in ("1", "2")
    ]

    pipeline = _SequentialContainerPipeline.create(exp_args)
    assert pipeline is not None
    assert pipeline.runtime_slots == (2, 5)
    pipeline.before_task(0)
    assert os.environ["WP_ACTIVE_RUNTIME_SLOT"] == "2"
    pipeline.close()

    assert released == [5, 2]
    assert "WP_ACTIVE_RUNTIME_SLOT" not in os.environ
    assert "WP_MATTERMOST_URL" not in os.environ


def test_study_run_blocks_ray_parallel_with_reset(monkeypatch, tmp_path):
    exp_args = _make_exp_args(sites=("mattermost",), website="mattermost")
    study = _make_study_for_run(exp_args, tmp_path)

    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.container_reset.reset_enabled",
        lambda: True,
    )

    with pytest.raises(ValueError, match="worker subprocesses"):
        study._run(n_jobs=3, parallel_backend="ray")


def test_study_run_still_blocks_joblib_parallel_with_reset(monkeypatch, tmp_path):
    exp_args = _make_exp_args(sites=("mattermost",), website="mattermost")
    study = _make_study_for_run(exp_args, tmp_path)

    monkeypatch.setattr(
        "webarena_pro_bgym.benchmark.container_reset.reset_enabled",
        lambda: True,
    )

    with pytest.raises(ValueError, match="worker subprocesses"):
        study._run(n_jobs=2, parallel_backend="joblib")
