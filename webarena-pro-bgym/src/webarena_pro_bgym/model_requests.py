"""Record the synchronous provider requests made during a BrowserGym decision."""

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
import json
import logging
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import time
from uuid import uuid4

import httpx

from webarena_pro_core.model_requests import ModelRequest, normalize_usage, summarize_requests


INDEX = "model_requests.jsonl"
_BODIES = "completions"
_SECRET_FIELD = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|(?:access|refresh|id)?[_-]?token|password|passwd|"
    r"(?:client[_-]?)?secret|authorization|cookie|signature)$", re.I
)
_SECRET_PAIR = re.compile(
    r'''(?i)(\b(?:api[_-]?key|(?:access[_-]?|refresh[_-]?)?token|password|passwd|secret|x-amz-signature|x-goog-signature|sig)'''
    r'''["']?\s*[:=]\s*)("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|[^\s&,;"'}]+)'''
)
_AUTH_LINE = re.compile(r"(?im)(\b(?:authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]+")
_URL_KEY = re.compile(r"([?&](?:key|credential|x-amz-credential|x-goog-credential)=)[^&\s#]+", re.I)
_URL_AUTH = re.compile(r"(https?://)[^\s/@]+@", re.I)


def _redact_pair(match):
    quote = match[2][0] if match[2].startswith(('"', "'")) else ""
    return f"{match[1]}{quote}[REDACTED]{quote}"


def _redact(value, secrets):
    if isinstance(value, dict):
        return {key: "[REDACTED]" if _SECRET_FIELD.search(key) else _redact(item, secrets)
                for key, item in value.items()}
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


@contextmanager
def _atomic_text(path):
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as out:
        temporary = Path(out.name)
        try:
            yield out
            out.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def _json_file(path, data):
    with _atomic_text(path) as out:
        json.dump(data, out, ensure_ascii=False, allow_nan=False)
        out.write("\n")


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


def _records(path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            yield ModelRequest.model_validate_json(line)


def write_episode_usage(directory):
    index = directory / INDEX
    if not index.is_file():
        return
    steps = defaultdict(list)
    records = list(_records(index))
    for record in records:
        steps[record.step_id].append(record)
    _json_file(directory / "model_usage.json", {
        "schema_version": 1, **summarize_requests(records),
        "steps": {step: summarize_requests(rows) for step, rows in steps.items()},
    })


def write_run_usage(directory):
    # A resumed episode can appear under multiple workers and its checkpoint.
    # Fresh retries incur additional usage and have distinct journals.
    indexes = sorted({path.resolve() for path in directory.rglob(INDEX)})
    if indexes:
        summary = summarize_requests(record for path in indexes for record in _records(path))
        _json_file(directory / "model_request.schema.json", ModelRequest.model_json_schema())
        _json_file(directory / "model_usage.json", {
            "schema_version": 1, "recorded_episodes": len(indexes), **summary,
        })


class EpisodeTrace:
    def __init__(self, directory, checkpoint=None):
        self.directory = Path(directory)
        self.id = uuid4().hex
        self.storage = self.directory
        if checkpoint is not None:
            self.id = checkpoint.data.setdefault("model_trace_id", self.id)
            self.storage = checkpoint.path.parent / "model_traces" / self.id
            if (self.storage / INDEX).exists():
                self.prepare()

    def prepare(self):
        self.storage.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.storage / _BODIES).mkdir(mode=0o700, exist_ok=True)
        (self.storage / INDEX).touch(mode=0o600, exist_ok=True)
        if self.storage != self.directory:
            for name in (INDEX, _BODIES):
                link = self.directory / name
                if not link.is_symlink():
                    link.symlink_to(os.path.relpath(self.storage / name, self.directory),
                                    target_is_directory=name == _BODIES)

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
        self.prepare()
        recording = _RecordingModel(model, provider, self, step_id, type(agent) is GenericAgent)
        agent.chat_llm = recording
        try:
            yield
        finally:
            agent.chat_llm = model


class _ArtifactError(BaseException):
    """Escape SDK and model retry handlers on a local artifact failure."""


