import json

import webarena_pro_bgym.benchmark.benchmark as benchmark_module
from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark


def test_benchmark_loads_tasks_with_unique_container_names(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "webarena_pro_core.task.DEPLOYED_WEBSITE_URLS",
        {"nextcloud": "http://localhost:3210"},
    )
    monkeypatch.setattr(benchmark_module, "_CONFIG_DIR", tmp_path)

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
                    "task_id": "test_task_2",
                    "intent": "Task two",
                    "website": "nextcloud",
                    "evaluation": "/tmp/eval2",
                },
            ]
        ),
        encoding="utf-8",
    )

    benchmark = WebArenaProBenchmark(sites=["nextcloud"])

    assert len(benchmark.env_args_list) == 2
    container_names = {
        env_args.task_config.container_name for env_args in benchmark.env_args_list
    }
    assert len(container_names) == 2
    assert benchmark.env_args_list[0].task_name == "webarena-pro-bgym.test_task_1"
    assert benchmark.env_args_list[1].task_name == "webarena-pro-bgym.test_task_2"
    assert all(env_args.max_steps == 50 for env_args in benchmark.env_args_list)


def test_benchmark_adds_dependencies_for_same_website(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "webarena_pro_core.task.DEPLOYED_WEBSITE_URLS",
        {
            "nextcloud": "http://localhost:3210",
            "gitlab": "http://localhost:9999",
        },
    )
    monkeypatch.setattr(benchmark_module, "_CONFIG_DIR", tmp_path)

    (tmp_path / "nextcloud.raw.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "task_a1",
                    "intent": "Task A1",
                    "website": "nextcloud",
                    "evaluation": "/tmp/eval1",
                },
                {
                    "task_id": "task_a2",
                    "intent": "Task A2",
                    "website": "nextcloud",
                    "evaluation": "/tmp/eval3",
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "gitlab.raw.json").write_text(
        json.dumps(
            [
                {
                    "task_id": "task_b1",
                    "intent": "Task B1",
                    "website": "gitlab",
                    "evaluation": "/tmp/eval2",
                },
            ]
        ),
        encoding="utf-8",
    )

    benchmark = WebArenaProBenchmark(sites=["nextcloud", "gitlab"], use_task_dependencies=True)
    dependencies = benchmark.dependency_graph_over_tasks()

    assert dependencies["webarena-pro-bgym.task_a1"] == []
    assert dependencies["webarena-pro-bgym.task_b1"] == []
    assert dependencies["webarena-pro-bgym.task_a2"] == ["webarena-pro-bgym.task_a1"]


def test_benchmark_skips_empty_config_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "webarena_pro_core.task.DEPLOYED_WEBSITE_URLS",
        {"nextcloud": "http://localhost:3210"},
    )
    monkeypatch.setattr(benchmark_module, "_CONFIG_DIR", tmp_path)

    (tmp_path / "nextcloud.raw.json").write_text("", encoding="utf-8")

    benchmark = WebArenaProBenchmark(sites=["nextcloud"])

    assert benchmark.env_args_list == []
