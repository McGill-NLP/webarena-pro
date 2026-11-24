"""Portable v1 schema and accounting for observed agent model requests."""

from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, computed_field, model_validator


class InputSplit(BaseModel):
    regular: NonNegativeInt | None = None
    cached: NonNegativeInt | None = None
    total: NonNegativeInt | None = None

    @classmethod
    def from_total(cls, total, cached, **details):
        regular = total - cached if total is not None and cached is not None else None
        return cls(total=total, cached=cached, regular=regular, **details)

    @model_validator(mode="after")
    def check_sum(self):
        if (
            None not in (self.regular, self.cached, self.total)
            and self.regular + self.cached != self.total
        ):
            raise ValueError("regular and cached input tokens must sum to total")
        return self


class InputTokens(InputSplit):
    cache_write: NonNegativeInt | None = None  # subset of regular
    by_modality: dict[str, InputSplit] = Field(default_factory=dict)


class OutputTokens(BaseModel):
    total: NonNegativeInt | None = None
    reasoning: NonNegativeInt | None = None
    text: NonNegativeInt | None = None
    tool_calls: NonNegativeInt | None = None


class Usage(BaseModel):
    input_tokens: InputTokens = Field(default_factory=InputTokens)
    output_tokens: OutputTokens = Field(default_factory=OutputTokens)


class ModelRequest(BaseModel):
    schema_version: Literal[1] = 1
    episode_id: str
    step_id: NonNegativeInt | None
    call_id: str
    attempt: PositiveInt | None = None
    call_reason: Literal["action", "parser_retry"] | None = None
    provider: str | None = None
    model_requested: str | None = None
    model_served: str | None = None
    route: str | None = None
    provider_request_id: str | None = None
    completion_id: str | None = None
    started_at: datetime | None = None
    latency_ms: NonNegativeInt | None = None
    time_to_first_token_ms: NonNegativeInt | None = None
    status: Literal["succeeded", "failed", "unresolved"] | None = None
    http_status: int | None = None
    error_type: str | None = None
    finish_reason: str | None = None
    usage: Usage = Field(default_factory=Usage)
    transcript_path: str | None = None
    transcript_line: PositiveInt | None = None


class CoverageGap(BaseModel):
    """Native data that cannot be attributed to individual requests."""

    episode_id: str
    source_path: str
    reason: str
    step_id: NonNegativeInt | None = None
    llm_call_count: NonNegativeInt | None = None


class RunRequests(BaseModel):
    schema_version: Literal[1] = 1
    runner: Literal["browsergym", "harbor"]
    run_id: str
    requests: list[ModelRequest]
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)

    @computed_field
    @property
    def totals(self) -> dict:
        return summarize_requests(self.requests)

    @computed_field
    @property
    def episode_totals(self) -> dict:
        episodes = defaultdict(list)
        for request in self.requests:
            episodes[request.episode_id].append(request)
        return {episode: summarize_requests(rows) for episode, rows in episodes.items()}

    def save(self, directory: Path):
        with atomic_text(directory / "model_requests.json") as out:
            out.write(self.model_dump_json(indent=2) + "\n")


def _sum_known(*counts):
    return sum(counts) if all(count is not None for count in counts) else None


def _modality_counts(details):
    return {
        entry["modality"].lower(): entry["tokenCount"]
        for entry in details or []
        if entry.get("modality") and entry.get("tokenCount") is not None
    }


def normalize_usage(api_format: str, payload: dict) -> Usage:
    """Map provider-reported counters. Missing breakdowns stay unknown."""
    if api_format == "gemini":
        return _gemini_usage(payload.get("usageMetadata") or {})
    usage = payload.get("usage") or {}
    if api_format == "anthropic":
        return _anthropic_usage(usage)
    return _chat_usage(usage)


