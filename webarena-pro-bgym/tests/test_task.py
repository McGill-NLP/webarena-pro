import logging
import os

import pytest

from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig, load_task_configs


class DummyPage:
	def __init__(self) -> None:
		self.last_url = None
		self.url = "about:blank"

	def goto(self, url: str, timeout: int | None = None, **kwargs) -> None:
		self.last_url = url
		self.url = url

	def on(self, event: str, handler) -> None:
		# No-op; task.setup attaches a download listener on real Playwright pages.
		return None


def test_task_setup_uses_hardcoded_deployed_url(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	config = WebArenaProTaskConfig(
		task_id="task-1",
		intent="Find document",
		sites=("nextcloud",),
		evaluation=None,
		container_name="webarena-pro-task-1-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		startup_wait_seconds=1.0,
	)
	observed_sleeps = []
	monkeypatch.setattr("webarena_pro_bgym.benchmark.task.time.sleep", lambda seconds: observed_sleeps.append(seconds))
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: None,
	)

	task = WebArenaProTask(seed=0, config=config)
	page = DummyPage()
	goal, info = task.setup(page)

	assert goal.startswith("Find document")
	assert "Available websites for this task:" in goal
	assert f"- nextcloud: {DEPLOYED_WEBSITE_URLS['nextcloud']}" in goal
	assert "mattermost" not in goal
	assert info["task_id"] == "task-1"
	assert info["website"] == "nextcloud"
	assert page.last_url == DEPLOYED_WEBSITE_URLS["nextcloud"]
	assert info["start_url"] == DEPLOYED_WEBSITE_URLS["nextcloud"]
	assert observed_sleeps == [config.startup_wait_seconds]


def test_task_teardown_is_noop(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	config = WebArenaProTaskConfig(
		task_id="task-1",
		intent="Find document",
		sites=("nextcloud",),
		evaluation=None,
		container_name="webarena-pro-task-1-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
	)

	task = WebArenaProTask(seed=0, config=config)

	assert task.teardown() is None


def test_task_teardown_stops_container_when_reset_enabled(monkeypatch):
	monkeypatch.delenv("WP_RESET_CONTAINER_PER_TASK", raising=False)
	monkeypatch.setenv("WP_RESET_BACKEND", "container")
	stopped_sites = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.stop_site_container",
		lambda site: stopped_sites.append(site),
	)

	config = WebArenaProTaskConfig(
		task_id="task-teardown",
		intent="Finish task",
		sites=("nextcloud",),
		evaluation=None,
		container_name="webarena-pro-task-teardown-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
	)

	task = WebArenaProTask(seed=0, config=config)
	task.teardown()

	assert stopped_sites == ["nextcloud"]


def test_task_teardown_stops_all_selected_site_containers(monkeypatch):
	monkeypatch.delenv("WP_RESET_CONTAINER_PER_TASK", raising=False)
	monkeypatch.setenv("WP_RESET_BACKEND", "container")
	stopped_sites = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.stop_site_container",
		lambda site: stopped_sites.append(site),
	)

	config = WebArenaProTaskConfig(
		task_id="task-teardown-cross-site",
		intent="Finish task",
		sites=("nextcloud", "mattermost"),
		evaluation=None,
		container_name="webarena-pro-task-teardown-cross-site-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
	)

	task = WebArenaProTask(seed=0, config=config)
	task.teardown()

	assert stopped_sites == ["nextcloud", "mattermost"]


def test_task_config_from_raw_task_uses_hardcoded_start_url():

	raw_task = {
		"task_id": "task-3",
		"intent": "Open app",
		"website": "nextcloud",
		"eval": {
			"eval_types": ["string_match"],
			"reference_answers": {"exact_match": ""},
		},
	}

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task=raw_task,
		container_name="webarena-pro-task-3-0",
	)

	assert config.start_url == DEPLOYED_WEBSITE_URLS["nextcloud"]


def test_task_config_from_raw_task_supports_wait_override(monkeypatch):
	raw_task = {
		"task_id": "task-4",
		"intent": "Open app",
		"website": "nextcloud",
		"eval": {
			"eval_types": ["string_match"],
			"reference_answers": {"exact_match": ""},
		},
		"startup_wait_seconds": 5,
	}

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task=raw_task,
		container_name="webarena-pro-task-4-0",
	)

	assert config.startup_wait_seconds == 5.0


