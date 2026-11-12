import json

import pytest

from webarena_pro_core.task import (
    CONFIG_DIR,
    DEPLOYED_WEBSITE_URLS,
    WebArenaProTaskConfig,
    load_raw_tasks,
    load_task_configs,
    task_config_files,
    task_container_name,
)


def test_task_config_from_raw_task_uses_core_start_url():
    config = WebArenaProTaskConfig.from_raw_task(
        raw_task={
            "task_id": "task-3",
            "intent": "Open app",
            "website": "nextcloud",
            "eval": {
                "eval_types": ["string_match"],
                "reference_answers": {"exact_match": ""},
            },
        },
        container_name="webarena-pro-task-3-0",
    )

    assert config.start_url == DEPLOYED_WEBSITE_URLS["nextcloud"]


def test_task_config_from_raw_task_uses_core_login_url():
    config = WebArenaProTaskConfig.from_raw_task(
        raw_task={
            "task_id": "task-5",
            "intent": "Login first",
            "website": "nextcloud",
            "require_login": True,
            "login_page": "http://localhost:9999/login",
        },
        container_name="webarena-pro-task-5-0",
    )

    assert config.require_login is True
    assert config.login_page == f"{DEPLOYED_WEBSITE_URLS['nextcloud']}/login"


def test_task_config_from_raw_task_supports_login_usernames_per_site():
    config = WebArenaProTaskConfig.from_raw_task(
        raw_task={
            "task_id": "task-cross-site-login-users",
            "intent": "Use both apps",
            "sites": ["nextcloud", "mattermost"],
            "require_login": True,
            "login_usernames": {
                "nextcloud": "agent2",
                "mattermost": "admin",
            },
        },
        container_name="webarena-pro-task-cross-site-login-users-0",
    )

    assert config.website == "nextcloud"
    assert config.sites == ("nextcloud", "mattermost")
    assert config.login_username == "agent2"
    assert config.login_usernames == {
        "nextcloud": "agent2",
        "mattermost": "admin",
    }


def test_task_config_rejects_legacy_website_that_conflicts_with_sites():
    with pytest.raises(ValueError, match="must match the first"):
        WebArenaProTaskConfig.from_raw_task(
            raw_task={
                "task_id": "task-conflicting-website",
                "intent": "Use both apps",
                "website": "mattermost",
                "sites": ["nextcloud", "mattermost"],
            },
            container_name="webarena-pro-task-conflicting-website-0",
        )


def test_task_config_rejects_login_usernames_for_unselected_sites():
    with pytest.raises(ValueError, match="not listed in `sites`"):
        WebArenaProTaskConfig.from_raw_task(
            raw_task={
                "task_id": "task-cross-site-login-users",
                "intent": "Use both apps",
                "sites": ["nextcloud"],
                "login_usernames": {
                    "mattermost": "admin",
                },
            },
            container_name="webarena-pro-task-cross-site-login-users-0",
        )


def test_load_task_configs_from_core_task_files(tmp_path):
    (tmp_path / "nextcloud.raw.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "test_task_1",
                    "intent": "Task one",
                    "website": "nextcloud",
                    "evaluation": "/tmp/eval1",
                },
                {
                    "task_id": "test task 2",
                    "intent": "Task two",
                    "website": "nextcloud",
                    "evaluation": "/tmp/eval2",
                },
            ]
        ),
        encoding="utf-8",
    )

    configs = load_task_configs(["nextcloud"], config_dir=tmp_path)

    assert [config.task_id for config in configs] == ["test_task_1", "test task 2"]
    assert [config.container_name for config in configs] == [
        "webarena-pro-test-task-1-0",
        "webarena-pro-test-task-2-1",
    ]


