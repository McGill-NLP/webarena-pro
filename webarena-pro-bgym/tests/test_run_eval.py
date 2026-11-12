from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import pytest

import webarena_pro_bgym.run_eval_cli as run_eval


def test_old_script_entry_point_delegates_to_tiered(monkeypatch):
    calls = []
    monkeypatch.setattr("webarena_pro_bgym.run_tiered_cli.main", lambda argv: calls.append(argv) or 0)
    assert run_eval.main(["--split", "dev", "--list"]) == 0
    assert calls == [["--split", "dev", "--list"]]


def test_resume_rejects_legacy_judge_study_before_starting_sites(monkeypatch):
    study = SimpleNamespace(exp_args_list=[SimpleNamespace(env_args=SimpleNamespace(
        task_config=SimpleNamespace(evaluation={"eval_types": ["rubric_verifier"]})))])
    monkeypatch.setattr(run_eval.WebArenaProStudy, "load", lambda path: study)
    monkeypatch.setattr(run_eval, "ensure_sites_ready", lambda *args: pytest.fail("Must not start sites"))
    assert run_eval._resume_existing_study(SimpleNamespace(resume_study="legacy-study")) == 1


def test_legacy_resume_requires_explicit_paid_restart(monkeypatch, caplog):
    study = SimpleNamespace(exp_args_list=[SimpleNamespace(env_args=SimpleNamespace(
        task_config=SimpleNamespace(evaluation={"nodes": []})))])
    monkeypatch.setattr(run_eval.WebArenaProStudy, "load", lambda path: study)
    monkeypatch.setattr(run_eval, "ensure_sites_ready", lambda *args: pytest.fail("Must not start sites"))
    assert run_eval._resume_existing_study(SimpleNamespace(resume_study="legacy-study")) == 1
    assert "--retry-from-start" in caplog.text
    assert "new agent calls" in caplog.text


def test_legacy_explicit_restart_delegates_to_supervised_migration(monkeypatch, tmp_path):
    study = SimpleNamespace(dir=tmp_path, exp_args_list=[SimpleNamespace(env_args=SimpleNamespace(
        task_config=SimpleNamespace(evaluation={"nodes": []}, website="mattermost")))])
    calls = []
    monkeypatch.setattr(run_eval.WebArenaProStudy, "load", lambda path: study)
    monkeypatch.setattr(run_eval, "ensure_sites_ready", lambda *args: pytest.fail("Migration handles runtime"))
    monkeypatch.setitem(run_eval.sys.modules, "webarena_pro_bgym.legacy_recovery", SimpleNamespace(
        resume_legacy_study=lambda study, args: calls.append((study, args)) or 0,
    ))
    args = SimpleNamespace(
        resume_study=str(tmp_path), retry_from_start=True, max_steps=None, n_jobs=1,
        n_relaunch=2, incomplete_only=False,
    )
    assert run_eval._resume_existing_study(args) == 0
    assert calls == [(study, args)]


def _make_exp(site: str, max_steps: int = 30, sites=None):
    return SimpleNamespace(
        env_args=SimpleNamespace(
            max_steps=max_steps,
            task_config=SimpleNamespace(website=site, sites=sites),
        )
    )


def test_study_sites_returns_unique_sorted_sites():
    study = SimpleNamespace(
        exp_args_list=[
            _make_exp("mattermost"),
            _make_exp("nextcloud"),
            _make_exp("mattermost"),
        ]
    )

    assert run_eval.study_sites(study) == ["mattermost", "nextcloud"]


def test_study_sites_uses_task_selected_sites():
    study = SimpleNamespace(
        exp_args_list=[
            _make_exp("nextcloud", sites=("nextcloud", "mattermost")),
        ]
    )

    assert run_eval.study_sites(study) == ["mattermost", "nextcloud"]


def test_selected_sites_for_env_args_uses_task_selected_sites():
    env_args = [
        SimpleNamespace(task_config=SimpleNamespace(website="nextcloud", sites=("nextcloud", "mattermost"))),
        SimpleNamespace(task_config=SimpleNamespace(website="metabase", sites=None)),
    ]

    assert run_eval.selected_sites_for_env_args(env_args) == [
        "mattermost",
        "metabase",
        "nextcloud",
    ]


