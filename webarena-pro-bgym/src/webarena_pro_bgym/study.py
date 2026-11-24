from datetime import datetime
from contextlib import contextmanager
from copy import deepcopy
import os
import re
import numpy as np
import traceback
import gzip
import json
import logging
import pickle
import signal
import uuid
from dataclasses import dataclass
from pathlib import Path

from browsergym.experiments.loop import StepInfo, _extract_err_msg, _aggregate_episode_stats
from browsergym.experiments.loop import _send_chat_info, save_package_versions
from browsergym.experiments.loop import _is_debugging
import gymnasium as gym
from browsergym.experiments.benchmark.base import Benchmark
from browsergym.core.env import BrowserEnv
from bgym import DEFAULT_BENCHMARKS

from agentlab.agents.agent_args import AgentArgs, AbstractAgentArgs
from agentlab.analyze import inspect_results
from agentlab.experiments import reproducibility_util as repro
from agentlab.experiments.loop import _move_old_exp
from agentlab.experiments.exp_utils import RESULTS_DIR, add_dependencies
from agentlab.experiments.launch_exp import (
    find_incomplete,
    non_dummy_count,
    run_experiments,
)
from browsergym.core.chat import Chat
from agentlab.experiments.study import Study, EnvArgs, ExpArgs, set_demo_mode, _make_study_name, get_most_recent_study, _convert_env_args

try:
    from agentlab.agents.tapeagent import TapeAgent, save_tape
except ImportError:
    TapeAgent = None

from webarena_pro_bgym.benchmark.env import REPORTING_STEP_BUDGETS, WebArenaProBrowserEnv
from webarena_pro_bgym.agent import configure_media
from webarena_pro_bgym.agentlab_compat import (
    count_message_tokens, count_observation_tokens, normalize_agent_info,
)
from webarena_pro_bgym.step_verifier import dispatch_step
from webarena_pro_bgym.checkpoint import EpisodeCheckpoint
from webarena_pro_bgym.model_requests import EpisodeTrace, write_episode_usage, write_run_usage
from webarena_pro_bgym.benchmark.actions import is_completion_action
from webarena_pro_bgym.utils import has_ungraded_score
from webarena_pro_core.verifier import drain_step_verifiers

SEED_MAX = 2 ^ 32  # arbitrary max value (exclusive), seems large enough

logger = logging.getLogger(__name__)

DEFAULT_OPERATION_TIMEOUT_SECONDS = 10 * 60
DEFAULT_CLOSE_TIMEOUT_SECONDS = 2 * 60
FATAL_WORKER_ERROR_MARKERS = (
    "WebArenaProStepTimeoutError",
    "WebArenaProBrowserCrashError",
    "Selectors.set_test_id_attribute: no running event loop",
    "no running event loop",
)