def test_load_raw_tasks_applies_adjacent_tiered_evaluations(tmp_path):
    raw_path = tmp_path / "nextcloud.raw.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "task_id": "171",
                    "intent": "Match by intent",
                    "website": "nextcloud",
                    "eval": {"eval_types": ["rubric_verifier"]},
                },
                {
                    "task_id": "234",
                    "original_task_id": "original-234",
                    "intent": "Match by original id",
                    "website": "nextcloud",
                    "eval": {"eval_types": ["rubric_verifier"]},
                },
                {
                    "task_id": "235",
                    "intent": "Match by current id",
                    "website": "nextcloud",
                },
                {
                    "task_id": "236",
                    "intent": "Keep the embedded DAG",
                    "website": "nextcloud",
                    "eval": {"nodes": [{"id": "embedded-node", "type": "tiered"}]},
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "nextcloud.tiered.json").write_text(
        json.dumps(
            {
                "_README": "metadata",
                "sidecar-id": {
                    "intent": "Match by intent",
                    "operator": "AND",
                    "nodes": [{"id": "intent-node", "type": "tiered"}],
                },
                "original-234": {
                    "intent": "The sidecar intent may differ when the id matches",
                    "operator": "AND",
                    "nodes": [{"id": "original-id-node", "type": "tiered"}],
                },
                "235": {
                    "intent": "An older prompt with the same current task id",
                    "operator": "AND",
                    "nodes": [{"id": "current-id-node", "type": "tiered"}],
                },
                "236": {"nodes": [{"id": "outdated-node", "type": "tiered"}]},
            }
        ),
        encoding="utf-8",
    )

    tasks = load_raw_tasks(raw_path)

    assert tasks[0]["eval"] == {
        "operator": "AND",
        "nodes": [{"id": "intent-node", "type": "tiered"}],
    }
    assert tasks[1]["eval"] == {
        "operator": "AND",
        "nodes": [{"id": "original-id-node", "type": "tiered"}],
    }
    assert tasks[2]["eval"] == {
        "operator": "AND",
        "nodes": [{"id": "current-id-node", "type": "tiered"}],
    }
    assert tasks[3]["eval"] == {"nodes": [{"id": "embedded-node", "type": "tiered"}]}


@pytest.mark.parametrize("filename,bundle", [("nextcloud.raw.json", False), ("dev.json", True)])
@pytest.mark.parametrize("eval_field", ["eval", "evaluation"])
def test_embedded_evaluations_load_without_reading_stale_sidecars(tmp_path, filename, bundle, eval_field):
    tasks = [{"task_id": "001", "intent": "Current prompt", "sites": ["nextcloud"],
              eval_field: {"operator": "AND", "nodes": [{"id": "current", "type": "tiered"}]}}]
    path = tmp_path / filename
    payload = {"sampling": {"seed": 42}, "tasks": tasks} if bundle else tasks
    path.write_text(json.dumps(payload))
    sidecar = "dev.tiered.json" if bundle else "nextcloud.tiered.json"
    (tmp_path / sidecar).write_text("invalid stale sidecar")

    assert load_raw_tasks(path) == tasks


def test_task_config_files_can_select_all_or_named_sites(tmp_path):
    (tmp_path / "a.raw.json").write_text("[]", encoding="utf-8")
    (tmp_path / "b.raw.json").write_text("[]", encoding="utf-8")

    assert [path.name for path in task_config_files("all", config_dir=tmp_path)] == [
        "a.raw.json",
        "b.raw.json",
    ]
    assert task_config_files(["nextcloud"], config_dir=tmp_path) == [
        tmp_path / "nextcloud.raw.json",
    ]


def test_core_task_directories_contain_moved_raw_tasks():
    assert (CONFIG_DIR / "nextcloud.raw.json").exists()


def test_packaged_task_ids_are_zero_padded_global_ids():
    configs = load_task_configs("all")
    task_ids = [config.task_id for config in configs]

    assert len(configs) == 300
    assert len(set(task_ids)) == len(task_ids)
    assert task_ids[0] == "001"
    assert max(task_ids) == "420"
    assert all(task_id.isdigit() and len(task_id) == 3 for task_id in task_ids)
    assert all("original_task_id" not in config.raw_task for config in configs)




def test_active_tasks_have_one_record_with_an_embedded_dag():
    assert not list(CONFIG_DIR.rglob("*.tiered.json"))
    task_ids = []
    for path in [*CONFIG_DIR.glob("*.raw.json"), CONFIG_DIR / "splits/dev.json"]:
        payload = json.loads(path.read_text())
        tasks = payload["tasks"] if isinstance(payload, dict) else payload
        assert load_raw_tasks(path) == tasks
        for task in tasks:
            task_ids.append(task["task_id"])
            assert task["intent"]
            assert task["eval"]["nodes"], (path.name, task["task_id"])
            assert not {"intent", "task_id", "eval_types", "rubrics"} & task["eval"].keys()
            assert "rubrics" not in task
            assert not {
                "original_task_id", "creator_username", "creator_username_source",
                "start_url", "require_reset",
            } & task.keys()
    assert len(task_ids) == len(set(task_ids)) == 400
    configs = load_task_configs("all") + load_task_configs(split="dev")
    assert len(configs) == 400
    assert all(config.evaluation == config.raw_task["eval"] for config in configs)


def test_task_container_name_normalizes_task_ids():
    assert task_container_name("Task 1_A", 7) == "webarena-pro-task-1-a-7"