class _RecordingModel:
    def __init__(self, model, provider, trace, step, generic_agent):
        self.model = model
        self.provider = provider
        self.trace = trace
        self.step = step
        self.generic_agent = generic_agent
        self.call_count = 0

    def __getattr__(self, name):
        return getattr(self.model, name)

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        self.call_id = uuid4().hex
        self.attempt = 0
        client = getattr(self.model, "native_client", None)
        if client is None:
            # The pinned OpenAI and Anthropic SDKs own an httpx.Client. Its
            # send boundary sees both SDK-internal retries and wrapper retries.
            client = self.model.client._client
            self.api_format = "anthropic" if self.provider == "anthropic" else "chat"
        else:
            self.api_format = "gemini"
        send = client.send
        previous = vars(client).get("send")
        client.send = partial(self.send, send)
        try:
            return self.model(*args, **kwargs)
        except _ArtifactError as exc:
            raise RuntimeError("Could not save model request artifacts") from exc.__cause__
        finally:
            if previous is None:
                del client.send
            else:
                client.send = previous

    def send(self, send, request: httpx.Request, **kwargs):
        self.attempt += 1
        journal = self.trace.storage / INDEX
        prefix = f"{_BODIES}/{self.call_id}-{self.attempt}"
        redact = _redactor(request.headers)
        try:
            body = redact(_body(request.content))
            record = ModelRequest(
                episode_id=self.trace.id, step_id=self.step, call_id=self.call_id, attempt=self.attempt,
                provider=self.provider, model_requested=body.get("model", self.model.model_name),
                started_at=datetime.now(timezone.utc), status="unresolved",
                raw_request_path=prefix + ".request.json",
            )
            if self.generic_agent:
                record.call_reason = "action" if self.call_count == 1 else "parser_retry"
            _json_file(self.trace.storage / record.raw_request_path, body)
            # One synchronous agent owns this logical episode. Keep the prior
            # index (metadata only) so a process kill leaves a complete journal
            # before, during, and after the provider call.
            prior = journal.read_text(encoding="utf-8")
            self._publish(journal, prior, record)
        except Exception as exc:
            raise _ArtifactError from exc

        start = time.monotonic()
        response = None
        try:
            response = send(request, **kwargs)
            return response
        except BaseException as exc:
            record.error_type = type(exc).__name__
            raise
        finally:
            record.latency_ms = round((time.monotonic() - start) * 1000)
            try:
                if response is not None:
                    self._save_response(record, response, prefix, redact)
                record.status = "failed" if record.error_type else "succeeded"
                self._publish(journal, prior, record)
            except Exception as exc:
                raise _ArtifactError from exc

    @staticmethod
    def _publish(journal, prior, record):
        with _atomic_text(journal) as out:
            out.write(prior)
            out.write(record.model_dump_json() + "\n")

    def _save_response(self, record, response, prefix, redact):
        raw = redact(_body(response.content))
        record.raw_response_path = prefix + ".response.json"
        _json_file(self.trace.storage / record.raw_response_path, raw)
        payload = raw if isinstance(raw, dict) else {}
        record.http_status = response.status_code
        if not response.is_success:
            record.error_type = "HTTPStatusError"
        elif not isinstance(raw, dict) or payload.get("error"):
            record.error_type = "InvalidProviderResponse"
        record.provider_request_id = redact(response.headers.get("x-request-id") or response.headers.get("request-id"))
        record.completion_id = payload.get("id") or payload.get("responseId")
        record.model_served = payload.get("model") or payload.get("modelVersion")
        route = payload.get("provider")
        if isinstance(route, str):
            record.route = route
        choices = payload.get("choices") or payload.get("candidates") or [{}]
        first = choices[0] if isinstance(choices, list) and isinstance(choices[0], dict) else {}
        record.finish_reason = first.get("finish_reason") or first.get("finishReason") or payload.get("stop_reason")
        try:
            record.usage = normalize_usage(self.api_format, payload)
        except (AttributeError, TypeError, ValueError):
            logging.getLogger(__name__).warning("Unrecognized usage in %s", record.raw_response_path)