class _FlushingStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after every emit.

    Python's default StreamHandler.emit does call ``self.flush()`` at the end,
    but when the stream is a block-buffered pipe (e.g. ``sys.stdout`` under
    ``uv run | tee``), nothing actually hits the FIFO until the buffer is
    full. Explicit flush keeps per-step logs visible in real time.
    """

    def emit(self, record):  # noqa: D401
        super().emit(record)
        try:
            self.stream.flush()
        except Exception:
            pass


class WebArenaProStepTimeoutError(BaseException):
    """Abort a task operation without entering transport or provider retries.

    HTTP clients can translate ``TimeoutError`` (also ``socket.timeout``) into
    retryable read errors, and generic ``Exception`` handlers can retry it too.
    The one-shot operation alarm must escape both; only the experiment's run
    and close boundaries handle this control signal and retire the worker.
    """


class WebArenaProFatalWorkerError(RuntimeError):
    """Raised when the current worker process should not run more tasks."""


def is_fatal_worker_error(err_msg: str | None, stack_trace: str | None = None) -> bool:
    text = "\n".join(part for part in (err_msg, stack_trace) if part)
    return any(marker in text for marker in FATAL_WORKER_ERROR_MARKERS)


def _format_timeout_seconds(seconds: float) -> str:
    if seconds.is_integer():
        return str(int(seconds))
    return f"{seconds:.1f}"


@contextmanager
def _wall_clock_timeout(seconds: float | None, label: str):
    if seconds is None or seconds <= 0:
        yield
        return

    sigalrm = getattr(signal, "SIGALRM", None)
    setitimer = getattr(signal, "setitimer", None)
    getitimer = getattr(signal, "getitimer", None)
    if sigalrm is None or setitimer is None or getitimer is None:
        yield
        return

    try:
        previous_handler = signal.getsignal(sigalrm)
        previous_timer = getitimer(signal.ITIMER_REAL)
    except ValueError:
        logger.debug("Skipping wall-clock timeout for %s outside the main thread.", label)
        yield
        return

    def _handle_timeout(_signum, _frame):
        raise WebArenaProStepTimeoutError(
            f"{label} timed out after {_format_timeout_seconds(seconds)}s"
        )

    signal.signal(sigalrm, _handle_timeout)
    setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        setitimer(signal.ITIMER_REAL, 0)
        signal.signal(sigalrm, previous_handler)
        if previous_timer[0] > 0:
            setitimer(signal.ITIMER_REAL, *previous_timer)


def _timeout_from_env(name: str, default: float) -> float | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using default %.1fs", name, raw_value, default)
        return default

    if value <= 0:
        return None
    return value


class WebArenaProStepInfo(StepInfo):
    def make_stats(self):
        # Normalize before any counting can raise, so failure summaries can
        # still attach the original error to AgentInfo returned by the agent.
        self.agent_info = normalize_agent_info(self.agent_info) or {}
        stats = {
            f"n_token_{key}": count_observation_tokens(value)
            for key, value in self.obs.items()
            if isinstance(value, str)
        }
        stats.update(self.agent_info.pop("stats", {}) or {})
        messages = self.agent_info.get("chat_messages")
        if messages is not None:
            stats["n_token_agent_messages"] = count_message_tokens(messages)
        timestamps = self.profiling
        stats["step_elapsed"] = timestamps.env_stop - timestamps.env_start
        stats["agent_elapsed"] = timestamps.agent_stop - timestamps.agent_start
        self.stats = stats

    def save_step_info(self, *args, **kwargs):
        self.agent_info = normalize_agent_info(self.agent_info) or {}
        return super().save_step_info(*args, **kwargs)

    def from_step(self, env: BrowserEnv, action: str, obs_preprocessor: callable):
        # The code below calls env.step(action) which calls env.post_step()
        super().from_step(env, action, obs_preprocessor)

    def from_budget_exhaustion(self, env):
        """Finalize the current step; no browser action or extra step is added."""
        self.reward, self.terminated, self.truncated, info = (
            env.unwrapped.evaluate_budget_exhaustion()
        )
        self.task_info = info.get("task_info")
        self.profiling.validation_start = info.get("validation_start")
        self.profiling.validation_stop = info.get("validation_stop")

@dataclass
class WebArenaProExpArgs(ExpArgs):
    """Arguments to run an experiment, i.e. run agent in an environment until done.

    This dataclass is used to store experiments arguments. It contains
    agent_args and env_args which follows the same principle. It contains helper
    functions to prepare and run experiments.

    Attributes:
    -----------
    agent_args: AbstractAgentArgs
        The arguments to instantiate the agent.
    env_args: EnvArgs
        The arguments to instantiate the environment.
    exp_dir: str
        The directory where the experiment will be saved.
    exp_name: str
        The name of the experiment. If None, it will be generated from the
        agent and environment names.
    enable_debug: bool
        If python is running in debug mode and `enable_debug` is True, errors
        will be raised instead of only logged
    error_msg: str
        Error that occured while running the experiment (if any).
    stack_trace: str
        Stack trace of the error (if any).
    order: int (internal)
        The order of the experiment in the batch. It is used to keep track of
        the original order of the experiments in case they are shuffled.
    """

    agent_args: AbstractAgentArgs
    env_args: EnvArgs
    exp_dir: str = None
    exp_name: str = None
    enable_debug: bool = True
    err_msg: str = None
    stack_trace: str = None
    order: int = None  # use to keep the original order the experiments were meant to be launched.
    logging_level: int = logging.INFO
    logging_level_stdout: int = logging.INFO
    exp_id: str = None
    depends_on: tuple[str] = ()
    save_screenshot: bool = True
    save_som: bool = False
    checkpoint_path: Path | None = None
    resume_requested: bool = False
    resume_from_start: bool = False

    def make_id(self):
        super().make_id()

    def prepare(self, exp_root):
        super().prepare(exp_root)

    def _set_logger(self):
        """Like super()._set_logger() but ALSO ensures a flushing stdout
        StreamHandler, so that ``uv run ... | tee`` / tmux panes see
        per-step progress in real time.

        Agentlab's base ``_set_logger`` removes all pre-existing StreamHandlers
        and adds a new one to ``sys.stderr``. Under ``uv run`` + pipe, that
        stderr stream ends up block-buffered and only flushes at process exit
        or large bursts — panes appear silent for tens of minutes.
        """
        import sys
        super()._set_logger()

        root_logger = logging.getLogger()

        # Avoid stacking duplicates if _set_logger is somehow called twice
        # without _unset_logger in between.
        for h in list(root_logger.handlers):
            if getattr(h, "_wp_stdout", False):
                root_logger.removeHandler(h)

        stdout_handler = _FlushingStreamHandler(sys.stdout)
        stdout_handler._wp_stdout = True  # type: ignore[attr-defined]
        stdout_handler.setLevel(self.logging_level_stdout)
        stdout_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        root_logger.addHandler(stdout_handler)

    def _unset_logger(self):
        # AgentLab removes the handler from the root logger but retains it on
        # ExpArgs. Its RLock prevents subsequent Study.save() and retry prepare()
        # from pickling a completed experiment, and the file remains open.
        handler = getattr(self, "logging_file_handler", None)
        if handler is None:
            return
        try:
            super()._unset_logger()
        finally:
            try:
                handler.close()
            finally:
                del self.logging_file_handler

    def _task_sites_for_cleanup(self) -> tuple[str, ...]:
        task_config = getattr(self.env_args, "task_config", None)
        if task_config is None:
            return ()

        task_sites = getattr(task_config, "sites", None)
        if task_sites:
            return tuple(dict.fromkeys(str(site) for site in task_sites))

        website = getattr(task_config, "website", None)
        if website:
            return (str(website),)

        return ()

    def _stop_selected_site_containers(self) -> None:
        from webarena_pro_bgym.benchmark.container_reset import (
            reset_enabled,
            stop_site,
        )

        if not reset_enabled():
            return

        for site in self._task_sites_for_cleanup():
            stop_site(site)

    @contextmanager
    def _termination_cleanup_handler(self, env_getter, reason_setter):
        previous_handlers: dict[int, object] = {}
        installed_signals: list[int] = []
        handling_signal = False

        def _handle_signal(signum, _frame):
            nonlocal handling_signal

            try:
                signal_name = signal.Signals(signum).name
            except ValueError:
                signal_name = f"signal {signum}"

            reason_setter(f"Received {signal_name}")

            if handling_signal:
                raise KeyboardInterrupt(f"Received {signal_name} during cleanup")
            handling_signal = True

            task_sites = self._task_sites_for_cleanup()
            logger.warning(
                "Received %s while running %s; cleaning up selected site containers: %s",
                signal_name,
                self.env_args.task_name,
                list(task_sites) if task_sites else ["<unknown>"],
            )

            env = env_getter()
            if env is not None:
                try:
                    env.close()
                except Exception:
                    logger.exception(
                        "Failed to close environment while handling %s for %s",
                        signal_name,
                        self.env_args.task_name,
                    )

            try:
                self._stop_selected_site_containers()
            except Exception:
                logger.exception(
                    "Failed to stop selected site containers while handling %s for %s",
                    signal_name,
                    self.env_args.task_name,
                )

            raise KeyboardInterrupt(f"Received {signal_name}")

        for signum in (
            getattr(signal, "SIGTERM", None),
            getattr(signal, "SIGINT", None),
        ):
            if signum is None:
                continue
            try:
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, _handle_signal)
                installed_signals.append(signum)
            except ValueError:
                logger.debug(
                    "Skipping signal cleanup handler registration for %s outside the main thread.",
                    signum,
                )

        try:
            yield
        finally:
            for signum in reversed(installed_signals):
                previous_handler = previous_handlers.get(signum)
                if previous_handler is None:
                    continue
                signal.signal(signum, previous_handler)

    def run(self):
        """Run the experiment and save the results"""
        # start writing logs to run logfile
        self._set_logger()
        self.worker_fatal_error = None

        # log python environment info
        save_package_versions(Path(self.exp_dir))

        episode_info = []
        checkpoint = None
        resumed_decision = False
        agent = None
        env, step_info, err_msg, stack_trace = None, None, None, None
        interruption_reason: dict[str, str | None] = {"value": None}
        reset_timeout = _timeout_from_env(
            "WEBARENA_PRO_RESET_TIMEOUT_SECONDS", DEFAULT_OPERATION_TIMEOUT_SECONDS
        )
        step_timeout = _timeout_from_env(
            "WEBARENA_PRO_STEP_TIMEOUT_SECONDS", DEFAULT_OPERATION_TIMEOUT_SECONDS
        )
        close_timeout = _timeout_from_env(
            "WEBARENA_PRO_CLOSE_TIMEOUT_SECONDS", DEFAULT_CLOSE_TIMEOUT_SECONDS
        )
        try:
            with self._termination_cleanup_handler(
                env_getter=lambda: env,
                reason_setter=lambda reason: interruption_reason.__setitem__("value", reason),
            ):
                logger.info(f"Running experiment {self.exp_name} in:\n  {self.exp_dir}")
                checkpoint = EpisodeCheckpoint.for_experiment(self)
                if checkpoint is not None:
                    if self.resume_requested and not self.resume_from_start:
                        checkpoint.load()
                        if checkpoint.data["phase"] == "finished":
                            EpisodeTrace(self.exp_dir, checkpoint)  # Reattach the saved request artifacts.
                            episode_info = checkpoint.data["episode"]
                            step_info = episode_info[-1]
                            for saved_step in episode_info:
                                deepcopy(saved_step).save_step_info(
                                    self.exp_dir, save_screenshot=self.save_screenshot, save_som=self.save_som
                                )
                            logger.info("Recovered completed episode without repeating agent or grading calls.")
                            return
                        from webarena_pro_bgym.benchmark.container_reset import reset_enabled
                        from webarena_pro_core.state_reset import NOOP_BACKEND, reset_backend_for_site
                        if not reset_enabled() or any(
                            reset_backend_for_site(site) == NOOP_BACKEND for site in _task_sites(self)
                        ):
                            from webarena_pro_bgym.checkpoint import _refuse
                            _refuse("per-task site reset is disabled")
                        os.environ.pop("WP_PREWARMED_TASK_ID", None)
                    else:
                        checkpoint.start()
                trace = EpisodeTrace(self.exp_dir, checkpoint)
                agent = self.agent_args.make_agent()
                if hasattr(agent, "set_task_name"):
                    agent.set_task_name(self.env_args.task_name)

                logger.debug("Agent created.")

                with _wall_clock_timeout(
                    reset_timeout, f"environment creation for {self.env_args.task_name}"
                ):
                    env = self.env_args.make_env(
                        action_mapping=agent.action_set.to_python_code,
                        exp_dir=self.exp_dir,
                        use_raw_page_output=getattr(self.agent_args, "use_raw_page_output", False),
                    )


                logger.debug("Environment created.")
                recovering = (checkpoint is not None and self.resume_requested
                              and not self.resume_from_start and bool(checkpoint.data["episode"]))
                if checkpoint is not None:
                    env.unwrapped._checkpoint_external_call = lambda: checkpoint.mark("external_pending")
                if recovering:
                    env.unwrapped._checkpoint_replay_obs = checkpoint.data["episode"][0].obs
                    env.unwrapped._checkpoint_replaying = True
                step_info = WebArenaProStepInfo(step=0)  # TODO: Use WebSynthStepInfo instead of StepInfo once the former is fixed
                episode_info = [step_info]
                with _wall_clock_timeout(
                    reset_timeout, f"environment reset for {self.env_args.task_name}"
                ):
                    step_info.from_reset(
                        env, seed=self.env_args.task_seed or 0, obs_preprocessor=agent.obs_preprocessor
                    )
                logger.debug("Environment reset.")

                if not hasattr(env.unwrapped, "register_episode_info"):
                    raise ValueError("The environment does not have a register_episode_info method. Make sure you are using the BrowserEnvWebSynth class.")
                env.unwrapped.register_episode_info(episode_info)
                if recovering:
                    episode_info, resumed_decision = checkpoint.restore(
                        env, agent, step_info, step_class=WebArenaProStepInfo,
                        timeout=lambda label: _wall_clock_timeout(step_timeout, label),
                    )
                    step_info = episode_info[-1]
                    for saved_step in episode_info:
                        deepcopy(saved_step).save_step_info(
                            self.exp_dir, save_screenshot=self.save_screenshot, save_som=self.save_som
                        )
                    logger.info("Rebuilt %d completed steps; continuing saved agent history.", step_info.step)
                elif checkpoint is not None:
                    checkpoint.save("ready", episode_info, agent, env)

                while not step_info.is_done:  # set a limit
                    step_info_pre = step_info  # pin obs/agent_info for verifier dispatch
                    logger.debug(f"Starting step {step_info.step}.")
                    if resumed_decision:
                        action = step_info.action
                        resumed_decision = False
                    else:
                        if checkpoint is not None:
                            checkpoint.mark("model_pending")
                        with _wall_clock_timeout(
                            step_timeout, f"agent action for {self.env_args.task_name} step {step_info.step}"
                        ):
                            with trace.step(agent, step_info.step):
                                action = step_info.from_action(agent)
                        if checkpoint is not None:
                            checkpoint.save("action_ready", episode_info, agent, env)
                    logger.debug(f"Agent chose action:\n {action}")

                    # agent_info_dict = {
                    #     "chat_messages": step_info.agent_info.chat_messages.to_openai(),
                    #     "thought": step_info.agent_info.think,
                    #     "action": action,
                    #     "extra_info": step_info.agent_info.extra_info,
                    # }

                    if action is None:
                        # will end the episode after saving the step info.
                        step_info.truncated = True
                        extra_info = (step_info.agent_info or {}).get("extra_info") or {}
                        if extra_info.get("budget_exhausted") is True:
                            if checkpoint is not None:
                                checkpoint.mark("evaluation_pending")
                            with _wall_clock_timeout(
                                step_timeout,
                                f"final budget evaluation for {self.env_args.task_name}",
                            ):
                                step_info.from_budget_exhaustion(env)

                    step_info.save_step_info(
                        self.exp_dir, save_screenshot=self.save_screenshot, save_som=self.save_som
                    )
                    logger.debug("Step info saved.")

                    if hasattr(env.unwrapped, "chat") and isinstance(env.unwrapped.chat, Chat):
                        _send_chat_info(env.unwrapped.chat, action, step_info.agent_info)
                        logger.debug("Chat info sent.")

                    if action is None:
                        if checkpoint is not None:
                            checkpoint.save("finished", episode_info, agent, env)
                        logger.info("Agent returned None action; ending episode.")
                        break

                    action_preview = repr(action)
                    if len(action_preview) > 120:
                        action_preview = action_preview[:117] + "..."
                    logger.info(
                        "step=%d task=%s action=%s",
                        step_info.step,
                        self.env_args.task_name,
                        action_preview,
                    )

                    if checkpoint is not None:
                        phase = "step_pending"
                        if (is_completion_action(action)
                                or (self.env_args.max_steps != -1
                                    and step_info.step + 1 >= self.env_args.max_steps)
                                or step_info.step + 1 in REPORTING_STEP_BUDGETS):
                            phase = "evaluation_pending"
                        elif "transcribe" in action:
                            phase = "external_pending"
                        checkpoint.mark(phase)
                    step_info = WebArenaProStepInfo(step=step_info.step + 1)  # TODO: Use WebSynthStepInfo instead of StepInfo once the former is fixed
                    episode_info.append(step_info)
                    step_info.exp_dir = self.exp_dir

                    with _wall_clock_timeout(
                        step_timeout,
                        f"environment step for {self.env_args.task_name} step {step_info.step}",
                    ):
                        step_info.from_step(env, action, obs_preprocessor=agent.obs_preprocessor)
                    logger.debug("Environment stepped.")
                    if checkpoint is not None:
                        checkpoint.mark("verifier_pending")
                    with _wall_clock_timeout(
                        step_timeout,
                        f"step verifier dispatch for {self.env_args.task_name} step {step_info.step}",
                    ):
                        dispatch_step(step_info_pre, action, step_info)
                        if checkpoint is not None:
                            drain_step_verifiers()
                    if checkpoint is not None:
                        checkpoint.save("finished" if step_info.is_done else "ready", episode_info, agent, env)
                    if step_info.is_done:
                        logger.debug(
                            f"Episode done: terminated: {step_info.terminated}, truncated: {step_info.truncated}."
                        )

        except (Exception, WebArenaProStepTimeoutError) as e:
            if isinstance(e, WebArenaProStepTimeoutError) and step_info is not None:
                try:
                    step_info.truncated = True
                except Exception:
                    logger.debug("Could not mark timed-out step as truncated.", exc_info=True)
            err_msg = f"Exception uncaught by agent or environment in task {self.env_args.task_name}.\n{type(e).__name__}:\n{e}"
            stack_trace = traceback.format_exc()

            self.err_msg = err_msg
            self.stack_trace = stack_trace
            if isinstance(e, WebArenaProStepTimeoutError) or is_fatal_worker_error(
                err_msg, stack_trace
            ):
                self.worker_fatal_error = err_msg

            logger.warning(err_msg + "\n" + stack_trace)
            if _is_debugging() and self.enable_debug:
                logger.warning("Debug mode is enabled. Raising the error.")
                raise

        finally:
            try:
                if step_info is not None:
                    step_info.save_step_info(
                        self.exp_dir, save_screenshot=self.save_screenshot, save_som=self.save_som
                    )
            except Exception as e:
                logger.error(f"Error while saving step info in the finally block: {e}")
            try:
                if not err_msg and interruption_reason["value"] is not None:
                    e = KeyboardInterrupt(interruption_reason["value"])
                    err_msg = f"Exception uncaught by agent or environment in task {self.env_args.task_name}.\n{type(e).__name__}:\n{e}"
                elif (
                    not err_msg
                    and len(episode_info) > 0
                    and not (episode_info[-1].terminated or episode_info[-1].truncated)
                ):
                    e = KeyboardInterrupt("Early termination??")
                    err_msg = f"Exception uncaught by agent or environment in task {self.env_args.task_name}.\n{type(e).__name__}:\n{e}"
                logger.info("Saving experiment info.")
                self.save_summary_info(episode_info, Path(self.exp_dir), err_msg, stack_trace)
                if TapeAgent is not None and isinstance(agent, TapeAgent):
                    task = getattr(env, "task", {})
                    save_tape(self.exp_dir, episode_info, task, agent.final_tape)
            except Exception as e:
                logger.exception(f"Error while saving experiment info: {e}")
            try:
                if env is not None:
                    with _wall_clock_timeout(
                        close_timeout, f"environment close for {self.env_args.task_name}"
                    ):
                        env.close()
            except (Exception, WebArenaProStepTimeoutError) as e:
                close_stack_trace = traceback.format_exc()
                close_msg = f"Error while closing the environment: {e}"
                if not err_msg:
                    self.err_msg = err_msg = close_msg
                    self.stack_trace = stack_trace = close_stack_trace
                    try:
                        self.save_summary_info(episode_info, Path(self.exp_dir), err_msg, stack_trace)
                    except Exception:
                        logger.exception("Could not save environment-close failure in the task summary")
                if isinstance(e, WebArenaProStepTimeoutError) or is_fatal_worker_error(
                    str(e), close_stack_trace
                ):
                    self.worker_fatal_error = close_msg
                logger.exception(f"Error while closing the environment: {e}")
                try:
                    self._stop_selected_site_containers()
                except Exception:
                    logger.exception(
                        "Error while stopping selected site containers after env.close() failed."
                    )
            try:
                self._unset_logger()  # stop writing logs to run logfile
            except Exception as e:
                logger.exception(f"Error while unsetting the logger: {e}")

    def save_summary_info(
        self,
        episode_info: list[WebArenaProStepInfo],
        exp_dir: Path,
        err_msg: str | None,
        stack_trace: str | None,
    ):
        # Also normalize old checkpoints and interrupted steps which have not
        # passed through make_stats/save_step_info yet.
        for step in episode_info:
            step.agent_info = normalize_agent_info(step.agent_info) or {}
        super().save_summary_info(episode_info, exp_dir, err_msg, stack_trace)
        # Preserve cutoff scores separately: summing interim rewards would
        # inflate the final score and lose which budget actually succeeded.
        summary_path = exp_dir / "summary_info.json"
        summary = json.loads(summary_path.read_text())
        # BrowserGym uses nansum, which otherwise turns unpriced native calls
        # into a misleading zero-dollar episode. Preserve missing pricing.
        if any((step.agent_info.get("stats") or {}).get("native_cost_unavailable")
               for step in episode_info):
            summary["cost_available"] = False
            summary["stats.cum_cost"] = None
            summary["stats.max_cost"] = None
        max_steps = getattr(getattr(self, "env_args", None), "max_steps", None)
        budget_scores = {}
        evaluations = []
        for step in episode_info:
            task_info = getattr(step, "task_info", None) or {}
            if task_info.get("dag_evaluated"):
                evaluations.append(step)
            if task_info.get("dag_evaluated") and step.step in REPORTING_STEP_BUDGETS:
                score = float(task_info["score"])
                budget_scores[str(step.step)] = {
                    "score": score, "success": score == 1.0, "evaluated_at_step": step.step,
                }
        terminal_evaluation = False
        if episode_info and max_steps is not None:
            final = episode_info[-1]
            task_info = getattr(final, "task_info", None) or {}
            if (final.is_done and task_info.get("dag_evaluated")
                    and task_info.get("evaluation_trigger") in {
                        "agent_completion", "budget_exhaustion", "early_termination",
                    }):
                terminal_evaluation = True
                score = float(task_info["score"])
                for budget in REPORTING_STEP_BUDGETS:
                    if final.step <= budget and (max_steps == -1 or budget <= max_steps):
                        budget_scores.setdefault(str(budget), {
                            "score": score, "success": score == 1.0, "evaluated_at_step": final.step,
                        })
                if max_steps == -1:
                    budget_scores["unlimited"] = {
                        "score": score, "success": score == 1.0, "evaluated_at_step": final.step,
                    }
        if max_steps is not None:
            summary["max_steps"] = max_steps
            budgets = [budget for budget in REPORTING_STEP_BUDGETS
                       if max_steps == -1 or budget <= max_steps]
            if max_steps == -1:
                budgets.append("unlimited")
            for budget in budgets:
                if str(budget) in budget_scores:
                    continue
                available = [step for step in evaluations
                             if budget == "unlimited" or step.step <= budget]
                previous = available[-1] if available else None
                budget_scores[str(budget)] = {
                    "status": "unavailable",
                    "score": None,
                    "success": None,
                    "evaluated_at_step": None,
                    "reason": ("episode_error" if summary.get("err_msg")
                               else "episode_ended_without_evaluation"),
                    "last_evaluated_score": (float(previous.task_info["score"])
                                             if previous is not None else None),
                    "last_evaluated_at_step": (previous.step if previous is not None else None),
                }
        if evaluations:
            last_evaluation = evaluations[-1]
            # Retain the latest observed score (which may be lower than a prior
            # cutoff). It is not a new terminal grade after a browser failure.
            summary["cum_reward"] = float(last_evaluation.task_info["score"])
            summary["score_provenance"] = {
                "status": "terminal" if terminal_evaluation else "last_evaluation",
                "evaluated_at_step": last_evaluation.step,
                "evaluation_trigger": last_evaluation.task_info.get("evaluation_trigger"),
            }
        summary["step_budget_scores"] = budget_scores
        summary_path.write_text(json.dumps(summary, indent=4))
        # AgentLab's generic summary drops task_info. Keep judge evidence in a
        # portable, private sidecar as well as the compressed step artifacts.
        audits = []
        for index, step in enumerate(episode_info):
            task_info = getattr(step, "task_info", None) or {}
            for node_id, result in (task_info.get("dag_results") or {}).items():
                for audit in result.get("judge_audits", []):
                    audits.append({"step": index, "node_id": node_id, "audit": audit})
        if audits:
            path = exp_dir / "judge_audits.json"
            with open(path, "w", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
                os.chmod(path, 0o600)
                json.dump(audits, output, indent=2, ensure_ascii=False)
        write_episode_usage(exp_dir)



def _task_name(exp_args) -> str:
    env_args = getattr(exp_args, "env_args", None)
    return getattr(env_args, "task_name", "<unknown>")


def _fatal_worker_reason(exp_args) -> str | None:
    reason = getattr(exp_args, "worker_fatal_error", None)
    if reason:
        return str(reason)

    err_msg = getattr(exp_args, "err_msg", None)
    stack_trace = getattr(exp_args, "stack_trace", None)
    if is_fatal_worker_error(err_msg, stack_trace):
        return str(err_msg or "fatal worker error")

    return None


def _task_sites(exp_args) -> tuple[str, ...]:
    env_args = getattr(exp_args, "env_args", None)
    task_config = getattr(env_args, "task_config", None)
    if task_config is None:
        return ()

    sites = getattr(task_config, "sites", None)
    if sites:
        return tuple(dict.fromkeys(str(site) for site in sites))

    website = getattr(task_config, "website", None)
    return (str(website),) if website else ()


def _task_id(exp_args) -> str:
    env_args = getattr(exp_args, "env_args", None)
    task_config = getattr(env_args, "task_config", None)
    task_id = getattr(task_config, "task_id", None)
    return str(task_id if task_id is not None else _task_name(exp_args))


class _SequentialContainerPipeline:
    """Alternate two isolated runtime slots and prepare one task ahead."""

    def __init__(
        self,
        *,
        exp_args_list,
        sites,
        base_slot_index,
        base_slot,
        standby_slot,
        base_env,
        standby_env,
        restore_env,
    ):
        self.exp_args_list = exp_args_list
        self.sites = tuple(sites)
        self.base_slot_index = int(base_slot_index)
        self.base_slot = base_slot
        self.standby_slot = standby_slot
        self.environments = (base_env, standby_env)
        self.restore_env = restore_env
        self.runtime_slots = (
            self.base_slot_index,
            int(standby_slot.worker_index),
        )
        self.prepared_tasks: dict[int, bool] = {}
        self.pending_job = None

    @classmethod
    def create(cls, exp_args_list):
        from webarena_pro_bgym.benchmark.container_reset import reset_enabled
        from webarena_pro_bgym.parallel import (
            ACTIVE_RUNTIME_SLOT_ENV_VAR,
            ReservedWorkerSlot,
            build_worker_environment,
            reassign_worker_environment,
            reserve_worker_slot,
        )
        from webarena_pro_bgym.prewarm import (
            assigned_runtime_slot,
            container_prewarm_enabled,
        )

        if (
            len(exp_args_list) < 2
            or not reset_enabled()
            or not container_prewarm_enabled()
        ):
            return None

        sites = tuple(
            dict.fromkeys(
                site for exp_args in exp_args_list for site in _task_sites(exp_args)
            )
        )
        if not sites:
            return None

        original_env = dict(os.environ)
        base_slot = None
        base_slot_index = assigned_runtime_slot()
        try:
            if base_slot_index is None:
                base_slot = reserve_worker_slot(sites=sites)
                base_slot_index = base_slot.worker_index
            # Queue coordinators reserve both slots before spawning a worker,
            # so they can clean up and release them even if it is killed.
            assigned_standby = os.environ.get("WP_QUEUE_STANDBY_SLOT")
            standby_slot = (
                ReservedWorkerSlot(int(assigned_standby), ())
                if assigned_standby is not None
                else reserve_worker_slot(sites=sites)
            )
        except Exception as error:
            if base_slot is not None:
                base_slot.release()
            logger.warning(
                "Could not reserve runtime slots; continuing without "
                "container prewarming: %s",
                error,
            )
            return None

        if standby_slot.worker_index == base_slot_index:
            standby_slot.release()
            logger.warning(
                "Standby runtime slot w%d matches the active slot; continuing "
                "without container prewarming.",
                base_slot_index,
            )
            return None

        if base_slot is None:
            base_env = dict(original_env)
        else:
            base_env = build_worker_environment(
                sites=sites,
                worker_index=base_slot_index,
                base_env=original_env,
                force_reset_per_task=False,
                set_parallel_worker_index=False,
            )
        base_env[ACTIVE_RUNTIME_SLOT_ENV_VAR] = str(base_slot_index)
        standby_env = reassign_worker_environment(
            sites=sites,
            from_worker_index=base_slot_index,
            to_worker_index=standby_slot.worker_index,
            base_env=base_env,
        )
        logger.info(
            "Enabled one-task-ahead container prewarming with runtime slots "
            "w%d and w%d.",
            base_slot_index,
            standby_slot.worker_index,
        )
        return cls(
            exp_args_list=exp_args_list,
            sites=sites,
            base_slot_index=base_slot_index,
            base_slot=base_slot,
            standby_slot=standby_slot,
            base_env=base_env,
            standby_env=standby_env,
            restore_env=original_env,
        )

    def before_task(self, index: int) -> None:
        from webarena_pro_bgym.parallel import activate_worker_environment
        from webarena_pro_bgym.prewarm import (
            PREWARMED_TASK_ENV_VAR,
            launch_container_prewarm,
        )

        active_position = index % 2
        activate_worker_environment(
            sites=self.sites,
            env=self.environments[active_position],
        )
        os.environ.pop(PREWARMED_TASK_ENV_VAR, None)
        if self.prepared_tasks.pop(index, False):
            os.environ[PREWARMED_TASK_ENV_VAR] = _task_id(
                self.exp_args_list[index]
            )

        next_index = index + 1
        if next_index >= len(self.exp_args_list):
            return

        next_position = next_index % 2
        try:
            self.pending_job = launch_container_prewarm(
                sites=_task_sites(self.exp_args_list[next_index]),
                task_id=_task_id(self.exp_args_list[next_index]),
                runtime_slot=self.runtime_slots[next_position],
                env=self.environments[next_position],
            )
        except Exception:
            self.pending_job = None
            self.prepared_tasks[next_index] = False
            logger.exception(
                "Could not launch container prewarm for task %s; it will be "
                "prepared synchronously.",
                _task_id(self.exp_args_list[next_index]),
            )

    def after_task(self, index: int) -> None:
        next_index = index + 1
        if next_index >= len(self.exp_args_list) or self.pending_job is None:
            return
        try:
            self.prepared_tasks[next_index] = self.pending_job.wait()
        except Exception:
            self.prepared_tasks[next_index] = False
            logger.exception(
                "Container prewarm for task %s failed; it will be prepared "
                "synchronously.",
                _task_id(self.exp_args_list[next_index]),
            )
        finally:
            self.pending_job = None

    def close(self) -> None:
        from webarena_pro_bgym.parallel import activate_worker_environment
        from webarena_pro_bgym.prewarm import (
            PREWARMED_TASK_ENV_VAR,
            cleanup_runtime_containers,
        )

        if self.pending_job is not None:
            try:
                self.pending_job.cancel()
            except Exception:
                logger.exception("Failed to cancel the active container prewarm")
            self.pending_job = None

        try:
            for env in self.environments:
                try:
                    cleanup_runtime_containers(sites=self.sites, env=env)
                except Exception:
                    logger.exception("Failed to clean up a container prewarm slot")
        finally:
            activate_worker_environment(sites=self.sites, env=self.restore_env)
            os.environ.pop(PREWARMED_TASK_ENV_VAR, None)
            self.standby_slot.release()
            if self.base_slot is not None:
                self.base_slot.release()


def _run_experiments_sequential_stop_on_fatal(
    exp_args_list: list[ExpArgs],
    study_dir: Path,
    avg_step_timeout: int,
) -> None:
    if len(exp_args_list) == 0:
        logging.warning("No experiments to run.")
        return

    study_dir = Path(study_dir)
    study_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Saving experiments to %s", study_dir)
    for exp_args in exp_args_list:
        exp_args.agent_args.prepare()
        exp_args.prepare(exp_root=study_dir)

    pipeline = _SequentialContainerPipeline.create(exp_args_list)
    try:
        for index, exp_args in enumerate(exp_args_list):
            if pipeline is not None:
                pipeline.before_task(index)
            exp_args.run()
            fatal_reason = _fatal_worker_reason(exp_args)
            if fatal_reason:
                task_name = _task_name(exp_args)
                raise WebArenaProFatalWorkerError(
                    f"{task_name} left the worker process unsafe for more tasks: "
                    f"{fatal_reason}"
                )
            if pipeline is not None:
                pipeline.after_task(index)
    finally:
        try:
            if pipeline is not None:
                pipeline.close()
        finally:
            logging.info(
                "All jobs are finished. Calling agent_args.close() on all agents..."
            )
            for exp_args in exp_args_list:
                exp_args.agent_args.close()
            logging.info("Experiment finished and saved in %s.", study_dir)


@dataclass
class WebArenaProStudy(Study):
    agent_args: list[AgentArgs] = None
    benchmark: Benchmark | str = None
    dir: Path = None
    suffix: str = ""  # used for adding a personnal comment to the study name
    uuid: str = None
    reproducibility_info: dict = None
    logging_level: int = logging.DEBUG
    logging_level_stdout: int = logging.WARNING
    comment: str = None  # Extra comments from the authors of this study
    ignore_dependencies: bool = False
    avg_step_timeout: int = 60
    demo_mode: bool = False

    def run_queue(self, queue_path: Path, worker_id: str, n_relaunch: int = 1) -> None:
        """Pull tasks as capacity frees up, retaining at most one prewarm claim.

        Worker study metadata contains only its own claims. The coordinator's
        study retains the complete task set for aggregation and manual resume.
        Local relaunches continue compatible checkpoints. Fatal failures are
        recorded before exiting so the coordinator can replace this process
        while keeping the failed task terminal for this invocation.
        """
        from webarena_pro_bgym.prewarm import (
            PREWARMED_TASK_ENV_VAR,
            cleanup_runtime_containers,
        )
        from webarena_pro_bgym.queue_client import QueueClient

        if n_relaunch < 1:
            raise ValueError("n_relaunch must be positive")
        queue = QueueClient.from_environment()
        available = {int(_task_id(exp)): exp for exp in self.exp_args_list}
        all_experiments = list(self.exp_args_list)
        self.exp_args_list = []
        self.set_reproducibility_info(strict_reproducibility=False, comment=self.comment)
        self.save()
        pipeline = None
        used_sites = set()
        try:
            self.benchmark.prepare_backends()
            pipeline = _SequentialContainerPipeline.create(all_experiments)
            if pipeline is not None:
                pipeline.exp_args_list = self.exp_args_list

            def claim(*, lookahead=False):
                task_id = queue.claim(lookahead=lookahead)
                if task_id is None:
                    return None
                exp = available[task_id]
                # A replacement builds fresh experiment arguments. Keep its
                # seed stable instead of AgentLab choosing a new one in prepare.
                if getattr(exp.env_args, "task_seed", None) is None:
                    exp.env_args.task_seed = 0
                row = getattr(queue, "last_claim", None) or {}
                exp.checkpoint_path = Path(queue_path).parent / "tasks" / str(task_id) / "checkpoint.pkl"
                exp.resume_requested = bool(row.get("retry_count"))
                exp.resume_from_start = bool(row.get("full_retry"))
                self.exp_args_list.append(exp)
                self.save()
                return exp

            current = claim()
            index = 0
            while current is not None:
                # Claim only one lookahead, and only when an actual standby
                # runtime is available. Nothing else is reserved in advance.
                next_exp = claim(lookahead=True) if pipeline is not None else None
                if pipeline is not None:
                    pipeline.before_task(index)
                used_sites.update(_task_sites(current))
                try:
                    current.agent_args.prepare()
                    for attempt in range(n_relaunch):
                        current.err_msg = None
                        current.stack_trace = None
                        current.worker_fatal_error = None
                        if attempt:
                            os.environ.pop(PREWARMED_TASK_ENV_VAR, None)
                            current.resume_requested = True
                            current.resume_from_start = False
                        if attempt == 0:
                            # Started means entering experiment preparation.
                            # Persist it before prepare writes exp_args.pkl so
                            # a recovered unstarted claim has no result stub
                            # that could be counted beside its new attempt.
                            queue.started(int(_task_id(current)))
                        current.prepare(exp_root=self.dir)
                        current.run()
                        fatal_reason = _fatal_worker_reason(current)
                        if fatal_reason:
                            current.err_msg = current.err_msg or fatal_reason
                            queue.fail(int(_task_id(current)), current.err_msg)
                            raise WebArenaProFatalWorkerError(
                                f"{_task_name(current)} left the worker unsafe: {fatal_reason}"
                            )
                        # run() can report an early termination only in the
                        # saved summary, or log a failure to write that file.
                        # Neither case should become a successful queue claim.
                        try:
                            summary = json.loads(
                                (Path(current.exp_dir) / "summary_info.json").read_text()
                            )
                            if not isinstance(summary, dict):
                                raise ValueError("task summary must be an object")
                            current.err_msg = current.err_msg or summary.get("err_msg")
                        except (OSError, ValueError, TypeError) as error:
                            current.err_msg = current.err_msg or f"Missing or invalid task summary: {error}"
                        if not current.err_msg:
                            break
                finally:
                    current.agent_args.close()
                if current.err_msg:
                    queue.fail(int(_task_id(current)), current.err_msg)
                else:
                    queue.complete(int(_task_id(current)))
                if pipeline is not None:
                    pipeline.after_task(index)
                current = next_exp if next_exp is not None else claim()
                index += 1
        finally:
            try:
                if pipeline is not None:
                    pipeline.close()
                else:
                    cleanup_runtime_containers(sites=sorted(used_sites), env=os.environ)
            finally:
                try:
                    drain_step_verifiers()
                    if self.exp_args_list:
                        write_run_usage(Path(self.dir))
                        self.get_results(suffix="queue")
                finally:
                    queue.close()
    
    def run(
        self,
        n_jobs=1,
        parallel_backend="sequential",
        strict_reproducibility=False,
        n_relaunch=3,
        relaunch_errors=True,
        exp_root=RESULTS_DIR,
    ):
        self.set_reproducibility_info(
            strict_reproducibility=strict_reproducibility, comment=self.comment
        )
        self.save(exp_root=exp_root)

        n_exp = len(self.exp_args_list)
        last_error_count = None

        for i in range(n_relaunch):
            logger.info(f"Launching study {self.name} - trial {i + 1} / {n_relaunch}")
            self._run(n_jobs, parallel_backend, strict_reproducibility)

            suffix = f"trial_{i + 1}_of_{n_relaunch}"
            _, summary_df, error_report = self.get_results(suffix=suffix)
            logger.info("\n" + str(summary_df))

            n_incomplete, n_error = self.find_incomplete(include_errors=relaunch_errors)

            if n_error / n_exp > 0.3:
                logger.warning("More than 30% of the experiments errored. Stopping the retries.")
                break

            if last_error_count is not None and n_error >= last_error_count:
                logger.warning(
                    "Last trial did not reduce the number of errors. Stopping the retries."
                )
                break

            if n_incomplete == 0:
                logger.info(f"Study {self.name} finished.")
                break

        logger.info("# Error Report:\n-------------\n\n" + error_report)

        if n_incomplete != 0:
            logger.warning(
                f"Study {self.name} did not finish after {n_relaunch} trials. There are {n_incomplete} incomplete experiments."
            )

    def _run(self, n_jobs=1, parallel_backend="joblib", strict_reproducibility=False):
        """Run all experiments in the study in parallel when possible.

        Args:
            n_jobs: int
                Number of parallel jobs.
            parallel_backend: str
                In-process backend to use. Use "sequential" when per-task
                reset is enabled; CLI worker subprocesses provide isolated
                parallelism for reset-enabled runs.
            strict_reproducibility: bool
                If True, all modifications have to be committed before running the experiments.
                Also, if relaunching a study, it will not be possible if the code has changed.

        Raises:
            ValueError: If the exp_args_list is None.
        """

        if self.exp_args_list is None:
            raise ValueError("exp_args_list is None. Please set exp_args_list before running.")

        from webarena_pro_bgym.benchmark.container_reset import reset_enabled

        if reset_enabled() and n_jobs != 1:
            raise ValueError(
                "Per-task container reset is enabled by default, so in-process "
                "parallelism with n_jobs>1 is unsafe. Use n_jobs=1, disable "
                "reset with WP_RESET_CONTAINER_PER_TASK=0, or run through the "
                "CLI with --n-jobs N so worker subprocesses can reserve "
                "isolated containers."
            )

        logger.info("Preparing backends...")
        self.benchmark.prepare_backends()
        logger.info("Backends ready.")

        try:
            if parallel_backend == "sequential":
                _run_experiments_sequential_stop_on_fatal(
                    self.exp_args_list,
                    self.dir,
                    avg_step_timeout=self.avg_step_timeout,
                )
            else:
                run_experiments(
                    n_jobs,
                    self.exp_args_list,
                    self.dir,
                    parallel_backend=parallel_backend,
                    avg_step_timeout=self.avg_step_timeout,
                )
        finally:
            # Block until every registered verifier has caught up on its
            # queued records before we return. AgentLab parallel backends use
            # separate workers with empty registries, so this is a no-op there.
            drain_step_verifiers()
            write_run_usage(Path(self.dir))

    @property
    def name(self):
        agent_names = [a.agent_name for a in self.agent_args]
        return _make_study_name(agent_names, [self.benchmark.name], self.suffix)

    def get_results(self, suffix="", also_save=True):
        paths = self.dir
        if (Path(self.dir) / "queue.jsonl").exists():
            from webarena_pro_bgym.run_eval_cli import current_attempt_summary_paths

            paths = [path.parent for path in current_attempt_summary_paths(self.dir)]
            if not paths:
                return None, None, "No current attempts have saved results."
        result_df = inspect_results.load_result_df(paths)
        error_report = inspect_results.error_report(result_df, max_stack_trace=3, use_log=True)
        # A close timeout can follow a completed grade. Keep that grade in the
        # trace/result table, but count the errored attempt as unsuccessful.
        # AgentLab's summarizer also requires every error's reward to be zero.
        summary_input = result_df.copy()
        if "cum_reward" in summary_input and "err_msg" in summary_input:
            summary_input.loc[summary_input["err_msg"].notna(), "cum_reward"] = 0
        # An agent can stop without an exception or terminal grade. A saved
        # checkpoint remains useful evidence, but cannot pass that episode.
        if "cum_reward" in summary_input and "score_provenance" in summary_input:
            summary_input.loc[summary_input.apply(has_ungraded_score, axis=1), "cum_reward"] = 0
        summary_df = inspect_results.summarize_study(summary_input)
        if also_save:
            label = f"_{suffix}" if suffix else ""
            result_df.to_csv(Path(self.dir) / f"result_df{label}.csv")
            summary_df.to_csv(Path(self.dir) / f"summary_df{label}.csv")
            (Path(self.dir) / f"error_report{label}.md").write_text(error_report)
        return result_df, summary_df, error_report

    def override_max_steps(self, max_steps):
        for exp_args in self.exp_args_list:
            exp_args.env_args.max_steps = max_steps

    @staticmethod
    def load(dir: Path) -> "WebArenaProStudy":
        dir = Path(dir)
        study_path = dir / "study.pkl.gz"
        if not study_path.exists() and dir.is_dir():
            # For backward compatibility
            first_result = next(
                inspect_results.yield_all_exp_results(savedir_base=dir, progress_fn=None)
            )
            benchmark_name = first_result.exp_args.env_args.task_name.split(".")[0]
            agent_args = first_result.exp_args.agent_args
            study = WebArenaProStudy(agent_args=agent_args, benchmark=benchmark_name, dir=dir)
        else:
            with gzip.open(dir / "study.pkl.gz", "rb") as f:
                study = pickle.load(f)  # type: WebArenaProStudy
            study.dir = dir

            # # just a check
            # for i, exp_args in enumerate(study.exp_args_list):
            #     if exp_args.order != i:
            #         logging.warning(f"The order of the experiments is not correct. {exp_args.order} != {i}")

        return study

    @staticmethod
    def load_most_recent(root_dir: Path = None, contains=None) -> "WebArenaProStudy":
        return WebArenaProStudy.load(get_most_recent_study(root_dir, contains=contains))

    def agents_on_benchmark(
        self,
        agents: list[AgentArgs] | AgentArgs,
        benchmark: Benchmark,
        demo_mode=False,
        logging_level: int = logging.INFO,
        logging_level_stdout: int = logging.INFO,
        ignore_dependencies=False,
    ):
        """Run one or multiple agents on a benchmark.

        Args:
            agents: list[AgentArgs] | AgentArgs
                The agent configuration(s) to run.
            benchmark: Benchmark
                The benchmark to run the agents on.
            demo_mode: bool
                If True, the experiments will be run in demo mode.
            logging_level: int
                The logging level for individual jobs.
            logging_level_stdout: int
                The logging level for the stdout.
            ignore_dependencies: bool
                If True, the dependencies will be ignored and all experiments can be run in parallel.

        Returns:
            list[WebSynthExpArgs]: The list of experiments to run.

        Raises:
            ValueError: If multiple agents are run on a benchmark that requires manual reset.
        """

        if not isinstance(agents, (list, tuple)):
            agents = [agents]

        if benchmark.name.startswith("visualwebarena") or benchmark.name.startswith("webarena"):
            if len(agents) > 1:
                raise ValueError(
                    f"Only one agent can be run on {benchmark.name} since the instance requires manual reset after each evaluation."
                )

        for agent in agents:
            agent.set_benchmark(
                benchmark, demo_mode
            )  # the agent can adapt (lightly?) to the benchmark
            configure_media(agent)

        env_args_list = benchmark.env_args_list
        if demo_mode:
            set_demo_mode(env_args_list)

        exp_args_list = []

        for agent in agents:
            for env_args in env_args_list:
                env_args = deepcopy(env_args)
                model_args = getattr(agent, "chat_model_args", None)
                if (getattr(model_args, "audio_support", False)
                        or getattr(model_args, "video_support", False)):
                    # Omni agents explicitly request listen()/watch(); avoid
                    # a separate background STT dependency and misleading captures.
                    env_args.enable_audio = False
                    env_args.audio_transcribe = False
                exp_args = WebArenaProExpArgs(
                    agent_args=agent,
                    env_args=env_args,
                    logging_level=logging_level,
                    logging_level_stdout=logging_level_stdout,
                )
                exp_args_list.append(exp_args)

        for i, exp_args in enumerate(exp_args_list):
            exp_args.order = i

        # not required now, but keeping around if we need it for visualwebareana on joblib
        # _flag_sequential_exp(exp_args_list, benchmark)

        if not ignore_dependencies:
            # populate the depends_on field based on the task dependencies in the benchmark
            exp_args_list = add_dependencies(exp_args_list, benchmark.dependency_graph_over_tasks())
        else:
            logger.warning(
                f"Ignoring dependencies for benchmark {benchmark.name}. This could lead to different results."
            )

        return exp_args_list