def test_override_study_max_steps_updates_all_experiments():
    study = SimpleNamespace(exp_args_list=[_make_exp("nextcloud", 10), _make_exp("metabase", 20)])

    run_eval.override_study_max_steps(study, 42)

    assert [exp.env_args.max_steps for exp in study.exp_args_list] == [42, 42]


def test_resume_study_relaunches_incomplete_runs(monkeypatch):
    calls = []

    class FakeStudy:
        def __init__(self):
            self.dir = Path("/tmp/fake-study")
            self.name = "fake-study"
            self.exp_args_list = [_make_exp("nextcloud", 12)]

        def find_incomplete(self, include_errors):
            calls.append(("find_incomplete", include_errors))
            return 2, 1

        def run(self, **kwargs):
            calls.append(("run", kwargs))

    monkeypatch.setattr(
        run_eval,
        "print_eval_results",
        lambda results_dir, label: calls.append(("print_eval_results", results_dir, label)),
    )

    study = FakeStudy()
    run_eval.resume_study(
        study=study,
        max_steps=99,
        n_jobs=3,
        n_relaunch=4,
        relaunch_errors=True,
    )

    assert calls[0] == ("find_incomplete", True)
    assert calls[1] == (
        "run",
        {
            "n_jobs": 1,
            "parallel_backend": "sequential",
            "n_relaunch": 4,
            "relaunch_errors": True,
        },
    )
    assert study.exp_args_list[0].env_args.max_steps == 99
    assert calls[2] == ("print_eval_results", Path("/tmp/fake-study"), "nextcloud")


def test_resume_study_skips_run_when_nothing_to_relaunch(monkeypatch):
    calls = []

    class FakeStudy:
        def __init__(self):
            self.dir = Path("/tmp/fake-study")
            self.name = "fake-study"
            self.exp_args_list = [_make_exp("metabase", 15)]

        def find_incomplete(self, include_errors):
            calls.append(("find_incomplete", include_errors))
            return 0, 0

        def run(self, **kwargs):
            calls.append(("run", kwargs))

    monkeypatch.setattr(
        run_eval,
        "print_eval_results",
        lambda results_dir, label: calls.append(("print_eval_results", results_dir, label)),
    )

    run_eval.resume_study(
        study=FakeStudy(),
        max_steps=None,
        n_jobs=1,
        n_relaunch=2,
        relaunch_errors=False,
    )

    assert calls == [
        ("find_incomplete", False),
        ("print_eval_results", Path("/tmp/fake-study"), "metabase"),
    ]


def test_supported_sites_include_generic_configs():
    sites = run_eval.supported_sites()

    assert "nextcloud" in sites
    assert "notion" in sites


def test_build_agent_uses_requested_model():
    agent = run_eval._build_agent("gemini/gemini-3.1-pro-preview")

    assert agent.chat_model_args is run_eval.WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.1-pro-preview"]


def test_build_agent_uses_requested_vllm_model():
    agent = run_eval._build_agent("vllm/qwen35-9b")

    assert agent.chat_model_args is run_eval.WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["vllm/qwen35-9b"]


def test_required_api_key_env_var_only_applies_to_gemini():
    assert run_eval._required_api_key_env_var("gemini/gemini-3.1-pro-preview") == "GEMINI_API_KEY"
    assert run_eval._required_api_key_env_var("vllm/qwen35-9b") is None


def test_print_eval_results_reports_binary_average_reward(tmp_path, capsys):
    passed = tmp_path / "2026-05-04_GenericAgent_on_webarena-pro-bgym.100_0"
    passed.mkdir()
    (passed / "summary_info.json").write_text('{"cum_reward": 12.7, "n_steps": 8}')

    failed = tmp_path / "2026-05-04_GenericAgent_on_webarena-pro-bgym.101_0"
    failed.mkdir()
    (failed / "summary_info.json").write_text('{"cum_reward": 0, "n_steps": 4}')

    run_eval.print_eval_results(tmp_path, "demo")

    assert "Total: 1/2 passed, avg_reward=0.500" in capsys.readouterr().out


