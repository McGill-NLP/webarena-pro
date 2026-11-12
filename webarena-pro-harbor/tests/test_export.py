import json
import shutil
import subprocess
import tomllib

import pytest
import yaml
from webarena_pro_mcp.media_policy import MediaSettings

from webarena_pro_harbor.cli import select_tasks
from webarena_pro_harbor.export import episode_config, export_tasks, validate_image


def test_export_isolated_portable_and_keeps_core_tasks(tmp_path, monkeypatch):
    monkeypatch.setenv("WP_EVAL_TOKEN", "DO-NOT-EXPORT-THIS-TOKEN")
    monkeypatch.setenv("WP_COLLABORA_URL", "https://private-office.example")
    tasks = select_tasks("dev", "all", None)
    out = tmp_path / "tasks"
    result = export_tasks(tasks, out, split="dev")
    assert len(result) == len(tasks) == 100
    for task in tasks:
        root = out / f"webarena-pro-dev-{task.task_id}"
        config = tomllib.loads((root / "task.toml").read_text())
        episode = json.loads((root / "environment/browser/episode.json").read_text())
        assert episode["task"] == task.raw_task
        assert (root / "instruction.md").read_text().startswith(task.intent + "\n")
        instruction = (root / "instruction.md").read_text()
        assert "final submission are free" in instruction
        assert "including after the last allowed action" in instruction
        assert "reserve an action" not in instruction
        assert config["verifier"]["environment_mode"] == "separate"
        assert config["verifier"]["collect"][0]["service"] == "webarena"
        assert config["artifacts"] == [
            {"source": "/webarena-evidence", "service": "webarena"},
            {"source": "/webarena-service", "service": "webarena"},
        ]
        services = yaml.safe_load((root / "environment/docker-compose.yaml").read_text())
        assert services["networks"]["websites"]["internal"] is True
        assert services["services"]["main"]["networks"] == ["default"]
        assert "environment" not in services["services"]["main"]
        assert (
            services["services"]["webarena"]["environment"]["WEBARENAPRO_LLM_JUDGE_STREAM"]
            == "${WP_HARBOR_JUDGE_STREAM:-0}"
        )
        for site in task.sites:
            assert services["services"][site]["networks"] == ["websites"]
            if site == "penpot":
                assert services["services"][site]["healthcheck"]["start_period"] == "180s"
                assert "disable-secure-session-cookies" in services["services"][site]["environment"]["PENPOT_FLAGS"]
            if site == "pipedrive":
                assert services["services"][site]["environment"]["NEXTAUTH_URL"] == episode["urls"][site]
        for name, service in services["services"].items():
            assert "ports" not in service
            assert "container_name" not in service
            if name not in {"webarena", "nextcloud"}:
                assert "volumes" not in service
            for mount in service.get("volumes", []):
                assert mount["type"] == "bind" and mount["read_only"] is True
                assert mount["bind"] == {"create_host_path": False}
                assert (root / "environment" / mount["source"]).is_file()
            assert "privileged" not in service
        # Neither build nor Harbor startup should copy private config into main.
        assert "COPY" not in (root / "environment/Dockerfile").read_text()
        assert (root / "environment/.dockerignore").read_text() == "**\n!Dockerfile\n"
    content = "\n".join(p.read_text() for p in out.rglob("*") if p.is_file())
    assert "DO-NOT-EXPORT-THIS-TOKEN" not in content
    assert "private-office.example" not in content
    assert "${WP_HARBOR_EVAL_TOKEN:" in content


def test_pinned_images_and_native_media(tmp_path, task):
    image = "example/jobportal@sha256:" + "a" * 64
    export_tasks(
        [task],
        tmp_path / "tasks",
        split="dev",
        images={"jobportal": image},
        max_steps=100,
        media=MediaSettings(profile="omni", audio=True, video=True, transcription="disabled"),
    )
    root = tmp_path / "tasks/webarena-pro-dev-fixture"
    config = json.loads((root / "environment/browser/episode.json").read_text())
    assert config["images"]["jobportal"] == image
    assert config["max_steps"] == 100
    assert config["media"]["profile"] == "omni"
    assert config["media"]["audio"] and config["media"]["video"]


