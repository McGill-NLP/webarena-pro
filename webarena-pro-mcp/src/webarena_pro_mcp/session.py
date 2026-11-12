"""One serialized, agent-independent episode and its private Core evidence."""

from __future__ import annotations

import asyncio
import base64
import copy
import json
import math
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from webarena_pro_core.task import WebArenaProTaskConfig
from webarena_pro_mcp.artifacts import Artifacts, safe_error
from webarena_pro_mcp.evaluation import ScoreBook, grade
from webarena_pro_mcp.mcp_client import connect, text_content
from webarena_pro_mcp.media_policy import MediaSettings
from webarena_pro_mcp.supervisor import Supervisor
from webarena_pro_mcp.tool_policy import PolicyError, ToolPolicy

SUBMIT = {
    "name": "webarena_submit",
    "description": "Finish the task and submit your final answer. Submission does not cost an action and remains available after the last action. No score is disclosed.",
    "inputSchema": {
        "type": "object",
        "properties": {"answer": {"type": "string", "maxLength": 100000}},
        "required": ["answer"],
        "additionalProperties": False,
    },
}

RATIONALE = "webarena_rationale"
OBSERVATION_TOOLS = {"browser_snapshot", "browser_take_screenshot", "browser_find"}


def costs_action(name, arguments):
    return name not in OBSERVATION_TOOLS | {SUBMIT["name"]} and not (
        name == "browser_tabs" and arguments.get("action") == "list"
    )


def message(text, *, error=False):
    return {"content": [{"type": "text", "text": text}], "isError": error}


def normalize_config(config):
    """Validate a private session configuration before starting any resources."""
    if not isinstance(config, dict) or config.get("schema_version", 1) != 1:
        raise ValueError("Expected a version 1 session configuration")
    config = dict(config)
    raw = config.get("task")
    evaluation = raw.get("eval") if isinstance(raw, dict) else None
    if not isinstance(evaluation, dict) or not evaluation.get("nodes"):
        raise ValueError("Session task must include a Core evaluation DAG")
    task = WebArenaProTaskConfig.from_raw_task(raw, container_name="external-owned")
    urls = config.get("urls")
    if not isinstance(urls, dict) or set(urls) != set(task.sites):
        raise ValueError("Session URLs must cover exactly the task websites")
    for url in urls.values():
        if not isinstance(url, str):
            raise ValueError("Session URLs must be HTTP(S) URLs")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Session URLs must be HTTP(S) URLs without embedded credentials")
    config["urls"] = dict(urls)
    config.setdefault("max_steps", 50)
    if type(config["max_steps"]) is not int or (config["max_steps"] != -1 and config["max_steps"] < 1):
        raise ValueError("max_steps must be a positive integer or -1")
    for name, default in {
        "wall_seconds": 1800, "tool_timeout": 60,
        "evaluation_timeout": 300, "setup_timeout": 1800,
    }.items():
        value = config.setdefault(name, default)
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    try:
        config["media"] = MediaSettings(**config.get("media", {})).as_dict()
    except TypeError as exc:
        raise ValueError("Invalid media configuration") from exc
    return config