@pytest.mark.parametrize("parallel", [False, True])
def test_completed_grade_with_close_error_is_not_reported_as_pass(tmp_path, capsys, parallel):
    exp_dir = tmp_path / "GenericAgent_on_webarena-pro-bgym.100_0"
    exp_dir.mkdir()
    (exp_dir / "summary_info.json").write_text(
        '{"cum_reward": 1, "n_steps": 8, "err_msg": "Environment close timed out"}'
    )
    if parallel:
        assert run_eval.aggregate_parallel_results("fixture", root_dir=tmp_path) == (0, 1)
    else:
        run_eval.print_eval_results(tmp_path, "fixture")
    output = capsys.readouterr().out
    assert "ERROR (score=1.00)" in output
    assert "Environment close timed out" in output
    assert "Total: 0/1 passed" in output


def test_run_agent_uses_sequential_study_inside_worker(monkeypatch, tmp_path):
    calls = {}
    benchmark = SimpleNamespace(name="fake-benchmark")
    env_args = SimpleNamespace(task_config=SimpleNamespace(task_id="104"))

    monkeypatch.setattr(
        run_eval,
        "_build_filtered_benchmark",
        lambda site, task_ids, max_steps: (benchmark, [env_args]),
    )
    monkeypatch.setattr(run_eval, "_build_agent", lambda agent_model: SimpleNamespace())
    monkeypatch.setattr(
        run_eval,
        "print_eval_results",
        lambda results_dir, label: calls.update(print=(results_dir, label)),
    )

    class FakeStudy:
        def __init__(self, **kwargs):
            calls["study"] = kwargs
            self.dir = tmp_path / "study"

        def run(self, **kwargs):
            calls["run"] = kwargs

    monkeypatch.setattr(run_eval, "WebArenaProStudy", FakeStudy)

    run_eval.run_agent(
        site="nextcloud",
        task_ids=[104],
        max_steps=30,
        n_jobs=2,
        n_relaunch=3,
        study_dir=str(tmp_path / "study"),
        agent_model="vllm/qwen35-9b",
    )

    assert calls["study"]["benchmark"] is benchmark
    assert calls["study"]["suffix"] == "nextcloud-eval"
    assert calls["study"]["dir"] == tmp_path / "study"
    assert calls["run"] == {
        "n_jobs": 1,
        "parallel_backend": "sequential",
        "n_relaunch": 3,
    }
    assert calls["print"] == (tmp_path / "study", "nextcloud")


def test_check_site_reachable_uses_generic_fallback(monkeypatch):
    class FakeResponse:
        status_code = 200

    calls = []

    def fake_get(url, timeout, allow_redirects, headers=None):
        calls.append((url, timeout, allow_redirects, headers))
        return FakeResponse()

    monkeypatch.setenv("WP_URL_MODE", "port")
    monkeypatch.setattr(run_eval.requests, "get", fake_get)

    assert run_eval.check_site_reachable("notion") is True
    assert calls[0][0] == run_eval.DEPLOYED_WEBSITE_URLS["notion"]
    assert calls[0][2] is True
    assert calls[0][3] is None


def test_check_site_reachable_rejects_generic_404(monkeypatch):
    class FakeResponse:
        status_code = 404

    monkeypatch.setattr(
        run_eval.requests,
        "get",
        lambda url, timeout, allow_redirects, headers=None: FakeResponse(),
    )

    assert run_eval.check_site_reachable("notion") is False


def test_check_site_reachable_uses_public_subdomain_url_for_remote_proxy(monkeypatch):
    class FakeResponse:
        status_code = 200

    calls = []

    def fake_get(url, timeout, allow_redirects, headers=None):
        calls.append((url, timeout, allow_redirects, headers))
        return FakeResponse()

    public_url = "http://notion--local.213.0.113.10.sslip.io"
    monkeypatch.setenv("WP_URL_MODE", "subdomain")
    monkeypatch.setenv("WP_WEB_SERVER_DOMAIN", "213.0.113.10.sslip.io")
    monkeypatch.setitem(run_eval.DEPLOYED_WEBSITE_URLS, "notion", public_url)
    monkeypatch.setattr(run_eval.requests, "get", fake_get)

    assert run_eval.check_site_reachable("notion") is True
    assert calls[0][0] == public_url
    assert calls[0][3] is None


