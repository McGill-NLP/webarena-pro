"""Record the synchronous provider requests made during a BrowserGym decision."""

import json
import logging
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from webarena_pro_core.model_requests import (
    CoverageGap,
    ModelRequest,
    RunRequests,
    normalize_usage,
)

INDEX = "model_requests.jsonl"


class EpisodeTrace:
    """One append-only transcript for a logical episode, including checkpoint resumes."""

    def __init__(self, directory, checkpoint=None):
        self.id = uuid4().hex
        self.local_path = Path(directory) / INDEX
        self.path = self.local_path
        if checkpoint is not None:
            self.id = checkpoint.data.setdefault("model_trace_id", self.id)
            self.path = checkpoint.path.parent / "model_traces" / self.id / INDEX
            if self.path.is_file():
                self._link_transcript()

    def _link_transcript(self):
        if self.path != self.local_path and not self.local_path.is_symlink():
            self.local_path.symlink_to(os.path.relpath(self.path, self.local_path.parent))

    @contextmanager
    def step(self, agent, step_id):
        from agentlab.agents.generic_agent.generic_agent import GenericAgent
        from agentlab.llm.chat_api import OpenAIChatModel

        model = getattr(agent, "chat_llm", None)
        provider = getattr(model, "request_provider", None)
        if isinstance(model, OpenAIChatModel):
            provider = "openai"
        if provider is None:
            yield
            return

        recorder = _StepRecorder(model, provider, self.id, step_id, type(agent) is GenericAgent)
        try:
            with patch.object(agent, "chat_llm", recorder):
                yield
        finally:
            self._append_step(recorder)

    def _append_step(self, recorder):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(
            self.path, "a+b", opener=lambda path, flags: os.open(path, flags, 0o600)
        ) as stream:
            self._link_transcript()
            if stream.tell():
                stream.seek(-1, os.SEEK_END)
                if stream.read(1) != b"\n":
                    # Isolate a torn final row before appending after recovery.
                    stream.write(b"\n")
            for record, request, response in recorder.attempts:
                payload = _journal_row(record, request, response, recorder.api_format)
                stream.write(json.dumps(payload, ensure_ascii=False).encode() + b"\n")


class _StepRecorder:
    """A model call groups its HTTP attempts. A parser follow-up starts a new call."""

    def __init__(self, model, provider, episode_id, step_id, generic_agent):
        self.model = model
        self.provider = provider
        self.episode_id = episode_id
        self.step_id = step_id
        self.generic_agent = generic_agent
        self.attempts = []
        self.native_client = getattr(model, "native_client", None)
        self.api_format = "chat"
        if self.native_client is not None:
            self.api_format = "gemini"
        elif provider == "anthropic":
            self.api_format = "anthropic"

    def __getattr__(self, name):
        return getattr(self.model, name)

    def __call__(self, *args, **kwargs):
        # Both supported SDKs expose their synchronous httpx client here.
        client = self.native_client if self.native_client is not None else self.model.client._client
        send = client.send
        call_id = uuid4().hex
        reason = None
        if self.generic_agent:
            reason = "parser_retry" if self.attempts else "action"
        attempt = 0

        def record_attempt(request, **options):
            nonlocal attempt
            attempt += 1
            record = ModelRequest(
                episode_id=self.episode_id,
                step_id=self.step_id,
                call_id=call_id,
                attempt=attempt,
                call_reason=reason,
                provider=self.provider,
                model_requested=self.model.model_name,
                started_at=datetime.now(timezone.utc),
                status="unresolved",
            )
            start = time.monotonic()
            response = None
            try:
                response = send(request, **options)
                return response
            except BaseException as error:
                record.error_type = type(error).__name__
                record.status = "failed"
                raise
            finally:
                record.latency_ms = round((time.monotonic() - start) * 1000)
                self.attempts.append((record, request, response))

        with patch.object(client, "send", record_attempt):
            return self.model(*args, **kwargs)


