"""Portable judge audit records and replay of frozen, actually submitted inputs.

No API keys or request headers are serialized. Evidence can itself be sensitive;
these records belong in the same access-controlled storage as episode artifacts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

SCHEMA_VERSION = 1
PROMPT_VERSION = "single-rubric-v1"


def safe_endpoint(url: str | None) -> str | None:
    """Retain endpoint identity without URL credentials/query parameters."""
    if not url:
        return None
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc.rsplit("@", 1)[-1], parts.path, "", ""))


def resolve_sampling(overrides: dict | None = None) -> dict:
    """Merge environment then per-node overrides; omit provider defaults."""
    settings = json.loads(os.environ.get("WEBARENAPRO_LLM_JUDGE_SAMPLING", "{}"))
    if not isinstance(settings, dict) or (overrides is not None and not isinstance(overrides, dict)):
        raise ValueError("judge sampling must be a JSON object")
    settings.update(overrides or {})
    return validate_sampling(settings)


def validate_sampling(settings: dict) -> dict:
    if not isinstance(settings, dict):
        raise ValueError("judge sampling must be a JSON object")
    for name, value in settings.items():
        if name not in {"temperature", "top_p", "max_tokens", "seed"}:
            raise ValueError("unsupported judge sampling option")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("judge sampling values must be finite numbers")
        if name == "temperature" and not 0 <= value <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if name == "top_p" and not 0 < value <= 1:
            raise ValueError("top_p must be greater than 0 and at most 1")
        if name in {"max_tokens", "seed"} and not isinstance(value, int):
            raise ValueError("max_tokens and seed must be integers")
        if name == "max_tokens" and value < 1:
            raise ValueError("max_tokens must be positive")
    return settings


def new_audit(rubric, context, model) -> dict:
    try:
        sdk_version = version("openai")
    except PackageNotFoundError:
        sdk_version = None
    task = context.task_config or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "audit_id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "task_id": task.get("task_id"),
        "task_start_date": str(context.task_start_date) if context.task_start_date else None,
        "rubric": rubric,
        "model": model,
        "openai_sdk_version": sdk_version,
        "aggregation": "single_sample",
        "attempts": [],
        "status": "configuration_error",
        "verdict": None,
    }


def response_text(response: Any) -> str | None:
    """Extract text defensively from an OpenAI-compatible response envelope."""
    # OpenAI-compatible providers can return HTTP 200 with an invalid envelope;
    # the SDK's non-strict construction may preserve those malformed values.
    choices = response.get("choices") if isinstance(response, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else None
    message = first.get("message") if isinstance(first, dict) else None
    text = message.get("content") if isinstance(message, dict) else None
    return text if isinstance(text, str) else None


def _parse_response(response: Any) -> dict:
    text = response_text(response)
    answers = re.findall(r"<answer>(.*?)</answer>", text, flags=re.I | re.S) if text is not None else []
    answer = answers[0].strip().lower() if len(answers) == 1 else None
    if answer not in {"successful", "unsuccessful", "in progress"}:
        if text is None:
            error = "Expected text in choices[0].message.content."
        elif len(answers) != 1:
            error = "Expected exactly one <answer>...</answer> tag."
        else:
            error = "The <answer> value must be Successful, Unsuccessful or In Progress."
        return {"status": "parse_error", "parsed_answer": answer, "verdict": None, "error_message": error}
    verdict = "pass" if answer == "successful" else "fail"
    return {"status": "positive" if verdict == "pass" else "negative", "parsed_answer": answer, "verdict": verdict}


def record_attempt(client, model, messages, kwargs, variant) -> dict:
    """Record one SDK call (the SDK may retry HTTP requests internally)."""
    request = {"model": model, "messages": copy.deepcopy(messages), **copy.deepcopy(kwargs)}
    attempt = {
        "variant": variant,
        "request": request,
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    start = time.monotonic()
    try:
        if request.get("stream"):
            # Keep long generations active through HTTP proxies, but publish
            # only a completed response. The SDK assembles text, reasoning,
            # finish reasons and usage without changing the judge prompt.
            options = {key: value for key, value in request.items() if key != "stream"}
            with client.chat.completions.stream(**options) as stream:
                stream.until_done()
                response = stream.current_completion_snapshot
            if not response.choices or any(choice.finish_reason is None for choice in response.choices):
                raise RuntimeError("Judge stream ended before completion")
        else:
            response = client.chat.completions.create(**request)
    except Exception as error:
        # Exception strings can echo headers or request bodies; don't persist them.
        attempt.update(status="model_error", error_type=type(error).__name__, verdict=None)
        attempt["error_message"] = f"Model request failed ({type(error).__name__})."
        status_code = getattr(error, "status_code", None)
        if isinstance(status_code, int):
            attempt["http_status"] = status_code
            attempt["error_message"] += f" HTTP status: {status_code}."
    else:
        # Non-object JSON can also survive non-strict SDK construction.
        attempt["response"] = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        attempt.update(_parse_response(attempt["response"]))
    attempt["elapsed_seconds"] = time.monotonic() - start
    return attempt


def find_audits(document: Any) -> list[dict]:
    """Accept a saved audit, DAG results, or a runner's nested task/summary info."""
    found = []
    if isinstance(document, dict):
        if document.get("schema_version") == SCHEMA_VERSION and "audit_id" in document and "attempts" in document:
            return [document]
        for value in document.values():
            found.extend(find_audits(value))
    elif isinstance(document, list):
        for value in document:
            found.extend(find_audits(value))
    # A runner may include the same record in more than one summary field.
    return list({record["audit_id"]: record for record in found}.values())