def test_check_site_reachable_uses_local_subdomain_url_first(monkeypatch):
    class FakeResponse:
        status_code = 200

    calls = []

    def fake_get(url, timeout, allow_redirects, headers=None):
        calls.append((url, timeout, allow_redirects, headers))
        return FakeResponse()

    monkeypatch.setenv("WP_URL_MODE", "subdomain")
    monkeypatch.setenv("WP_WEB_SERVER_DOMAIN", "localhost")
    monkeypatch.setenv("WP_WEB_SERVER_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("WP_WEB_SERVER_PORT", "8080")
    monkeypatch.setattr(run_eval.requests, "get", fake_get)

    assert run_eval.check_site_reachable("notion") is True
    assert calls[0][0] == "http://notion--local.localhost:8080"
    assert calls[0][3] is None


def test_check_site_reachable_falls_back_to_proxy_host_for_local_subdomain(monkeypatch):
    class FakeResponse:
        status_code = 200

    calls = []

    def fake_get(url, timeout, allow_redirects, headers=None):
        calls.append((url, timeout, allow_redirects, headers))
        if url == "http://notion--local.localhost:8080":
            raise run_eval.requests.ConnectionError("local wildcard DNS unavailable")
        return FakeResponse()

    monkeypatch.setenv("WP_URL_MODE", "subdomain")
    monkeypatch.setenv("WP_WEB_SERVER_DOMAIN", "localhost")
    monkeypatch.setenv("WP_WEB_SERVER_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("WP_WEB_SERVER_PORT", "8080")
    monkeypatch.setattr(run_eval.requests, "get", fake_get)

    assert run_eval.check_site_reachable("notion") is True
    assert calls == [
        ("http://notion--local.localhost:8080", 30, True, None),
        (
            "http://127.0.0.1:8080",
            30,
            True,
            {"Host": "notion--local.localhost:8080"},
        ),
    ]


def test_ensure_site_up_uses_worker_specific_container_name(monkeypatch):
    calls = []
    reachable = iter([False, True])

    monkeypatch.setattr(run_eval, "ensure_docker_running", lambda: True)
    monkeypatch.setattr(run_eval, "check_site_reachable", lambda site: next(reachable))
    monkeypatch.setenv("WP_MATTERMOST_CONTAINER_NAME", "mattermost-w7")
    monkeypatch.setenv("WP_URL_MODE", "port")

    class FakeManager:
        def ensure_container_running(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        "webarena_pro_core.docker.DockerContainerManager",
        lambda: FakeManager(),
    )

    assert run_eval.ensure_site_up("mattermost", wait_timeout=1) is True
    assert calls[0]["name"] == "mattermost-w7"


def test_ensure_sites_ready_skips_container_preflight_when_task_reset_runs(monkeypatch):
    calls = []

    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "1")
    monkeypatch.setattr(run_eval, "ensure_site_up", lambda site: calls.append(site))

    args = SimpleNamespace(
        skip_preflight=False,
        no_autostart=False,
        dry_run=False,
        n_jobs=2,
    )

    assert run_eval.ensure_sites_ready(["mattermost"], args) is True
    assert calls == []


def test_ensure_sites_ready_checks_sites_for_dry_run(monkeypatch):
    calls = []

    monkeypatch.setattr(
        run_eval,
        "ensure_site_up",
        lambda site: calls.append(site) or True,
    )

    args = SimpleNamespace(
        skip_preflight=False,
        no_autostart=False,
        dry_run=True,
        n_jobs=2,
    )

    assert run_eval.ensure_sites_ready(["mattermost", "mattermost"], args) is True
    assert calls == ["mattermost"]


def test_ensure_sites_ready_checks_sites_when_task_reset_disabled(monkeypatch):
    calls = []

    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
    monkeypatch.setattr(
        run_eval,
        "ensure_site_up",
        lambda site: calls.append(site) or True,
    )

    args = SimpleNamespace(
        skip_preflight=False,
        no_autostart=False,
        dry_run=False,
        n_jobs=2,
    )

    assert run_eval.ensure_sites_ready(["mattermost"], args) is True
    assert calls == ["mattermost"]


def test_run_one_site_delegates_n_jobs_to_worker_parallel(monkeypatch):
    calls = []
    monkeypatch.delenv("WP_PARALLEL_WORKER_INDEX", raising=False)
    monkeypatch.setattr(
        run_eval,
        "run_parallel",
        lambda site, args, task_ids: calls.append((site, args.n_jobs, task_ids)) or 0,
    )

    args = SimpleNamespace(
        n_jobs=2,
        parallel=None,
        dry_run=False,
        max_steps=30,
        n_relaunch=1,
        study_dir=None,
        agent_model="vllm/qwen35-9b",
    )

    assert run_eval._run_one_site("mattermost", args, [99, 100]) == 0
    assert calls == [("mattermost", 2, [99, 100])]


def test_run_one_site_refuses_nested_worker_parallel(monkeypatch):
    monkeypatch.setenv("WP_PARALLEL_WORKER_INDEX", "0")

    args = SimpleNamespace(
        n_jobs=2,
        parallel=None,
        dry_run=False,
        max_steps=30,
        n_relaunch=1,
        study_dir=None,
        agent_model="vllm/qwen35-9b",
    )

    assert run_eval._run_one_site("mattermost", args, [99, 100]) == 2
def test_parallel_aggregation_ignores_archived_retry_attempts(tmp_path):
    import json
    from webarena_pro_bgym.run_eval_cli import aggregate_parallel_results

    for name, reward in (("_old_on_webarena-pro-bgym.001_0", 0),
                         ("new_on_webarena-pro-bgym.001_0", 1)):
        directory = tmp_path / "workers" / "worker-0" / name
        directory.mkdir(parents=True)
        (directory / "summary_info.json").write_text(json.dumps({"cum_reward": reward}))
    assert aggregate_parallel_results("tiered", root_dir=tmp_path) == (1, 1)


def test_parallel_aggregation_uses_current_worker_even_if_old_summary_is_newer(tmp_path):
    import json
    from webarena_pro_bgym.task_queue import TaskQueue

    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["mattermost"]})
    queue.claim("worker-current")
    queue.started(1, "worker-current")
    queue.complete(1, "worker-current")
    for worker, reward, modified in (("worker-old", 0, 2000), ("worker-current", 1, 1000)):
        directory = tmp_path / "workers" / worker / "exp_on_webarena-pro-bgym.001_0"
        directory.mkdir(parents=True)
        summary = directory / "summary_info.json"
        summary.write_text(json.dumps({"cum_reward": reward}))
        os.utime(summary, (modified, modified))
    assert run_eval.aggregate_parallel_results("tiered", root_dir=tmp_path) == (1, 1)