def test_task_config_from_raw_task_uses_fixed_login_url(monkeypatch):
	raw_task = {
		"task_id": "task-5",
		"intent": "Login first",
		"website": "nextcloud",
		"eval": {
			"eval_types": ["string_match"],
			"reference_answers": {"exact_match": ""},
		},
		"require_login": True,
		"login_page": "http://localhost:9999/login",
	}

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task=raw_task,
		container_name="webarena-pro-task-5-0",
	)

	assert config.require_login is True
	assert config.login_page == f"{DEPLOYED_WEBSITE_URLS['nextcloud']}/login"


def test_task_setup_calls_ui_login_when_required(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	config = WebArenaProTaskConfig(
		task_id="task-6",
		intent="Do task",
		sites=("nextcloud",),
		evaluation=None,
		container_name="webarena-pro-task-6-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		require_login=True,
		startup_wait_seconds=1.0,
	)
	observed_sleeps = []
	call_order = []
	monkeypatch.setattr("webarena_pro_bgym.benchmark.task.time.sleep", lambda seconds: observed_sleeps.append(seconds))
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: call_order.append(("wait", site)),
	)
	monkeypatch.setattr(
		"webarena_pro_bgym.benchmark.task.WebArenaProInstance.ui_login",
		lambda self, site, page, username=None: call_order.append(("login", site, username)),
	)

	task = WebArenaProTask(seed=0, config=config)
	page = DummyPage()
	goal, info = task.setup(page)

	assert goal.startswith("Do task")
	assert "Available websites for this task:" in goal
	assert f"- nextcloud: {DEPLOYED_WEBSITE_URLS['nextcloud']}" in goal
	assert "mattermost" not in goal
	assert info["start_url"] == DEPLOYED_WEBSITE_URLS["nextcloud"]
	assert observed_sleeps == [config.startup_wait_seconds]
	assert call_order == [("wait", "nextcloud"), ("login", "nextcloud", None)]
	assert page.last_url == DEPLOYED_WEBSITE_URLS["nextcloud"]


@pytest.mark.parametrize("task_id", ["050", "056"])
@pytest.mark.parametrize("reset_enabled", [False, True])
def test_firefly_task_setup_logs_in_before_agent_navigation(monkeypatch, task_id, reset_enabled):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1" if reset_enabled else "0")
	monkeypatch.delenv("WP_PREWARMED_TASK_ID", raising=False)
	monkeypatch.setenv("WP_FIREFLY_URL", "http://firefly--w7.localhost:8080")
	calls = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.reset_site",
		lambda site: calls.append(("reset", site)),
	)
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: calls.append(("wait", site)),
	)
	monkeypatch.setattr(
		"webarena_pro_bgym.benchmark.task.WebArenaProInstance.ui_login",
		lambda self, site, page, username=None: calls.append(("login", site, username)),
	)
	config = next(task for task in load_task_configs(split="test") if task.task_id == task_id)
	task = WebArenaProTask(seed=0, config=config)

	class RecordingPage(DummyPage):
		def goto(self, url, **kwargs):
			calls.append(("goto", url))
			super().goto(url, **kwargs)

	# Each fresh browser session must log in, including a subsequent episode/reset.
	for _ in range(2):
		calls.clear()
		goal, info = task.setup(RecordingPage())
		assert calls == [
			("reset" if reset_enabled else "wait", "firefly"),
			("login", "firefly", "test@example.com"),
			("goto", "http://firefly--w7.localhost:8080"),
		]
		assert goal.startswith(config.intent)
		assert info["task_id"] == task_id


def test_task_setup_logs_worker_container_lifecycle(monkeypatch, caplog):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
	monkeypatch.setenv("WP_RESET_BACKEND", "container")
	monkeypatch.setenv("WP_PARALLEL_WORKER_INDEX", "0")
	monkeypatch.setenv("WP_EXP_HASH", "w0")
	monkeypatch.setenv("WP_MATTERMOST_CONTAINER_NAME", "mattermost-w0")
	monkeypatch.setenv(
		"WP_MATTERMOST_URL",
		"http://mattermost--w0.localhost:8080",
	)
	reset_sites = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.reset_site",
		lambda site: reset_sites.append(site),
	)

	config = WebArenaProTaskConfig(
		task_id="task-worker-logs",
		intent="Do task",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-worker-logs-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
	)

	task = WebArenaProTask(seed=0, config=config)
	with caplog.at_level(logging.INFO, logger="webarena_pro_bgym.benchmark.task"):
		task.setup(DummyPage())

	assert reset_sites == ["mattermost"]
	assert (
		"worker 0: starting container for mattermost "
		"(mattermost-w0) at http://mattermost--w0.localhost:8080"
		in caplog.text
	)
	assert (
		"worker 0: container ready for mattermost "
		"(mattermost-w0) at http://mattermost--w0.localhost:8080"
		in caplog.text
	)


