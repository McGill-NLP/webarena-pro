"""Durable, conservative continuation of an agent episode after worker death.

These private pickle files are local run artifacts, just like exp_args.pkl;
never load a checkpoint from an untrusted study. A checkpoint saves decisions,
not a browser snapshot. Continuation reconstructs a fresh reset environment and
checks observations before reusing decisions. Unknown paid-call outcomes fail
closed rather than silently buying a second response.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import fields, is_dataclass
from datetime import date
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import pickle
import re
from urllib.parse import urlsplit

from agentlab.agents.generic_agent.generic_agent import GenericAgent


class CheckpointRecoveryError(RuntimeError):
    """The saved episode cannot safely continue without a deliberate retry."""


def _refuse(reason):
    raise CheckpointRecoveryError(
        f"Cannot continue saved task: {reason}. Use --retry-from-start to deliberately "
        "start a fresh episode (previous model work will be repeated)."
    )


_AGENT_FIELDS = ("seed", "plan", "plan_step", "memories", "thoughts", "actions", "obs_history")
_AMBIGUOUS_PHASES = {"model_pending", "evaluation_pending", "external_pending", "verifier_pending"}
_REPLAY_ACTIONS = {
    "noop", "scroll", "fill", "select_option", "click", "dblclick", "hover", "press",
    "focus", "clear", "drag_and_drop", "upload_file", "tab_close", "tab_focus",
    "new_tab", "go_back", "go_forward", "goto",
    "scroll_at", "mouse_move", "mouse_down", "mouse_up", "mouse_click",
    "mouse_dblclick", "mouse_drag_and_drop", "keyboard_down", "keyboard_up",
    "keyboard_press", "keyboard_type", "keyboard_insert_text",
}


def agent_state(agent):
    # Subclasses can own additional state; accepting them implicitly would lose
    # budget counters/history. Add a reviewed adapter when another agent needs it.
    if type(agent) is not GenericAgent:
        return None
    return deepcopy({name: getattr(agent, name) for name in _AGENT_FIELDS})


def restore_agent(agent, state):
    if type(agent) is not GenericAgent or state is None or set(state) != set(_AGENT_FIELDS):
        _refuse("the agent has no supported state adapter")
    for name, value in state.items():
        setattr(agent, name, deepcopy(value))


def _rewrite(value, substitutions):
    """Rewrite only whole configured origins, including URLs inside observations."""
    if isinstance(value, str):
        for old, new in sorted(substitutions.items(), key=lambda pair: -len(pair[0])):
            value = re.sub(re.escape(old.rstrip("/")) + r"(?=$|[/?#\s'\"<>\)])",
                           lambda _match: new.rstrip("/"), value)
        return value
    if isinstance(value, dict):
        return {key: _rewrite(item, substitutions) for key, item in value.items()}
    if isinstance(value, list):
        return [_rewrite(item, substitutions) for item in value]
    if isinstance(value, tuple):
        return tuple(_rewrite(item, substitutions) for item in value)
    return value


def observation_signature(obs, urls):
    if not isinstance(obs, dict) or not any(obs.get(key) for key in ("axtree_txt", "pruned_html")):
        _refuse("the observation has no stable accessibility tree or HTML")
    # Raw DOM node IDs, profiling and chat timestamps change on reset. Agent-
    # visible DOM/BIDs, focus, tabs, errors and pixels must still agree. We do
    # not fuzzy-match observations or reuse a click against a changed target.
    keys = ("axtree_txt", "pruned_html", "url", "open_pages_urls", "open_pages_titles",
            "active_page_index", "focused_element_bid", "last_action_error")
    values = {key: obs.get(key) for key in keys}
    values = _rewrite(values, {url: f"site://{site}" for site, url in urls.items()})
    screenshot = obs.get("screenshot")
    if screenshot is not None:
        values["pixels"] = hashlib.sha256(screenshot.tobytes()).hexdigest()
        values["shape"] = list(screenshot.shape)
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


def replay_action(action, substitutions, allowed_origins=None):
    """Accept only literal high-level actions; never replay arbitrary Python."""
    try:
        parsed = ast.parse(action)
        if not parsed.body:
            raise ValueError("empty action")
        for statement in parsed.body:
            call = statement.value if isinstance(statement, ast.Expr) else None
            if (not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name)
                    or call.func.id not in _REPLAY_ACTIONS):
                raise ValueError("unsupported action")
            # Uploads reference local files and can change outside the episode.
            if call.func.id == "upload_file":
                raise ValueError("file upload")
            for value in [*call.args, *(keyword.value for keyword in call.keywords)]:
                ast.literal_eval(value)
            if any(keyword.arg is None for keyword in call.keywords):
                raise ValueError("keyword expansion")
            if call.func.id == "goto" and allowed_origins is not None:
                target = (call.args[0] if call.args else
                          next(keyword.value for keyword in call.keywords if keyword.arg == "url"))
                url = ast.literal_eval(target)
                if urlsplit(url).netloc not in allowed_origins:
                    raise ValueError("navigation outside the reset websites")
    except (SyntaxError, ValueError, TypeError, StopIteration):
        _refuse("the saved action is not supported for safe replay")
    return _rewrite(action, substitutions)


class EpisodeCheckpoint:
    def __init__(self, path: Path, identity: str):
        self.path = Path(path)
        self.identity = identity
        self.data = None

    @classmethod
    def for_experiment(cls, exp):
        path = getattr(exp, "checkpoint_path", None)
        if path is None:
            return None
        # Agent args contain configuration, not instantiated API clients. The
        # task config/seed and budget belong to the identity as well.
        def config_value(value):
            if is_dataclass(value):
                return {"type": f"{type(value).__module__}.{type(value).__qualname__}",
                        "fields": {field.name: config_value(getattr(value, field.name))
                                   for field in fields(value)}}
            if isinstance(value, dict):
                return {key: config_value(item) for key, item in value.items()}
            if isinstance(value, (tuple, list)):
                return [config_value(item) for item in value]
            return value

        env_config = config_value(exp.env_args)
        task_config = getattr(exp.env_args, "task_config", None)
        if getattr(task_config, "start_url", None):
            from webarena_pro_core.website_metadata import deployed_website_url
            substitutions = {}
            for site in task_config.sites:
                try:
                    parsed = urlsplit(deployed_website_url(site))
                except KeyError:
                    continue
                substitutions[f"{parsed.scheme}://{parsed.netloc}"] = f"site://{site}"
            # Saved legacy args can retain the old runtime URL. The primary
            # start/login URL is deployment metadata; retain its path/query.
            parsed = urlsplit(task_config.start_url)
            substitutions[f"{parsed.scheme}://{parsed.netloc}"] = f"site://{task_config.website}"
            env_config = _rewrite(env_config, substitutions)
        runtime = (version("agentlab"), version("browsergym-core"))
        payload = (config_value(exp.agent_args), env_config, runtime)
        identity = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return cls(Path(path), identity)

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with open(temporary, "wb", opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
            os.chmod(temporary, 0o600)
            pickle.dump(self.data, output, protocol=pickle.HIGHEST_PROTOCOL)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path)
        descriptor = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def start(self):
        if self.path.exists():
            # Keep old paid work available for inspection after explicit fresh retry.
            import time
            self.path.replace(self.path.with_name(f"checkpoint.previous-{time.time_ns()}.pkl"))
        self.data = {"version": 1, "identity": self.identity, "day": date.today(),
                     "phase": "reset", "episode": [], "agent": None, "urls": {}}
        self.write()

    def load(self):
        if not self.path.exists():
            _refuse("no durable checkpoint exists (older studies cannot restore agent history)")
        try:
            with self.path.open("rb") as source:
                self.data = pickle.load(source)
        except Exception as error:
            _refuse(f"the checkpoint is unreadable: {error}")
        if not isinstance(self.data, dict) or self.data.get("version") != 1:
            _refuse("the checkpoint format is unsupported")
        if self.data.get("identity") != self.identity:
            _refuse("task, agent, model, budget, or runtime configuration changed")
        if self.data.get("phase") == "finished":
            return self.data
        if self.data.get("day") != date.today():
            _refuse("the task execution date changed")
        if self.data.get("phase") in _AMBIGUOUS_PHASES:
            _refuse(f"a paid call may have completed without a durable response ({self.data['phase']})")
        if self.data.get("phase") not in {"reset", "ready", "action_ready", "step_pending"}:
            _refuse("the checkpoint phase is invalid")
        if self.data["episode"] and self.data.get("agent") is None:
            _refuse("the agent has no supported state adapter")
        return self.data

    def mark(self, phase):
        self.data["phase"] = phase
        self.write()

    def save(self, phase, episode, agent, env):
        self.data.update(phase=phase, episode=deepcopy(episode), agent=agent_state(agent),
                         urls=self._task_urls(env))
        self.write()

    @staticmethod
    def _task_urls(env):
        task = env.unwrapped.task
        urls = dict(task.instance.urls)
        sites = getattr(getattr(task, "config", None), "sites", urls)
        return {site: urls[site] for site in sites}

    def restore(self, env, agent, initial_step, *, step_class, timeout):
        """Replay committed browser actions without invoking agent or graders.

        Returns the original episode/stats and whether the last cached decision
        is still to be executed. A partial action is only executed on the newly
        reset baseline, never on the website state left by the old worker.
        """
        data = self.data
        if not data["episode"]:
            return [initial_step], False
        if not getattr(env.unwrapped.task, "checkpoint_reset_verified", False):
            _refuse("the environment did not confirm a fresh per-task site reset")
        from webarena_pro_core.eval.registry import registered_step_verifiers
        if registered_step_verifiers():
            _refuse("custom step verifiers have no checkpoint state adapter")
        old_urls = data["urls"]
        new_urls = self._task_urls(env)
        if set(old_urls) != set(new_urls):
            _refuse("the configured website set changed")
        replacements = {old: new_urls[site] for site, old in old_urls.items()}
        episode = deepcopy(data["episode"])
        # Preflight every replayed action before mutating the freshly reset site.
        origins = {urlsplit(url).netloc for url in old_urls.values()}
        actions = [replay_action(step.action, replacements, origins) for step in episode[:-1]]
        if data["phase"] in {"action_ready", "step_pending"} and episode[-1].action is not None:
            # The pending action is allowed to be a final grading action only
            # in action_ready; step_pending always means a nonterminal action.
            from webarena_pro_bgym.benchmark.actions import is_completion_action
            if not is_completion_action(episode[-1].action):
                replay_action(episode[-1].action, replacements, origins)

        current = initial_step
        env.unwrapped._checkpoint_replaying = True
        try:
            for index, saved in enumerate(episode):
                if observation_signature(current.obs, new_urls) != observation_signature(saved.obs, old_urls):
                    _refuse(f"the rebuilt browser observation diverged at step {index}")
                if index == len(actions):
                    break
                from browsergym.core.chat import Chat
                from browsergym.experiments.loop import _send_chat_info
                if isinstance(getattr(env.unwrapped, "chat", None), Chat):
                    _send_chat_info(env.unwrapped.chat, actions[index], saved.agent_info)
                env.unwrapped._checkpoint_replay_obs = episode[index + 1].obs
                following = step_class(step=index + 1)
                with timeout(f"checkpoint replay step {index + 1}"):
                    following.from_step(env, actions[index], obs_preprocessor=agent.obs_preprocessor)
                current = following
        finally:
            env.unwrapped._checkpoint_replaying = False
            env.unwrapped._checkpoint_replay_obs = None

        for step in episode:
            step.obs = _rewrite(step.obs, replacements)
            step.action = _rewrite(step.action, replacements)
        restore_agent(agent, _rewrite(data["agent"], replacements))
        env.unwrapped.register_episode_info(episode)
        # Fresh env.step calls already restored steps_taken; keep the original
        # artifacts/stats so replay does not replenish the task's step budget.
        return episode, data["phase"] in {"action_ready", "step_pending"}