def test_parallel_aggregation_does_not_report_old_result_if_current_worker_has_none(tmp_path):
    from webarena_pro_bgym.task_queue import TaskQueue

    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["mattermost"]})
    queue.claim("worker-current")
    queue.started(1, "worker-current")
    old = tmp_path / "workers" / "worker-old" / "exp_on_webarena-pro-bgym.001_0"
    old.mkdir(parents=True)
    (old / "summary_info.json").write_text('{"cum_reward": 1}')
    assert run_eval.aggregate_parallel_results("tiered", root_dir=tmp_path) == (0, 0)


def test_queue_aggregation_collapses_retry_directory_suffixes(tmp_path):
    import json
    from webarena_pro_bgym.task_queue import TaskQueue

    queue = TaskQueue.create(tmp_path / "queue.jsonl", {1: ["mattermost"]})
    queue.claim("worker-current")
    queue.started(1, "worker-current")
    queue.complete(1, "worker-current")
    for suffix, reward, modified in (("001_0", 0, 1000), ("001_0_1", 1, 2000)):
        directory = tmp_path / "workers" / "worker-current" / f"exp_on_webarena-pro-bgym.{suffix}"
        directory.mkdir(parents=True)
        summary = directory / "summary_info.json"
        summary.write_text(json.dumps({"cum_reward": reward}))
        os.utime(summary, (modified, modified))
    assert run_eval.aggregate_parallel_results("tiered", root_dir=tmp_path) == (1, 1)