def agreement_report(attempts: list[dict]) -> dict:
    """Pairwise agreement excludes errors; report error counts separately."""
    votes = Counter(a["verdict"] for a in attempts if a.get("verdict") in {"pass", "fail"})
    n = sum(votes.values())
    pairs = n * (n - 1) // 2
    matching = sum(count * (count - 1) // 2 for count in votes.values())
    usage = Counter()
    for attempt in attempts:
        response = attempt.get("response")
        reported_usage = response.get("usage") if isinstance(response, dict) else None
        if isinstance(reported_usage, dict):
            for key, value in reported_usage.items():
                if isinstance(value, int):
                    usage[key] += value
    return {
        "samples": len(attempts), "valid_verdicts": n,
        "status_counts": dict(Counter(a["status"] for a in attempts)),
        "verdict_counts": dict(votes), "matching_pairs": matching, "valid_pairs": pairs,
        "pairwise_agreement": matching / pairs if pairs else None,
        "unanimous": len(votes) == 1 if n >= 2 else None,
        "usage": dict(usage),
        "elapsed_seconds": sum(a["elapsed_seconds"] for a in attempts),
    }


def submitted_audit(audit: dict) -> dict:
    """Resolve the original submitted request behind an identical-input hit."""
    if audit.get("attempts"):
        return audit
    source = audit.get("source_audit")
    if audit.get("reuse", {}).get("status") == "hit" and isinstance(source, dict):
        if source.get("audit_id") != audit["reuse"].get("source_audit_id"):
            raise ValueError("cached audit provenance does not match its source")
        if source.get("attempts"):
            return source
    raise ValueError("audit contains no submitted request")


def replay_audit(audit: dict, *, repeats: int = 3, attempt_index: int = -1, sampling: dict | None = None) -> dict:
    """Re-submit one frozen request; never rebuild evidence from today's task.

    The final attempt is the actual judged prompt (possibly pruned), or the
    last failed API request if no response was obtained. Overrides apply only
    to explicitly supplied sampling settings, not the ambient environment.
    """
    from openai import OpenAI
    from webarena_pro_core.eval.llm_judge import _client_config

    if repeats < 1:
        raise ValueError("repeats must be positive")
    submitted = submitted_audit(audit)
    original = submitted["attempts"][attempt_index]
    request = copy.deepcopy(original["request"])
    model, messages = request.pop("model"), request.pop("messages")
    if sampling is not None:
        # Validate without allowing the current environment to alter frozen inputs.
        request.update(validate_sampling(sampling))
    config = _client_config(model)
    endpoint = audit.get("endpoint") or config["base_url"]
    attempts = []
    with OpenAI(api_key=config["api_key"], base_url=endpoint, max_retries=audit.get("sdk_max_retries", 2)) as client:
        for _ in range(repeats):
            attempts.append(record_attempt(client, model, messages, request, original["variant"]))
    return {
        "source_audit_id": audit["audit_id"],
        "task_id": audit.get("task_id"),
        "rubric": audit["rubric"], "source_prompt_version": audit["prompt_version"],
        "source_attempt_index": attempt_index % len(submitted["attempts"]),
        "submitted_audit_id": submitted["audit_id"],
        "source_status": original["status"], "endpoint": safe_endpoint(endpoint),
        "sampling_overrides": sampling or {}, "attempts": attempts,
        "agreement": agreement_report(attempts),
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Replay saved judge requests and measure agreement; makes paid model calls.")
    parser.add_argument("inputs", type=Path, nargs="+", help="JSON audit or saved DAG/summary results")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-id", help="Select one record (e.g. the disputed task 382 watch-video node)")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--attempt", type=int, default=-1, help="Default: final actually submitted prompt")
    parser.add_argument("--sampling", type=json.loads, help="Explicit sampling experiment, e.g. '{\"temperature\":0}'")
    args = parser.parse_args(argv)
    records = {}
    for path in args.inputs:
        for audit in find_audits(json.loads(path.read_text())):
            if not args.audit_id or audit["audit_id"] == args.audit_id:
                records[audit["audit_id"]] = audit
    if not records:
        parser.error("no matching judge audits; older runs without captured inputs cannot be reconstructed by this command")
    if args.repeats < 1:
        parser.error("repeats must be positive")
    try:
        if args.sampling is not None:
            validate_sampling(args.sampling)
        for audit in records.values():
            submitted_audit(audit)["attempts"][args.attempt]
    except (ValueError, IndexError) as error:
        parser.error(str(error))
    # Create the private output before making calls; do not overwrite earlier evidence.
    with open(args.output, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        os.chmod(args.output, 0o600)
        result = {"schema_version": SCHEMA_VERSION, "aggregation": "none (diagnostic repeats only)", "cases": []}
        for audit in records.values():
            result["cases"].append(replay_audit(audit, repeats=args.repeats, attempt_index=args.attempt, sampling=args.sampling))
            output.seek(0)
            json.dump(result, output, indent=2, ensure_ascii=False)
            output.truncate()
            output.flush()
        print(json.dumps([case["agreement"] for case in result["cases"]], indent=2))


if __name__ == "__main__":
    main()
