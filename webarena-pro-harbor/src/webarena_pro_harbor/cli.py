"""Authoring commands and private runtime entrypoints."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from webarena_pro_mcp.media_policy import MediaSettings

from .export import CONTROL, EVIDENCE, export_tasks, validate_image


def select_tasks(split, sites, task_ids):
    from webarena_pro_core.task import load_task_configs

    tasks = load_task_configs(split=split, sites=sites.split(",") if sites != "all" else "all")
    if task_ids:
        wanted = {value.strip().zfill(3) for value in task_ids.split(",")}
        selected = [task for task in tasks if task.task_id in wanted]
        missing = wanted - {task.task_id for task in selected}
        if missing:
            raise ValueError("Tasks not found in selected split/sites: " + ", ".join(sorted(missing)))
        tasks = selected
    if not tasks:
        raise ValueError("No tasks selected")
    return tasks


def build_runtime(source_root, tag, platform=None):
    validate_image(tag)
    root = Path(source_root).resolve()
    with tempfile.TemporaryDirectory(prefix="webarena-harbor-build-") as directory:
        context = Path(directory)
        wheels = context / "wheels"
        wheels.mkdir()
        for name in (
            "webarena-pro-core",
            "webarena-pro-media",
            "webarena-pro-mcp",
            "webarena-pro-harbor",
        ):
            package = root / name
            if not (package / "pyproject.toml").is_file():
                raise ValueError(
                    f"Missing package at {package}; pass --source-root pointing at this repository"
                )
            subprocess.run(
                ["uv", "build", "--wheel", "--out-dir", str(wheels), str(package)], check=True
            )
        (context / "Dockerfile").write_text(
            files("webarena_pro_harbor").joinpath("templates/Dockerfile").read_text()
        )
        command = ["docker", "build", "--tag", tag]
        if platform:
            command += ["--platform", platform]
        subprocess.run([*command, str(context)], check=True)


def parser():
    p = argparse.ArgumentParser(description="Export and serve native WebArena-Pro Harbor tasks")
    commands = p.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    export = commands.add_parser("export")
    for item in (listing, export):
        item.add_argument("--split", choices=("dev", "test"), default="dev")
        item.add_argument("--site", default="all")
        item.add_argument("--task", help="Comma-separated task IDs")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--runtime-image", default="webarena-pro-harbor:local")
    export.add_argument("--max-steps", type=int, choices=(50, 100, -1), default=50)
    export.add_argument("--wall-seconds", type=float, default=1800)
    export.add_argument(
        "--evaluation-timeout",
        type=float,
        default=300,
        help="Private Core grading deadline in seconds, separate from the agent budget",
    )
    export.add_argument(
        "--image-map", type=Path, help="JSON mapping site IDs to pinned Docker image references"
    )
    export.add_argument("--browser-only", action="store_true")
    export.add_argument(
        "--record-screenshots", action="store_true",
        help="Save private screenshots at startup and after each action for trace inspection",
    )
    export.add_argument("--transcription-backend", choices=("api", "disabled"), default="api")
    export.add_argument(
        "--native-audio",
        action="store_true",
        help="Enable native WAV audio; agent/model must support MCP audio",
    )
    export.add_argument(
        "--native-video",
        action="store_true",
        help="Enable native MP4 video; agent/model must support MCP video",
    )
    build = commands.add_parser("build-runtime")
    build.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[3])
    build.add_argument("--tag", default="webarena-pro-harbor:local")
    build.add_argument("--platform")
    networks = commands.add_parser(
        "preflight-networks", help="Probe Docker capacity before starting a Harbor study"
    )
    networks.add_argument("--concurrency", type=int, default=1,
                          help="Concurrent Harbor trials (the same value as harbor run -n)")
    networks.add_argument("--timeout", type=float, default=120,
                          help="Allocation deadline in seconds; cleanup gets up to 30 more seconds")
    from .service import DIAGNOSTICS

    for command in ("serve", "supervise"):
        serve = commands.add_parser(command, help="Private browser-service entrypoint")
        serve.add_argument("--config", type=Path, required=True)
        serve.add_argument("--directory", type=Path, default=Path(EVIDENCE))
        serve.add_argument("--socket", type=Path, default=Path(CONTROL))
        serve.add_argument("--port", type=int, default=8000)
        if command == "supervise":
            serve.add_argument("--diagnostics", type=Path, default=Path(DIAGNOSTICS))
    health = commands.add_parser("healthcheck", help="Record private browser health diagnostics")
    health.add_argument("--directory", type=Path, default=Path(DIAGNOSTICS))
    health.add_argument("--port", type=int, default=8000)
    finalize = commands.add_parser(
        "finalize", help="Private Harbor collection hook; requires service filesystem access"
    )
    finalize.add_argument("--socket", type=Path, default=Path(CONTROL))
    finalize.add_argument("--timeout", type=float, default=360)
    return p


def main():
    p = parser()
    args = p.parse_args()
    try:
        if args.command in {"list", "export"}:
            tasks = select_tasks(args.split, args.site, args.task)
            if args.command == "list":
                print(
                    json.dumps(
                        [
                            {"task_id": t.task_id, "sites": t.sites, "intent": t.intent}
                            for t in tasks
                        ],
                        indent=2,
                    )
                )
            else:
                if args.browser_only and (args.native_audio or args.native_video):
                    raise ValueError("--browser-only cannot be combined with native media")
                manifest = export_tasks(
                    tasks,
                    args.output,
                    split=args.split,
                    runtime_image=args.runtime_image,
                    max_steps=args.max_steps,
                    wall_seconds=args.wall_seconds,
                    evaluation_timeout=args.evaluation_timeout,
                    images=json.loads(args.image_map.read_text()) if args.image_map else None,
                    record_screenshots=args.record_screenshots,
                    media=MediaSettings(
                        enabled=not args.browser_only,
                        profile="omni" if args.native_audio or args.native_video else "standard",
                        audio=args.native_audio,
                        video=args.native_video,
                        transcription=args.transcription_backend,
                    ),
                )
                print(f"Exported {len(manifest)} tasks to {args.output.resolve()}")
        elif args.command == "build-runtime":
            build_runtime(args.source_root, args.tag, args.platform)
        elif args.command == "preflight-networks":
            from .network_preflight import preflight_networks

            result = preflight_networks(args.concurrency, args.timeout)
            print(
                f"Docker allocated and released {result['networks']} networks for "
                f"{result['concurrency']} concurrent trials. Capacity is point-in-time, "
                "not reserved; run Harbor against the same Docker context."
            )
        elif args.command == "supervise":
            from .service import supervise

            raise SystemExit(supervise(args.config, args.directory, args.socket, args.port, args.diagnostics))
        elif args.command == "healthcheck":
            from .service import healthcheck

            raise SystemExit(healthcheck(args.directory, args.port))
        elif args.command == "serve":
            from webarena_pro_mcp.server import serve

            asyncio.run(serve(args.config, args.directory, args.socket, args.port, host="0.0.0.0"))
        elif args.command == "finalize":
            from webarena_pro_mcp.server import finalize

            asyncio.run(finalize(args.socket, args.timeout))
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