def test_task_setup_consumes_matching_prewarm_without_reset(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
	monkeypatch.setenv("WP_PREWARMED_TASK_ID", "task-prewarmed")
	reset_sites = []
	ready_sites = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.reset_site",
		lambda site: reset_sites.append(site),
	)
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: ready_sites.append(site),
	)

	config = WebArenaProTaskConfig(
		task_id="task-prewarmed",
		intent="Use the ready site",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-prewarmed-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
	)

	WebArenaProTask(seed=0, config=config).setup(DummyPage())

	assert reset_sites == []
	assert ready_sites == ["mattermost"]
	assert "WP_PREWARMED_TASK_ID" not in os.environ


def test_task_setup_ignores_stale_prewarm_marker(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
	monkeypatch.setenv("WP_PREWARMED_TASK_ID", "different-task")
	reset_sites = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.reset_site",
		lambda site: reset_sites.append(site),
	)

	config = WebArenaProTaskConfig(
		task_id="current-task",
		intent="Use a freshly reset site",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-current-task-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
	)

	WebArenaProTask(seed=0, config=config).setup(DummyPage())

	assert reset_sites == ["mattermost"]
	assert "WP_PREWARMED_TASK_ID" not in os.environ


def test_task_setup_uses_legacy_login_username(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	config = WebArenaProTaskConfig(
		task_id="task-legacy-login-user",
		intent="Do task",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-legacy-login-user-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
		require_login=True,
		login_username="jane.smith",
	)
	call_order = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: None,
	)
	monkeypatch.setattr(
		"webarena_pro_bgym.benchmark.task.WebArenaProInstance.ui_login",
		lambda self, site, page, username=None: call_order.append(("login", site, username)),
	)

	task = WebArenaProTask(seed=0, config=config)
	task.setup(DummyPage())

	assert call_order == [("login", "mattermost", "jane.smith")]


def test_task_setup_logs_into_all_selected_sites(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	config = WebArenaProTaskConfig(
		task_id="task-cross-site-login",
		intent="Use both apps",
		sites=("nextcloud", "mattermost"),
		evaluation=None,
		container_name="webarena-pro-task-cross-site-login-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		require_login=True,
		login_usernames={"nextcloud": "daniel.brooks", "mattermost": "admin"},
	)
	call_order = []
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: call_order.append(("wait", site)),
	)
	monkeypatch.setattr(
		"webarena_pro_bgym.benchmark.task.WebArenaProInstance.ui_login",
		lambda self, site, page, username=None: call_order.append(("login", site, username)),
	)

	task = WebArenaProTask(seed=0, config=config)
	page = DummyPage()
	goal, info = task.setup(page)

	assert "Available websites for this task:" in goal
	assert f"- nextcloud: {DEPLOYED_WEBSITE_URLS['nextcloud']}" in goal
	assert f"- mattermost: {DEPLOYED_WEBSITE_URLS['mattermost']}" in goal
	assert info["sites"] == ["nextcloud", "mattermost"]
	assert info["website_urls"] == {
		"nextcloud": DEPLOYED_WEBSITE_URLS["nextcloud"],
		"mattermost": DEPLOYED_WEBSITE_URLS["mattermost"],
	}
	assert call_order == [
		("wait", "nextcloud"),
		("wait", "mattermost"),
		("login", "nextcloud", "daniel.brooks"),
		("login", "mattermost", "admin"),
	]
	assert page.last_url == DEPLOYED_WEBSITE_URLS["nextcloud"]


def test_task_setup_prompts_with_worker_runtime_urls(monkeypatch):
	monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
	monkeypatch.setenv("WP_NEXTCLOUD_URL", "http://localhost:4100")
	monkeypatch.setenv("WP_MATTERMOST_URL", "http://localhost:4101")
	monkeypatch.setattr(
		"webarena_pro_core.state_reset.wait_until_site_ready",
		lambda site: None,
	)

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task={
			"task_id": "task-worker-runtime-urls",
			"intent": "Use the selected websites",
			"sites": ["nextcloud", "mattermost"],
		},
		container_name="webarena-pro-task-worker-runtime-urls-0",
	)

	task = WebArenaProTask(seed=0, config=config)
	page = DummyPage()
	goal, info = task.setup(page)

	assert "- nextcloud: http://localhost:4100" in goal
	assert "- mattermost: http://localhost:4101" in goal
	assert "metabase" not in goal
	assert info["start_url"] == "http://localhost:4100"
	assert info["website_urls"] == {
		"nextcloud": "http://localhost:4100",
		"mattermost": "http://localhost:4101",
	}
	assert page.last_url == "http://localhost:4100"


