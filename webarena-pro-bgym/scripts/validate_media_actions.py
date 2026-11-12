"""Opt-in live Gemini media validation in isolated site containers.

Requires Docker, populated Acidwave/yt-lite images, Chromium, and GEMINI_API_KEY.
This makes paid model calls and resets only its newly created containers.

This harness records actions and provider payload metadata without logging keys
or base64 media. It does not inject actions or change task intents/evaluators.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

SOURCE = Path(__file__).resolve().parents[2]
MODEL = "gemini-3.5-flash"
ALIAS = "gemini/gemini-3.5-flash-omni"
TASKS = {"422": "acidwave", "398": "acidwave", "386": "yt-lite", "361": "yt-lite"}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def event(directory, kind, **data):
    with (directory / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"event": kind, "time": time.time(), **data}, default=str) + "\n")


def metadata(value):
    if isinstance(value, dict):
        return {key: metadata(item) for key, item in value.items()
                if not key.endswith("_b64") and key not in {"data", "bytes", "audio_segment"}}
    if isinstance(value, (list, tuple)):
        return [metadata(item) for item in value]
    if isinstance(value, bytes):
        return {"byte_count": len(value)}
    return value


def install_trace(directory):
    import httpx
    from agentlab.agents.generic_agent.generic_agent import GenericAgent

    original_send = httpx.Client.send
    calls = 0

    def traced_send(client, request, *args, **kwargs):
        nonlocal calls
        native = request.url.path.endswith(":generateContent")
        chat = request.url.path.endswith("/chat/completions")
        if not native and not chat:
            return original_send(client, request, *args, **kwargs)
        calls += 1
        call_id = calls
        body = json.loads(request.content)
        attachments = []
        if native:
            for content in body.get("contents", []):
                for part in content.get("parts", []):
                    inline = part.get("inlineData", part.get("inline_data"))
                    file_data = part.get("fileData", part.get("file_data"))
                    if inline:
                        raw = base64.b64decode(inline.get("data", ""))
                        attachments.append({"mime_type": inline.get("mimeType", inline.get("mime_type")),
                                            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                            "video_metadata": part.get("videoMetadata", part.get("video_metadata"))})
                    elif file_data:
                        attachments.append({"mime_type": file_data.get("mimeType", file_data.get("mime_type")),
                                            "file_reference": True,
                                            "video_metadata": part.get("videoMetadata", part.get("video_metadata"))})
        event(directory, "model_request", call=call_id, role="agent" if native else "judge",
              requested_model=MODEL if native else body.get("model"),
              endpoint=f"{request.url.scheme}://{request.url.host}{request.url.path}",
              attachments=attachments)
        started = time.monotonic()
        try:
            response = original_send(client, request, *args, **kwargs)
        except Exception as exc:
            event(directory, "model_error", call=call_id, error_type=type(exc).__name__)
            raise
        payload = response.json()
        texts = []
        if native:
            for candidate in payload.get("candidates", []):
                texts.extend(part["text"] for part in candidate.get("content", {}).get("parts", [])
                             if part.get("text") and not part.get("thought"))
        event(directory, "model_response", call=call_id, role="agent" if native else "judge",
              status_code=response.status_code, seconds=round(time.monotonic() - started, 3),
              returned_model=payload.get("modelVersion", payload.get("model")),
              usage=payload.get("usageMetadata", payload.get("usage")), texts=texts,
              finish_reasons=[candidate.get("finishReason") for candidate in payload.get("candidates", [])])
        return response

    httpx.Client.send = traced_send
    original_action = GenericAgent.get_action

    def traced_action(agent, obs, *args, **kwargs):
        clips = {key: metadata(value) for key, value in obs.items()
                 if ("clip" in key or key in {"extracted_frames", "watch_results"}) and value}
        event(directory, "observation", media=clips)
        result = original_action(agent, obs, *args, **kwargs)
        action = result[0] if isinstance(result, tuple) else result
        event(directory, "agent_action", action=action)
        return result

    GenericAgent.get_action = traced_action


def worker(args):
    directory = Path(args.directory)
    install_trace(directory)
    from webarena_pro_bgym.run_cli import main
    from webarena_pro_bgym.run_eval_cli import _build_agent
    from webarena_pro_core.state_reset import wait_until_site_ready

    site = TASKS[args.task]
    model_args = _build_agent(ALIAS).chat_model_args
    assert model_args.model_name == MODEL
    assert model_args.audio_support and model_args.video_support
    event(directory, "configuration", requested_model=MODEL, alias=ALIAS, task=args.task,
          site=site, audio_support=True, video_support=True, max_steps=args.max_steps)
    wait_until_site_ready(site, timeout_seconds=240)
    return main(["--split", "dev", "--site", site, "--task", args.task,
                 "--agent-model", ALIAS, "--max-steps", str(args.max_steps),
                 "--n-jobs", "1", "--n-relaunch", "1", "--no-autostart",
                 "--no-reset-per-task", "--study-dir", str(directory / "results")])


def run_task(args, task_id):
    from dotenv import dotenv_values

    site = TASKS[task_id]
    directory = Path(args.output_dir).resolve() / args.run_id / task_id
    directory.mkdir(parents=True, exist_ok=False)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("WP_", "OPENAI_", "VLLM_", "GEMINI_", "GOOGLE_", "OPENROUTER_", "WEBARENAPRO_"))}
    key = os.environ.get("GEMINI_API_KEY")
    if not key and args.env_file:
        key = dotenv_values(args.env_file).get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Configured Gemini credential is unavailable")
    token = secrets.token_urlsafe(32)
    name = f"issue127-{args.run_id}-{task_id}"
    image = args.acidwave_image if site == "acidwave" else args.yt_lite_image
    container_port = 80 if site == "acidwave" else 7860
    state = {"requested_model": MODEL, "alias": ALIAS, "site": site, "task": task_id,
             "split": "dev", "max_steps": args.max_steps, "image": image,
             "container": name, "started": time.time(), "status": "starting",
             "fresh_container_per_task": True, "source_revision": args.revision}
    save(directory / "status.json", state)
    created = False
    try:
        container_env = dict(os.environ, WP_EVAL_TOKEN=token)
        subprocess.run(["docker", "run", "-d", "--name", name,
                        "--label", "codex.validation=issue127-listen-watch",
                        "-p", f"127.0.0.1::{container_port}", "-e", "WP_EVAL_TOKEN", image],
                       env=container_env, text=True, capture_output=True, check=True, timeout=180)
        created = True
        inspect = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
        state["image"] = inspect["Image"]
        port = inspect["NetworkSettings"]["Ports"][f"{container_port}/tcp"][0]["HostPort"]
        prefix = site.upper().replace("-", "_")
        env.update(PYTHONUNBUFFERED="1", PYTHONPATH=":".join(str(SOURCE / part / "src")
                   for part in ("webarena-pro-bgym", "webarena-pro-core")),
                   GEMINI_API_KEY=key, GEMINI_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/",
                   WEBARENAPRO_LLM_JUDGE_MODEL=MODEL, WP_URL_MODE="port", WP_EXP_HASH=name,
                   WP_EVAL_TOKEN=token, WP_RESET_BACKEND="none", WP_PREWARM_CONTAINERS="0",
                   WP_RESET_CONTAINER_PER_TASK="0", WEBARENA_PRO_STEP_TIMEOUT_SECONDS="300",
                   WEBARENA_PRO_RESET_TIMEOUT_SECONDS="300")
        env[f"WP_{prefix}_CONTAINER_NAME"] = name
        env[f"WP_{prefix}_URL"] = f"http://127.0.0.1:{port}"
        env[f"WP_{prefix}_HOST_PORT"] = port
        state["url"] = env[f"WP_{prefix}_URL"]
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--task", task_id,
                   "--directory", str(directory), "--max-steps", str(args.max_steps)]
        with (directory / "run.log").open("w") as log:
            process = subprocess.Popen(command, env=env, cwd=SOURCE / "webarena-pro-bgym",
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            state.update(status="running", pid=process.pid, command=command)
            save(directory / "status.json", state)
            try:
                state["exit_code"] = process.wait(timeout=args.timeout)
                state["status"] = "finished"
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                state.update(status="timed_out", exit_code=process.returncode)
    except Exception as exc:
        state.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        if created:
            logs = subprocess.run(["docker", "logs", name], text=True, capture_output=True, timeout=60)
            (directory / "container.log").write_text(logs.stdout + logs.stderr)
            state["container_removed"] = subprocess.run(["docker", "rm", "-f", name],
                capture_output=True, timeout=120).returncode == 0
        state["finished"] = time.time()
        summaries = []
        for path in directory.glob("results/**/summary_info.json"):
            summary = json.loads(path.read_text())
            summaries.append({"path": str(path), "n_steps": summary.get("n_steps"),
                              "reward": summary.get("cum_reward"), "error": summary.get("err_msg"),
                              "terminated": summary.get("terminated"), "truncated": summary.get("truncated")})
        state["episodes"] = summaries
        save(directory / "status.json", state)
    print(json.dumps({"task": task_id, "status": state["status"], "episodes": state["episodes"]}), flush=True)
    trace = directory / "events.jsonl"
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    expected_action = "listen(" if site == "acidwave" else "watch("
    expected_mime = "audio/wav" if site == "acidwave" else "video/mp4"
    actions = [str(e.get("action", "")) for e in events if e["event"] == "agent_action"]
    successful_calls = {e["call"] for e in events if e["event"] == "model_response"
                        and e.get("status_code") == 200}
    delivered = any(e["event"] == "model_request" and e["call"] in successful_calls
                    and any(a.get("mime_type") == expected_mime for a in e.get("attachments", []))
                    for e in events)
    state["media_delivery_verified"] = delivered and any(expected_action in a for a in actions)
    state["task_success"] = bool(state["episodes"]) and all(
        e.get("reward") == 1 and not e.get("error") for e in state["episodes"])
    save(directory / "status.json", state)
    return int(bool(state.get("exit_code", 1)) or not state["media_delivery_verified"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--task", choices=list(TASKS))
    parser.add_argument("--directory")
    parser.add_argument("--run-id", default="run1")
    parser.add_argument("--output-dir", help="Directory for sanitized traces and local raw episode artifacts")
    parser.add_argument("--env-file", help="Optional explicit dotenv file containing GEMINI_API_KEY")
    parser.add_argument("--acidwave-image", default="webarenapro/acidwave:latest")
    parser.add_argument("--yt-lite-image", default="webarenapro/yt-lite:latest")
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=2400)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if not args.output_dir:
        parser.error("--output-dir is required")
    if not args.run_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_id):
        parser.error("--run-id must contain only letters, digits, hyphens and underscores")
    selected = [args.task] if args.task else list(TASKS)
    failures = 0
    for task_id in selected:
        failures += bool(run_task(args, task_id))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