def _journal_row(record, request, response, api_format):
    """Decode and redact provider bodies once, when the browser step is saved."""
    redact = _redactor(request.headers)
    body = redact(_body(request.content))
    if isinstance(body, dict) and body.get("model"):
        record.model_requested = body["model"]
    raw_response = None
    if response is not None:
        raw_response = redact(_body(response.content))
        payload = raw_response if isinstance(raw_response, dict) else {}
        record.http_status = response.status_code
        record.provider_request_id = redact(
            response.headers.get("x-request-id") or response.headers.get("request-id")
        )
        record.completion_id = payload.get("id") or payload.get("responseId")
        record.model_served = payload.get("model") or payload.get("modelVersion")
        if isinstance(payload.get("provider"), str):
            record.route = payload["provider"]
        if not response.is_success:
            record.error_type = "HTTPStatusError"
        elif not isinstance(raw_response, dict) or payload.get("error"):
            record.error_type = "InvalidProviderResponse"
        record.status = "failed" if record.error_type else "succeeded"
        choices = payload.get("choices") or payload.get("candidates") or [{}]
        first = choices[0] if isinstance(choices, list) and isinstance(choices[0], dict) else {}
        record.finish_reason = (
            first.get("finish_reason") or first.get("finishReason") or payload.get("stop_reason")
        )
        try:
            record.usage = normalize_usage(api_format, payload)
        except (AttributeError, TypeError, ValueError):
            logging.getLogger(__name__).warning("Unrecognized usage in call %s", record.call_id)
    row = record.model_dump(mode="json", exclude={"transcript_path", "transcript_line"})
    return {**row, "request": body, "response": raw_response}


def write_run_usage(directory: Path):
    """Build the run file from completed journal rows, counting resumed episodes once."""
    run = RunRequests(runner="browsergym", run_id=directory.name, requests=[])
    visited = set()
    for journal in sorted(directory.rglob(INDEX)):
        if journal.resolve() in visited:
            continue
        visited.add(journal.resolve())
        source = journal.relative_to(directory).as_posix()
        with journal.open("rb") as stream:
            for number, line in enumerate(stream, start=1):
                try:
                    # Only newline-terminated rows have been committed.
                    if not line.endswith(b"\n"):
                        raise ValueError("incomplete row")
                    row = ModelRequest.model_validate_json(line)
                except ValueError:
                    run.coverage_gaps.append(
                        CoverageGap(
                            episode_id=journal.parent.name,
                            source_path=source,
                            reason=f"invalid journal line {number}",
                        )
                    )
                    continue
                row.transcript_path = source
                row.transcript_line = number
                run.requests.append(row)
    for summary in sorted(directory.rglob("summary_info.json")):
        if not (summary.parent / INDEX).exists():
            run.coverage_gaps.append(
                CoverageGap(
                    episode_id=summary.parent.name,
                    source_path=summary.relative_to(directory).as_posix(),
                    reason="no_request_journal",
                )
            )
    run.save(directory)


_SECRET_FIELD = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|(?:access|refresh|id)?[_-]?token|password|passwd|"
    r"(?:client[_-]?)?secret|authorization|cookie|signature)$",
    re.I,
)
_SECRET_PAIR = re.compile(
    r"""(?i)(\b(?:api[_-]?key|(?:access[_-]?|refresh[_-]?)?token|password|passwd|secret|x-amz-signature|x-goog-signature|sig)"""
    r"""["']?\s*[:=]\s*)("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|[^\s&,;"'}]+)"""
)
_AUTH_LINE = re.compile(r"(?im)(\b(?:authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+")
_URL_KEY = re.compile(r"([?&](?:key|credential|x-amz-credential|x-goog-credential)=)[^&\s#]+", re.I)
_URL_AUTH = re.compile(r"(https?://)[^\s/@]+@", re.I)


def _redact_pair(match):
    quote = match[2][0] if match[2].startswith(('"', "'")) else ""
    return f"{match[1]}{quote}[REDACTED]{quote}"


def _redact(value, secrets):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_FIELD.search(key) else _redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[REDACTED]")
        value = _URL_AUTH.sub(r"\1[REDACTED]@", value)
        value = _URL_KEY.sub(r"\1[REDACTED]", value)
        value = _AUTH_LINE.sub(r"\1[REDACTED]", value)
        return _SECRET_PAIR.sub(_redact_pair, value)
    return value


def _redactor(headers):
    secrets = {value for key, value in os.environ.items() if value and _SECRET_FIELD.search(key)}
    for key in ("authorization", "x-api-key", "api-key", "x-goog-api-key", "cookie"):
        if value := headers.get(key):
            secrets.add(value)
            if key == "authorization":
                secrets.add(value.split()[-1])
    return partial(_redact, secrets=sorted(secrets, key=len, reverse=True))


def _body(content):
    try:
        return json.loads(content)
    except (ValueError, UnicodeDecodeError):
        return content.decode("utf-8", errors="replace")