def test_task_config_from_raw_task_supports_login_username_selection():
	raw_task = {
		"task_id": "task-login-user",
		"intent": "Login as a chosen user",
		"website": "mattermost",
		"eval": {
			"eval_types": ["string_match"],
			"reference_answers": {"exact_match": ""},
		},
		"require_login": True,
		"login_username": "jane.smith",
	}

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task=raw_task,
		container_name="webarena-pro-task-login-user-0",
	)

	assert config.login_username == "jane.smith"


def test_task_config_from_raw_task_supports_login_usernames_per_site():
	raw_task = {
		"task_id": "task-cross-site-login-users",
		"intent": "Use both apps",
		"sites": ["nextcloud", "mattermost"],
		"eval": {
			"eval_types": ["string_match"],
			"reference_answers": {"exact_match": ""},
		},
		"require_login": True,
		"login_usernames": {
			"nextcloud": "daniel.brooks",
			"mattermost": "admin",
		},
	}

	config = WebArenaProTaskConfig.from_raw_task(
		raw_task=raw_task,
		container_name="webarena-pro-task-cross-site-login-users-0",
	)

	assert config.website == "nextcloud"
	assert config.sites == ("nextcloud", "mattermost")
	assert config.login_username == "daniel.brooks"
	assert config.login_usernames == {
		"nextcloud": "daniel.brooks",
		"mattermost": "admin",
	}


def test_task_config_rejects_legacy_website_that_conflicts_with_sites():
	raw_task = {
		"task_id": "task-conflicting-website",
		"intent": "Use both apps",
		"website": "mattermost",
		"sites": ["nextcloud", "mattermost"],
	}

	with pytest.raises(ValueError, match="must match the first"):
		WebArenaProTaskConfig.from_raw_task(
			raw_task=raw_task,
			container_name="webarena-pro-task-conflicting-website-0",
		)


def test_task_config_rejects_login_usernames_for_unselected_sites():
	raw_task = {
		"task_id": "task-cross-site-login-users",
		"intent": "Use both apps",
		"sites": ["nextcloud"],
		"login_usernames": {
			"mattermost": "admin",
		},
	}

	with pytest.raises(ValueError, match="not listed in `sites`"):
		WebArenaProTaskConfig.from_raw_task(
			raw_task=raw_task,
			container_name="webarena-pro-task-cross-site-login-users-0",
		)


def test_resolve_login_credentials_by_username():
	config = WebArenaProTaskConfig(
		task_id="task-login-username",
		intent="Login as chosen username",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-login-username-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
		require_login=True,
		login_username="jane.smith",
	)

	task = WebArenaProTask(seed=0, config=config)
	username, password = task.instance._auto_login.resolve_credentials(
		site=config.website, username=config.login_username
	)

	assert username == "jane.smith"
	assert password == "User@Secure123"


def test_resolve_login_credentials_raises_for_missing_username():
	config = WebArenaProTaskConfig(
		task_id="task-login-missing-username",
		intent="Login without username",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-login-missing-username-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
		require_login=True,
	)

	task = WebArenaProTask(seed=0, config=config)
	username, password = task.instance._auto_login.resolve_credentials(
		site=config.website, username=config.login_username
	)

	assert username == "admin"
	assert password == "Admin@Secure123"


def test_resolve_login_credentials_raises_for_unknown_username():
	config = WebArenaProTaskConfig(
		task_id="task-login-unknown-username",
		intent="Login with unknown username",
		sites=("mattermost",),
		evaluation=None,
		container_name="webarena-pro-task-login-unknown-username-0",
		start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
		require_login=True,
		login_username="unknown.user",
	)

	task = WebArenaProTask(seed=0, config=config)

	with pytest.raises(RuntimeError, match="No credentials found"):
		task.instance._auto_login.resolve_credentials(
			site=config.website, username=config.login_username
		)


class DummyOpenPage:
	def __init__(self, url: str) -> None:
		self.url = url

	def goto(self, url, **kwargs):
		self.url = url


class DummyPageContext:
	def __init__(self, pages) -> None:
		self.pages = pages


class DummyValidationPage:
	def __init__(self, pages) -> None:
		self.context = DummyPageContext(pages)


def test_task_validate_contains_navigation_to_unselected_site():
	config = WebArenaProTaskConfig(
		task_id="task-reject-unselected-site",
		intent="Stay in Nextcloud",
		sites=("nextcloud",),
		evaluation=None,
		container_name="webarena-pro-task-reject-unselected-site-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
	)
	task = WebArenaProTask(seed=0, config=config)
	page = DummyValidationPage([DummyOpenPage(DEPLOYED_WEBSITE_URLS["mattermost"])])

	score, done, _, info = task.validate(page, chat_messages=[])

	assert score == 0
	assert done is False
	assert page.context.pages[0].url == "about:blank"
	assert info == {"dag_evaluated": False, "navigation_blocked": True}