class Session:
    def __init__(self, browser, supervisor, artifacts, config):
        self.browser, self.supervisor, self.artifacts = browser, supervisor, artifacts
        self.config = config
        self.lock = asyncio.Lock()
        self.steps = 0
        self.calls = 0
        self.trajectory = []
        self.current_url = ""
        self.evaluation_revision = 0
        self.graded_revision = None
        self.last_action = None
        self.answer = None
        self.closed = False
        self.failure = None
        self.result = None
        self.book = ScoreBook(config["max_steps"])
        self.deadline = None
        self.tools = {tool["name"]: copy.deepcopy(tool) for tool in [*browser.tools, SUBMIT]}
        for tool in self.tools.values():
            tool["inputSchema"].setdefault("properties", {})[RATIONALE] = {
                "type": "string", "maxLength": 10000,
                "description": "Optional brief explanation of this action, saved for evaluation; never sent to the browser/media tool.",
            }

    async def _record(self, action, result, *, deadline, rationale=None, counted=False):
        # Query browser-owned tab state, including for media and submit results
        # that have no snapshot header. Retain only a previously validated URL
        # if diagnostic capture is temporarily unavailable.
        url_source = "retained"
        try:
            remaining = min(5, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("No tool time remains for URL capture")
            self.current_url = await asyncio.wait_for(
                self.browser.current_url(), remaining
            )
            url_source = "browser"
        except Exception:
            pass
        except asyncio.CancelledError as exc:
            self.failure = safe_error(exc)
            self.artifacts.write("failure.json", {"status": "environment_error", "error": self.failure})
            raise
        obs = {"url": self.current_url, "url_source": url_source, "axtree_txt": text_content(result)}
        self.last_action = action
        entry = {"step": self.steps, "call": self.calls, "counted": counted, "action": action, "obs": obs}
        if rationale is not None:
            entry["agent_info"] = {"think": rationale}
        self.trajectory.append(entry)
        self.artifacts.append("trajectory.jsonl", self.trajectory[-1])

    async def capture_screenshot(self, existing=None):
        """Record visual evidence privately, without adding an agent action or input."""
        if not self.config.get("record_screenshots", False):
            return
        started = time.monotonic()
        record = {
            "step": self.steps,
            "call": self.calls,
            "phase": "initial" if self.calls == 0 else "after_action",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            remaining = 5 if self.deadline is None else min(5, self.deadline - started)
            if remaining <= 0:
                raise TimeoutError("No episode time remains for a screenshot")
            result = existing or await asyncio.wait_for(
                self.browser.call("browser_take_screenshot", {"scale": "css", "fullPage": False}),
                remaining,
            )
            if result.get("isError"):
                raise RuntimeError("Browser screenshot was unavailable")
            block = next(p for p in result.get("content", []) if p.get("type") == "image")
            data = base64.b64decode(block["data"], validate=True)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError("Screenshot exceeds the 20 MiB evidence limit")
            if block.get("mimeType") == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
                suffix = "png"
            elif block.get("mimeType") == "image/jpeg" and data.startswith(b"\xff\xd8\xff"):
                suffix = "jpg"
            else:
                raise ValueError("Unsupported screenshot image")
            call_suffix = f"-call-{self.calls:06d}" if self.calls else ""
            relative = f"screenshots/step-{self.steps:06d}{call_suffix}.{suffix}"
            path = self.artifacts.root / relative
            path.parent.mkdir(mode=0o700, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o600)
            record.update(status="captured", image_file=relative)
        except Exception as exc:
            # Missing diagnostic evidence must not change the original action or grade.
            record.update(status="unavailable", error=safe_error(exc))
        record["elapsed_seconds"] = time.monotonic() - started
        self.artifacts.append("screenshots.jsonl", record)

    async def _add_visual_observation(self, result, deadline):
        """Supplement a completed action outside its authoritative timeout."""
        try:
            remaining = min(5, deadline - time.monotonic())
            if remaining <= 0:
                raise TimeoutError("No episode time remains for a screenshot")
            screenshot = await asyncio.wait_for(
                self.browser.call("browser_take_screenshot", {"scale": "css", "fullPage": False}),
                remaining,
            )
            if screenshot.get("isError"):
                raise RuntimeError("Screenshot capture returned an error")
            images = [p for p in screenshot.get("content", []) if p.get("type") == "image"]
            if not images:
                raise RuntimeError("Screenshot capture returned no image")
            result["automatic_screenshot"] = screenshot
            result["content"].extend(images)
        except Exception:
            result["automatic_screenshot"] = message("Post-action screenshot unavailable", error=True)
            result["content"].append({
                "type": "text", "text": "Post-action screenshot unavailable; request browser_take_screenshot to retry without spending an action."
            })
        except asyncio.CancelledError as exc:
            # An external cancellation still aborts the trial. Only this
            # diagnostic capture's own TimeoutError is recoverable.
            self.failure = safe_error(exc)
            self.artifacts.write("failure.json", {"status": "environment_error", "error": self.failure})
            raise

    async def _grade(self, *, terminal=False):
        started = time.monotonic()
        state = {
            "step": self.steps,
            "terminal": terminal,
            "timeout_seconds": self.config["evaluation_timeout"],
        }
        self.artifacts.write("evaluation-state.json", {**state, "status": "running"})
        try:
            evaluation, evidence = await grade(
                self.browser,
                self.supervisor,
                self.trajectory,
                self.last_action,
                self.config["evaluation_timeout"],
                artifacts=self.artifacts,
            )
        except BaseException as exc:
            self.artifacts.write(
                "evaluation-state.json",
                {
                    **state,
                    "status": "error",
                    "elapsed_seconds": time.monotonic() - started,
                    "error": safe_error(exc),
                },
            )
            raise
        self.book.record(self.steps, evaluation, terminal=terminal)
        self.graded_revision = self.evaluation_revision
        self.artifacts.write(
            f"evaluation-{self.steps}.json", {**evaluation, "observation": evidence}
        )
        self.artifacts.write(
            "evaluation-state.json",
            {
                **state,
                "status": "graded",
                "elapsed_seconds": time.monotonic() - started,
            },
        )

    async def call(self, name, arguments):
        # A client can reconnect or send concurrent requests. Neither creates a
        # new episode, bypasses the budget, nor interleaves a grader with an action.
        async with self.lock:
            if self.closed or self.failure or self.answer is not None:
                return message("The episode has ended. Stop using tools.", error=True)
            if self.deadline is None:
                self.deadline = time.monotonic() + self.config["wall_seconds"]
            if time.monotonic() >= self.deadline:
                self.closed = True
                return message(
                    "The episode time budget is exhausted. Stop using tools.", error=True
                )
            limit = self.config["max_steps"]
            observation_deadline = min(self.deadline, time.monotonic() + self.config["tool_timeout"])
            self.calls += 1
            counted = False
            rationale = None
            action = f"{name}({json.dumps(arguments, ensure_ascii=False)})"
            self.artifacts.append(
                "calls.jsonl", {"step": self.steps, "call": self.calls, "action": action, "status": "started"}
            )
            try:
                definition = self.tools.get(name)
                if definition is None or list(
                    Draft202012Validator(definition["inputSchema"]).iter_errors(arguments)
                ):
                    raise PolicyError("Unknown tool or invalid arguments")
                arguments = dict(arguments)
                rationale = arguments.pop(RATIONALE, None)
                action = f"{name}({json.dumps(arguments, ensure_ascii=False)})"
                counted = costs_action(name, arguments)
                if counted and limit != -1 and self.steps >= limit:
                    counted = False
                    raise PolicyError("The action budget is exhausted. Observe if needed, then call webarena_submit(answer).")
                if counted:
                    self.steps += 1
                if name == SUBMIT["name"]:
                    self.answer = arguments["answer"]
                    action = f"send_msg_to_user({self.answer!r})"
                    result = message("Final answer recorded. The episode is finished.")
                else:
                    timeout = (
                        MediaSettings(**self.config["media"]).timeout_for(name)
                        if name.startswith("media_")
                        else self.config["tool_timeout"]
                    )
                    observation_deadline = min(self.deadline, time.monotonic() + timeout)
                    result = await asyncio.wait_for(
                        self.browser.call(name, arguments),
                        max(0.01, observation_deadline - time.monotonic()),
                    )
                    if result.get("rejected_before_action") and counted:
                        self.steps -= 1
                        counted = False
            except PolicyError as exc:
                if counted:
                    self.steps -= 1
                    counted = False
                result = message(str(exc), error=True)
            except BaseException as exc:
                # Cancellation or a transport timeout leaves an uncertain action.
                # Fail the trial; never continue or report an invented zero score.
                self.failure = safe_error(exc)
                self.artifacts.write(
                    "failure.json", {"status": "environment_error", "error": self.failure}
                )
                if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                    raise
                return message(
                    "Browser or media execution failed; this trial must be retried.", error=True
                )
            if counted or self.answer is not None:
                self.evaluation_revision += 1
            await self._record(action, result, deadline=observation_deadline, rationale=rationale, counted=counted)
            if counted and "automatic_observation" in result:
                await self._add_visual_observation(result, observation_deadline)
            self.artifacts.append(
                "calls.jsonl", {"step": self.steps, "call": self.calls, "counted": counted,
                                "status": "returned", "result": result}
            )
            if counted or name == SUBMIT["name"]:
                existing = result.get("automatic_screenshot")
                await self.capture_screenshot(existing)
            # At the final action limit no more mutations are allowed. Grade
            # through the private finalizer, outside the agent's MCP response
            # timeout. Intermediate checkpoints still precede subsequent actions.
            if counted and self.steps in self.book.cutoffs and self.steps != limit:
                try:
                    await self._grade(terminal=self.answer is not None)
                except BaseException as exc:
                    self.failure = safe_error(exc)
                    self.artifacts.write(
                        "failure.json", {"status": "evaluation_error", "error": self.failure}
                    )
                    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                        raise
                    return message(
                        "Checkpoint evaluation failed; this trial cannot be scored.", error=True
                    )
            # Return only MCP content, never private evaluator details or paths.
            return {
                key: result[key]
                for key in ("content", "isError", "structuredContent")
                if key in result
            }

    async def finalize(self):
        """Invoked through a private Unix socket after the orchestrator stops its client."""
        async with self.lock:
            if self.result is not None:
                return self.result
            self.closed = True
            try:
                if self.failure:
                    raise RuntimeError(self.failure)
                if self.book.last_grade and self.graded_revision == self.evaluation_revision:
                    self.book.record(self.steps, self.book.last_grade[1], terminal=True)
                else:
                    await self._grade(terminal=True)
                diagnostics = await self.supervisor.call("diagnostics")
                self.artifacts.write("diagnostics.json", diagnostics)
                scores = self.book.finish("client_finished")
                rewards = {"reward": scores["score"], "success": int(scores["success"])}
                for cutoff, value in scores["step_budget_scores"].items():
                    if value["status"] == "available":
                        rewards[f"score_at_{cutoff}"] = value["score"]
                self.result = {
                    "schema_version": 1,
                    "status": "graded",
                    "rewards": rewards,
                    "steps": self.steps,
                    "final_answer": self.answer,
                    **scores,
                }
            except Exception as exc:
                self.result = {
                    "schema_version": 1,
                    "status": "error",
                    "error": safe_error(exc),
                    "steps": self.steps,
                }
            self.artifacts.write("result.json", self.result)
            return self.result


@asynccontextmanager
async def open_session(config, directory: Path, *, fixture_urls=None):
    config = normalize_config(config)
    artifacts = Artifacts(directory)
    task = WebArenaProTaskConfig.from_raw_task(config["task"], container_name="external-owned")
    supervisor = Supervisor(
        task,
        directory,
        "mcp-session",
        fixture_urls=fixture_urls,
        external_urls=None if fixture_urls is not None else config["urls"],
    )
    try:
        startup = await supervisor.start(timeout=config["setup_timeout"])
        artifacts.write("provenance.json", {"config": config, "startup": startup})
        policy = ToolPolicy(
            list(startup["urls"].values()),
            blocked_paths=startup["blocked_paths"],
            media=MediaSettings(**config["media"]),
        )
        async with connect(
            startup["endpoint"], directory / "browser", policy, config["tool_timeout"]
        ) as browser:
            initial = await browser.call("browser_navigate", {"url": startup["urls"][task.website]})
            if initial.get("isError"):
                raise RuntimeError("Could not open the task's initial page")
            artifacts.write("initial.json", initial)
            session = Session(browser, supervisor, artifacts, config)
            session.current_url = await browser.current_url()
            await session.capture_screenshot()
            yield session
    finally:
        await supervisor.close()