def test_export_refuses_overwrite_and_unsafe_ids(tmp_path, task):
    out = tmp_path / "dataset"
    out.mkdir()
    (out / "keep").write_text("original")
    with pytest.raises(ValueError, match="already exists"):
        export_tasks([task], out, split="dev")
    assert (out / "keep").read_text() == "original"
    task.task_id = "../../escape"
    with pytest.raises(ValueError, match="directory"):
        export_tasks([task], tmp_path / "new", split="dev")
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("image", ["ubuntu\nRUN bad", "${TOKEN}", "image --build-arg=bad", ""])
def test_invalid_image_references(image):
    with pytest.raises(ValueError):
        validate_image(image)


def test_test_split_keeps_300_tasks(tmp_path):
    tasks = select_tasks("test", "all", None)
    assert len(export_tasks(tasks, tmp_path / "test", split="test")) == 300


def test_export_reuses_sidecar_images_and_keeps_task_local_files(tmp_path):
    tasks = select_tasks("dev", "nextcloud", None)[:2]
    assert len(tasks) == 2
    out = tmp_path / "exported"
    runtime = "example/runtime@sha256:" + "a" * 64
    nextcloud = "example/nextcloud@sha256:" + "b" * 64
    export_tasks(tasks, out, split="dev", runtime_image=runtime, images={"nextcloud": nextcloud})
    # A task directory remains usable after relocation; no absolute paths or
    # shared sibling build context tie it to the original exported dataset.
    relocated = tmp_path / "relocated"
    shutil.move(out, relocated)
    for task in tasks:
        env = relocated / f"webarena-pro-dev-{task.task_id}" / "environment"
        services = yaml.safe_load((env / "docker-compose.yaml").read_text())["services"]
        browser, site = services["webarena"], services["nextcloud"]
        assert browser["image"] == runtime and site["image"] == nextcloud
        assert "build" not in browser and "build" not in site
        assert not list((env / "browser").glob("Dockerfile"))
        assert not list((env / "nextcloud").glob("Dockerfile"))
        config = json.loads((env / browser["volumes"][0]["source"]).read_text())
        assert config["task"]["task_id"] == task.task_id
        assert browser["command"][-1] == browser["volumes"][0]["target"]
        assert site["entrypoint"] == ["sh", site["volumes"][0]["target"]]
        assert site["user"] == "root"
        assert site["command"] == ["apache2-foreground"]
        for service in (browser, site):
            for mount in service["volumes"]:
                assert mount["read_only"] and mount["bind"]["create_host_path"] is False
                assert (env / mount["source"]).resolve().is_relative_to(env.resolve())
                assert (env / mount["source"]).is_file()
                assert not mount["target"].startswith("/opt/webarena-seed")
        subprocess.run(["sh", "-n", str(env / "nextcloud/entrypoint.sh")], check=True)


@pytest.mark.parametrize("media,in_flight", [
    (MediaSettings(enabled=False), 60),
    (MediaSettings(transcription="disabled"), 180),
    (MediaSettings(), 900),
    (MediaSettings(transcription="local"), 900),
    (MediaSettings(transcription_timeout=1200), 1200),
    (MediaSettings(timeout=1200, transcription_timeout=900), 1200),
])
def test_grading_deadline_propagates_without_extending_agent_budget(tmp_path, task, media, in_flight):
    export_tasks(
        [task],
        tmp_path / "tasks",
        split="dev",
        wall_seconds=600,
        evaluation_timeout=900,
        media=media,
    )
    root = tmp_path / "tasks/webarena-pro-dev-fixture"
    episode = json.loads((root / "environment/browser/episode.json").read_text())
    config = tomllib.loads((root / "task.toml").read_text())
    assert episode["evaluation_timeout"] == 900
    assert episode["media"]["transcription_timeout"] == media.transcription_timeout
    assert episode["wall_seconds"] == 600 and episode["max_steps"] == 50
    assert config["agent"]["timeout_sec"] == 660
    collect = config["verifier"]["collect"][0]
    deadline = float(collect["command"].split()[-1])
    assert deadline >= 900 + in_flight + 120 + 120
    assert collect["timeout_sec"] > deadline


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_evaluation_deadline(task, timeout):
    with pytest.raises(ValueError, match="evaluation_timeout"):
        episode_config(task, evaluation_timeout=timeout)
