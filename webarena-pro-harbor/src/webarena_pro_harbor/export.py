"""Generate self-contained Harbor tasks without changing benchmark content."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from importlib.resources import files
from pathlib import Path

import yaml
from webarena_pro_core import WEBSITES_CONTAINER_PORTS, WEBSITES_IMAGES, site_env_var_key
from webarena_pro_core.state_reset import site_container_run_overrides
from webarena_pro_mcp.media_policy import MediaSettings

TOKEN = "${WP_HARBOR_EVAL_TOKEN:?Set WP_HARBOR_EVAL_TOKEN to a private random value}"
EVIDENCE = "/webarena-evidence"
CONTROL = "/run/webarena/control.sock"


def validate_image(image):
    # Image references enter Compose and build commands; reject whitespace,
    # expansion, and newlines rather than interpreting executable syntax.
    if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@-]*", image):
        raise ValueError(f"Invalid image reference: {image!r}")
    return image


def application_environments(urls):
    # Core supports site-specific optional deployment overrides. Export with a
    # clean process environment so the author's local .env and tokens cannot
    # enter task packages. Token interpolation is deferred to Compose runtime.
    code = (
        "import json,sys; from webarena_pro_core import website_environment; "
        "data=json.load(sys.stdin); print(json.dumps({site:website_environment("
        "site,public_url=url,eval_token=data['token']) or {} "
        "for site,url in data['urls'].items()}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps({"urls": urls, "token": TOKEN}),
        text=True,
        capture_output=True,
        check=True,
        env={"PATH": os.environ.get("PATH", "")},
    )
    return json.loads(result.stdout)


def episode_config(
    task, *, max_steps=50, wall_seconds=1800, evaluation_timeout=300, media=None, images=None,
    record_screenshots=False,
):
    if type(max_steps) is not int or max_steps not in {-1, 50, 100}:
        raise ValueError("max_steps must be 50, 100, or -1 (unlimited)")
    if not math.isfinite(wall_seconds) or wall_seconds <= 0:
        raise ValueError("wall_seconds must be finite and positive")
    if not math.isfinite(evaluation_timeout) or evaluation_timeout <= 0:
        raise ValueError("evaluation_timeout must be finite and positive")
    if not task.raw_task or not task.evaluation or not task.evaluation.get("nodes"):
        raise ValueError(f"Task {task.task_id} has no supported Core DAG")
    selected_images = {
        site: validate_image((images or {}).get(site, WEBSITES_IMAGES[site])) for site in task.sites
    }
    return {
        "schema_version": 1,
        "task": task.raw_task,
        "urls": {site: f"http://{site}:{WEBSITES_CONTAINER_PORTS[site]}" for site in task.sites},
        "images": selected_images,
        "max_steps": max_steps,
        "wall_seconds": wall_seconds,
        "setup_timeout": 1800,
        "tool_timeout": 60,
        "evaluation_timeout": evaluation_timeout,
        "record_screenshots": bool(record_screenshots),
        "media": (media or MediaSettings()).as_dict(),
    }


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def readonly_file(source, target):
    # Relative sources keep copied task directories portable. Refuse missing
    # files instead of silently creating a host directory at the mount source.
    return {
        "type": "bind",
        "source": source,
        "target": target,
        "read_only": True,
        "bind": {"create_host_path": False},
    }


def compose(config, runtime_image, app_env, environment_dir):
    urls = config["urls"]
    private_env = {
        "WP_EVAL_TOKEN": TOKEN,
        "WEBARENAPRO_LLM_JUDGE_MODEL": "${WP_HARBOR_JUDGE_MODEL:-qwen/qwen3.6-27b}",
        "WEBARENAPRO_LLM_JUDGE_STREAM": "${WP_HARBOR_JUDGE_STREAM:-0}",
        "WEBARENA_PRO_ASR_API_KEY": "${WP_HARBOR_ASR_API_KEY:-}",
        "WEBARENA_PRO_ASR_BASE_URL": "${WP_HARBOR_ASR_BASE_URL:-https://api.openai.com/v1}",
    }
    # The user selects the judge independently of the Harbor agent. Core chooses
    # the appropriate provider from its normal model routing rules.
    for provider in ("OPENAI", "OPENROUTER", "VLLM", "GEMINI"):
        private_env[f"{provider}_API_KEY"] = "${WP_HARBOR_JUDGE_API_KEY:-}"
    defaults = {
        "OPENAI": "https://api.openai.com/v1",
        "OPENROUTER": "https://openrouter.ai/api/v1",
        "GEMINI": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "VLLM": "http://localhost:8000/v1",
    }
    for provider, default in defaults.items():
        private_env[f"{provider}_BASE_URL"] = "${WP_HARBOR_JUDGE_BASE_URL:-" + default + "}"
    private_env.update({f"WP_{site_env_var_key(s)}_URL": u for s, u in urls.items()})
    services = {
        "main": {
            "networks": ["default"],
            "depends_on": {"webarena": {"condition": "service_healthy"}},
        },
        "webarena": {
            "image": validate_image(runtime_image),
            "command": [
                "webarena-pro-harbor", "supervise", "--config", "/opt/webarena/episode.json"
            ],
            "volumes": [
                readonly_file("./browser/episode.json", "/opt/webarena/episode.json")
            ],
            "init": True,
            "shm_size": "1gb",
            "networks": ["default", "websites"],
            "environment": private_env,
            "depends_on": {
                site: {"condition": "service_healthy" if site == "peppermint" else "service_started"}
                for site in urls
            },
            "healthcheck": {
                "test": [
                    "CMD",
                    "webarena-pro-harbor", "healthcheck",
                ],
                "interval": "5s",
                "timeout": "3s",
                "retries": 360,
            },
        },
    }
    for site in urls:
        service = {
            "image": config["images"][site],
            "platform": "linux/amd64",
            "networks": ["websites"],
            "environment": app_env[site],
            **site_container_run_overrides(site),
        }
        if site == "mattermost":
            service["environment"].update(
                {
                    "MM_CALLS_ICE_HOST_OVERRIDE": "mattermost",
                    "MM_CALLS_ICE_HOST_PORT_OVERRIDE": "8443",
                }
            )
        if site == "peppermint":
            # Override older images too: the frontend can answer while the API
            # is still starting. The auth check is public and 401 means ready.
            probe = files("webarena_pro_harbor").joinpath("templates/peppermint-healthcheck.sh").read_text()
            service["healthcheck"] = {
                "test": ["CMD-SHELL", probe.replace("$", "$$")],
                "interval": "5s",
                "timeout": "8s",
                # Docker treats zero as inheriting the image's start period.
                "start_period": "1s",
                # Docker waits an interval after each probe, so include its
                # maximum duration rather than treating retries as seconds.
                "retries": max(1, math.floor(config["setup_timeout"] / (5 + 8))),
            }
        if site == "penpot":
            # Its bundled JVM/database can take longer than the image's
            # one-minute health window when several trials start together.
            service["healthcheck"] = {"start_period": "180s"}
        if site == "nextcloud":
            # Reuse the configured site image. Each trial keeps its own writable
            # seed tree; only these small, task-local configuration files mount
            # from the host. Never mount over the image's preseeded snapshot.
            service["user"] = "root"
            service["entrypoint"] = ["sh", "/run/webarena/nextcloud-entrypoint.sh"]
            service["command"] = ["apache2-foreground"]
            service["volumes"] = [
                readonly_file(
                    "./nextcloud/entrypoint.sh", "/run/webarena/nextcloud-entrypoint.sh"
                ),
                readonly_file(
                    "./nextcloud/opcache-recommended.ini",
                    "/usr/local/etc/php/conf.d/opcache-recommended.ini",
                ),
            ]
            write(
                environment_dir / "nextcloud/entrypoint.sh",
                '#!/bin/sh\nset -eu\n'
                'mkdir -p /opt/webarena-seed\n'
                'chown www-data:www-data /opt/webarena-seed\n'
                'if [ -x /seedDir/docker-entrypoint-preseeded.sh ]; then\n'
                '  exec /seedDir/docker-entrypoint-preseeded.sh "$@"\n'
                'fi\n'
                'exec /entrypoint.sh "$@"\n',
            )
            write(
                environment_dir / "nextcloud/opcache-recommended.ini",
                "opcache.jit=0\nopcache.jit_buffer_size=0\n",
            )
        services[site] = service
    return {"services": services, "networks": {"default": {}, "websites": {"internal": True}}}


def export_tasks(
    tasks,
    output,
    *,
    split,
    runtime_image="webarena-pro-harbor:local",
    max_steps=50,
    wall_seconds=1800,
    evaluation_timeout=300,
    media=None,
    images=None,
    record_screenshots=False,
):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"Output already exists; choose a new directory: {output}")
    validate_image(runtime_image)
    configs = [
        episode_config(
            t,
            max_steps=max_steps,
            wall_seconds=wall_seconds,
            evaluation_timeout=evaluation_timeout,
            media=media,
            images=images,
            record_screenshots=record_screenshots,
        )
        for t in tasks
    ]
    urls = {site: url for cfg in configs for site, url in cfg["urls"].items()}
    app_env = application_environments(urls)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".harbor-export-", dir=output.parent))
    manifest = []
    try:
        for task, cfg in zip(tasks, configs, strict=True):
            # Wait for any in-flight action, two evidence queries, Core grading,
            # and the supervisor's 120-second diagnostics deadline plus overhead.
            media_settings = cfg["media"]
            media_timeout = 0
            if media_settings["enabled"]:
                media_timeout = media_settings["timeout"]
                if media_settings["transcription"] != "disabled":
                    media_timeout = max(media_timeout, media_settings["transcription_timeout"])
            in_flight = max(cfg["tool_timeout"], media_timeout)
            collect_timeout = math.ceil(
                in_flight + 2 * cfg["tool_timeout"] + cfg["evaluation_timeout"] + 120 + 30
            )
            if not re.fullmatch(r"[A-Za-z0-9_-]+", task.task_id):
                raise ValueError("Task IDs must be safe directory names")
            name = f"webarena-pro-{split}-{task.task_id}"
            root = staging / name
            env = root / "environment"
            serialized = json.dumps(cfg, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            digest = hashlib.sha256(serialized.encode()).hexdigest()
            instruction = task.intent + "\n\n"
            instruction += "The task websites are already initialized and signed in to the required accounts.\n"
            instruction += "Use the WebArena-Pro MCP tools for all website interactions.\n"
            instruction += "\n".join(f"- {s}: {u}" for s, u in cfg["urls"].items()) + "\n\n"
            budget = "unlimited" if max_steps == -1 else str(max_steps)
            instruction += f"Action budget: {budget}. Browser mutations and media processing cost one action. "
            instruction += "Snapshots, screenshots, find queries, tab listings, and final submission are free. "
            instruction += "Finish by calling webarena_submit with your final answer, including after the last allowed action. "
            instruction += "Text written only in your agent's final chat response is not submitted to the evaluator. "
            instruction += "After submission or wall-time exhaustion, stop calling tools.\n"
            write(root / "instruction.md", instruction)
            write(
                env / "Dockerfile",
                "FROM node:22-bookworm-slim\nRUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git curl ca-certificates && rm -rf /var/lib/apt/lists/*\nWORKDIR /workspace\n",
            )
            write(env / ".dockerignore", "**\n!Dockerfile\n")
            write(env / "browser/episode.json", serialized)
            # Deep copy: per-task overrides must not mutate cached site settings.
            services = compose(cfg, runtime_image, json.loads(json.dumps(app_env)), env)
            write(env / "docker-compose.yaml", yaml.safe_dump(services, sort_keys=False))
            write(
                root / "task.toml",
                f'''version = "1.0"
artifacts = [{{ source = "{EVIDENCE}", service = "webarena" }}, {{ source = "/webarena-service", service = "webarena" }}]

[task]
name = "webarena-pro/{split}-{task.task_id}"
description = "WebArena-Pro task {task.task_id} ({split})"
keywords = ["browser", "webarena-pro", "mcp"]

[metadata]
task_id = "{task.task_id}"
split = "{split}"
config_sha256 = "{digest}"

[agent]
timeout_sec = {float(wall_seconds) + 60}

[environment]
build_timeout_sec = 2400.0
cpus = 2
memory_mb = 4096
storage_mb = 20480

[[environment.mcp_servers]]
name = "webarena-pro"
transport = "streamable-http"
url = "http://webarena:8000/mcp"

[verifier]
timeout_sec = 60.0
environment_mode = "separate"

[[verifier.collect]]
service = "webarena"
command = "webarena-pro-harbor finalize --timeout {collect_timeout}"
timeout_sec = {float(collect_timeout + 20)}
''',
            )
            write(
                root / "tests/Dockerfile",
                "FROM python:3.12-slim-bookworm\nCOPY . /tests/\nWORKDIR /tests\n",
            )
            write(root / "tests/test.sh", "#!/bin/sh\nset -eu\npython /tests/verify.py\n")
            write(
                root / "tests/verify.py",
                files("webarena_pro_harbor").joinpath("verify.py").read_text(),
            )
            (root / "tests/test.sh").chmod(0o755)
            manifest.append(
                {
                    "task": name,
                    "task_id": task.task_id,
                    "config_sha256": digest,
                    "images": cfg["images"],
                }
            )
        write(
            staging / "manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "split": split,
                    "runtime_image": runtime_image,
                    "tasks": manifest,
                },
                indent=2,
            )
            + "\n",
        )
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return manifest
