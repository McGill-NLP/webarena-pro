from types import SimpleNamespace
import pytest

from webarena_pro_bgym.benchmark import env as env_module
from webarena_pro_bgym.benchmark.env import WebArenaProBrowserEnv, WebArenaProEnv


def _make_env(max_steps: int, steps_taken: int = 0) -> WebArenaProEnv:
    env = WebArenaProEnv.__new__(WebArenaProEnv)
    env.env_args = SimpleNamespace(max_steps=max_steps)
    env.steps_taken = steps_taken
    env.last_step_output = {}
    return env


def test_step_terminates_on_send_msg_to_user(monkeypatch):
    env = _make_env(max_steps=30, steps_taken=5)

    monkeypatch.setattr(
        WebArenaProBrowserEnv,
        "step",
        lambda self, action: ({}, 0.0, False, False, {}),
    )

    _, _, terminated, truncated, _ = WebArenaProEnv.step(
        env, 'send_msg_to_user("final answer")'
    )

    assert terminated is True
    assert truncated is False
    assert env.steps_taken == 6


def test_step_terminates_on_done(monkeypatch):
    env = _make_env(max_steps=30, steps_taken=0)

    monkeypatch.setattr(
        WebArenaProBrowserEnv,
        "step",
        lambda self, action: ({}, 0.0, False, False, {}),
    )

    _, _, terminated, truncated, _ = WebArenaProEnv.step(env, "done()")

    assert terminated is True
    assert truncated is False
    assert env.steps_taken == 1


def test_step_still_truncates_on_max_steps(monkeypatch):
    env = _make_env(max_steps=2, steps_taken=1)

    monkeypatch.setattr(
        WebArenaProBrowserEnv,
        "step",
        lambda self, action: ({}, 0.0, False, False, {}),
    )

    _, _, terminated, truncated, _ = WebArenaProEnv.step(env, "click('a12')")

    assert terminated is False
    assert truncated is True
    assert env.steps_taken == 2


def test_budget_signal_is_cleared_after_step_error_and_reset(monkeypatch):
    env = _make_env(max_steps=1)

    def failed_step(self, action):
        assert self._budget_exhausted is True
        raise RuntimeError("browser unavailable")

    monkeypatch.setattr(WebArenaProBrowserEnv, "step", failed_step)
    with pytest.raises(RuntimeError, match="browser unavailable"):
        env.step("click('save')")
    assert env._budget_exhausted is False
    assert env._budget_checkpoint is False
    assert env.steps_taken == 0

    def reset(self, seed):
        assert self._budget_exhausted is False
        assert self._budget_checkpoint is False
        assert self.last_action is None
        assert self.last_step_output is None
        assert self.steps_taken == 0

    monkeypatch.setattr(WebArenaProBrowserEnv, "reset", reset)
    env.last_action = "done()"
    env._budget_exhausted = True
    env._budget_checkpoint = True
    env.steps_taken = 1
    env.reset()


def test_env_init_drops_raw_page_output_for_old_browsergym(monkeypatch):
    env_args = SimpleNamespace(
        enable_audio=True,
        audio_duration=5.0,
        audio_transcribe=True,
        task_config=object(),
    )
    captured = {}

    def fake_browser_env_init(self, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(
        env_module,
        "_BROWSER_ENV_ACCEPTS_USE_RAW_PAGE_OUTPUT",
        False,
    )
    monkeypatch.setattr(WebArenaProBrowserEnv, "__init__", fake_browser_env_init)

    WebArenaProEnv(env_args, action_mapping=None, use_raw_page_output=True)

    assert "use_raw_page_output" not in captured
    assert captured["action_mapping"] is None