def test_task_validate_uses_dag_evaluator(monkeypatch):
	from webarena_pro_core.eval import dag as dag_module

	captured = {}

	class AlwaysPass(dag_module.NodeEvaluator):
		def evaluate(self, eval_config, context):
			captured["eval_config"] = eval_config
			captured["trajectory"] = context.trajectory
			captured["last_step_output"] = context.last_step_output
			return True

	monkeypatch.setitem(dag_module._REGISTRY, "pass", AlwaysPass())

	config = WebArenaProTaskConfig(
		task_id="task-7",
		intent="Do task",
		sites=("nextcloud",),
		container_name="webarena-pro-task-7-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		evaluation={
			"operator": "AND",
			"scoring": "binary",
			"nodes": [
				{
					"id": "s1",
					"type": "pass",
					"eval_config": {"expected": "ok"},
				}
			],
		},
		raw_task={
			"task_id": "task-7",
			"intent": "Do task",
			"eval": {
				"operator": "AND",
				"scoring": "binary",
				"nodes": [
					{
						"id": "s1",
						"type": "pass",
						"eval_config": {"expected": "ok"},
					}
				],
			},
			"persona": {
				"name": "Test User",
				"skills": [],
				"interests": [],
				"description": "",
			},
		},
	)

	task = WebArenaProTask(seed=0, config=config)
	score, done, _, info = task.validate(
		page=DummyPage(),
		chat_messages=[{"role": "assistant", "message": "Final answer"}],
		last_step_output={"episode_info": []},
		last_action='send_msg_to_user("Final answer")',
	)

	assert score == 1.0
	assert done is True
	assert info["score"] == 1.0
	assert info["dag_results"] == {"s1": {"passed": True, "reason": ""}}
	assert captured["trajectory"] == []


def test_task_validate_returns_zero_without_eval_config():
	config = WebArenaProTaskConfig(
		task_id="task-8",
		intent="Do task",
		sites=("nextcloud",),
		container_name="webarena-pro-task-8-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		evaluation=None,
	)

	task = WebArenaProTask(seed=0, config=config)
	score, done, _, info = task.validate(page=DummyPage(), chat_messages=[])

	assert score == 0.0
	assert done is False
	assert info["score"] == 0.0


def test_task_validate_rejects_flat_rubric_verifier():
	config = WebArenaProTaskConfig(
		task_id="task-rubric-verifier",
		intent="Do task",
		sites=("nextcloud",),
		container_name="webarena-pro-task-rubric-verifier-0",
		start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
		evaluation={
			"eval_types": ["rubric_verifier"],
			"reference_answers": {"hint": "Complete the task."},
		},
	)

	task = WebArenaProTask(seed=0, config=config)
	with pytest.raises(ValueError, match="Whole-task rubric evaluation was removed"):
		task.validate(page=DummyPage(), chat_messages=[], last_action='send_msg_to_user("done")')


def test_task_replaces_judge_scope_on_setup_and_shares_it_between_checkpoints(monkeypatch):
    from webarena_pro_core.eval import llm_judge

    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
    monkeypatch.setattr("webarena_pro_core.state_reset.wait_until_site_ready", lambda site: None)
    dag = {"nodes": [{"id": "r1", "type": "llm_judge", "eval_config": {"rubric": "Save file"}}]}
    config = WebArenaProTaskConfig(
        task_id="cache-checkpoints", intent="Save file", sites=("nextcloud",),
        container_name="unused", start_url=DEPLOYED_WEBSITE_URLS["nextcloud"],
        evaluation=dag, raw_task={"task_id": "cache-checkpoints", "intent": "Save file"},
    )
    task = WebArenaProTask(seed=0, config=config)
    page = DummyPage()
    initial_scope = task.judge_cache
    task.setup(page)
    assert task.judge_cache is not initial_scope
    scopes = []

    def judge(rubric, context, model):
        scopes.append(context.judge_cache)
        return "pass", "scripted"

    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", judge)
    for _ in range(2):
        task.validate(page, [], budget_checkpoint=True,
                      last_step_output={"obs": {"axtree_txt": "File saved"}})
    assert scopes == [task.judge_cache, task.judge_cache]
    previous_scope = task.judge_cache
    task.setup(page)
    assert task.judge_cache is not previous_scope