def _anthropic_usage(usage) -> Usage:
    write = usage.get("cache_creation_input_tokens")
    cached = usage.get("cache_read_input_tokens")
    regular = _sum_known(usage.get("input_tokens"), write)
    inputs = InputTokens(
        regular=regular, cached=cached, total=_sum_known(regular, cached), cache_write=write
    )
    details = usage.get("output_tokens_details") or {}
    outputs = OutputTokens(
        total=usage.get("output_tokens"),
        reasoning=details.get("thinking_tokens"),
        text=details.get("text_tokens"),
        tool_calls=details.get("tool_call_tokens"),
    )
    return Usage(input_tokens=inputs, output_tokens=outputs)


def _gemini_usage(usage) -> Usage:
    inputs = InputTokens.from_total(
        usage.get("promptTokenCount"), usage.get("cachedContentTokenCount")
    )
    totals = _modality_counts(usage.get("promptTokensDetails"))
    cached = _modality_counts(usage.get("cacheTokensDetails"))
    # A partial cache breakdown cannot assign the remaining cache hits.
    # Once the breakdown accounts for every hit, other modalities have zero.
    remaining_cache = None
    if inputs.cached == sum(cached.values()):
        remaining_cache = 0
    for modality in sorted(totals.keys() | cached.keys()):
        inputs.by_modality[modality] = InputSplit.from_total(
            totals.get(modality), cached.get(modality, remaining_cache)
        )
    # totalTokenCount also includes tool-use prompts. Candidate tokens
    # can include function calls, so a TEXT modality is not a text-only bill.
    candidates = usage.get("candidatesTokenCount")
    thoughts = usage.get("thoughtsTokenCount")
    total = _sum_known(candidates, thoughts)
    accounted = _sum_known(inputs.total, candidates, usage.get("toolUsePromptTokenCount", 0))
    if total is None and accounted is not None and accounted == usage.get("totalTokenCount"):
        total = candidates
    outputs = OutputTokens(total=total, reasoning=thoughts)
    return Usage(input_tokens=inputs, output_tokens=outputs)


def _chat_usage(usage) -> Usage:
    details = usage.get("prompt_tokens_details") or {}
    inputs = InputTokens.from_total(
        usage.get("prompt_tokens"),
        details.get("cached_tokens"),
        cache_write=details.get("cache_write_tokens"),
    )
    for modality in ("text", "image", "audio", "video"):
        count = details.get(f"{modality}_tokens")
        cached = (details.get("cached_tokens_details") or {}).get(f"{modality}_tokens")
        if count is not None or cached is not None:
            inputs.by_modality[modality] = InputSplit.from_total(count, cached)
    details = usage.get("completion_tokens_details") or {}
    outputs = OutputTokens(
        total=usage.get("completion_tokens"),
        reasoning=details.get("reasoning_tokens"),
        text=details.get("text_tokens"),
        tool_calls=details.get("tool_call_tokens"),
    )
    return Usage(input_tokens=inputs, output_tokens=outputs)


def _counts(fields, prefix=""):
    for name, value in fields.items():
        key = f"{prefix}{name}"
        if isinstance(value, dict):
            yield from _counts(value, key + ".")
        else:
            yield key, value


def summarize_requests(records):
    """Sum each counter independently and expose its coverage over all attempts."""
    summary = {
        "request_count": 0,
        "failed_count": 0,
        "unresolved_count": 0,
        "retry_count": 0,
        "metrics": {},
    }
    for record in records:
        summary["request_count"] += 1
        summary["failed_count"] += record.status == "failed"
        summary["unresolved_count"] += record.status == "unresolved"
        summary["retry_count"] += record.attempt is not None and record.attempt > 1
        fields = {
            **record.usage.model_dump(),
            "latency_ms": record.latency_ms,
            "time_to_first_token_ms": record.time_to_first_token_ms,
        }
        for key, value in _counts(fields):
            metric = summary["metrics"].setdefault(key, {"sum": None, "reported_requests": 0})
            if value is not None:
                metric["sum"] = (metric["sum"] or 0) + value
                metric["reported_requests"] += 1
    return summary


@contextmanager
def atomic_text(path):
    """Publish a complete private artifact, including when rebuilding a run."""
    with NamedTemporaryFile("w", dir=path.parent, encoding="utf-8", delete=False) as out:
        temporary = Path(out.name)
        try:
            yield out
            out.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
