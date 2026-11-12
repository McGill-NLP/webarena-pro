"""Versioned browser facts and collection requirements; no browser runtime code."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PROBES = 128
MAX_TEXT = 16384
MAX_REACTIONS = 512
MAX_EVIDENCE_BYTES = 4 * 1024 * 1024


class EvidenceUnavailable(ValueError):
    """A UI check cannot make a trustworthy observation."""


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class UIProbe(Record):
    kind: Literal["count", "first_text", "nextcloud_reactions"]
    selector: str = Field(default="", max_length=8192)

    @property
    def key(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class UIEvidencePlan(Record):
    schema_version: Literal[1] = 1
    probes: list[UIProbe] = Field(default_factory=list, max_length=MAX_PROBES)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class Reaction(Record):
    message_id: str = Field(pattern=r"^[0-9]+$", max_length=32)
    text: str = Field(max_length=MAX_TEXT)
    selected: bool


class UIProbeResult(Record):
    probe: UIProbe
    status: Literal["ok", "error", "truncated", "unsupported"]
    count: int | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, max_length=MAX_TEXT)
    reactions: list[Reaction] | None = Field(default=None, max_length=MAX_REACTIONS)
    error: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def check_payload(self):
        fields = {"count": self.count, "first_text": self.text, "nextcloud_reactions": self.reactions}
        if self.status == "ok" and fields[self.probe.kind] is None:
            raise ValueError("successful probe is missing its result")
        if any(value is not None for kind, value in fields.items() if kind != self.probe.kind):
            raise ValueError("probe result has the wrong payload kind")
        return self


class UIEvidence(Record):
    schema_version: Literal[1] = 1
    evaluation_id: str = Field(min_length=1, max_length=128)
    step: int | None = Field(default=None, ge=0)
    tab_id: str | None = Field(default=None, max_length=128)
    url: str = Field(default="", max_length=8192)
    document_id: str | None = Field(default=None, max_length=128)
    captured_at: float = Field(ge=0, allow_inf_nan=False)
    status: Literal["ok", "unavailable", "error", "stale"]
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    results: dict[str, UIProbeResult] = Field(default_factory=dict, max_length=MAX_PROBES)
    error: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def check_keys(self):
        if any(key != result.probe.key for key, result in self.results.items()):
            raise ValueError("probe identity mismatch")
        if len(self.model_dump_json().encode()) > MAX_EVIDENCE_BYTES:
            raise ValueError("UI evidence exceeds size allowance")
        return self

    def result(self, probe: UIProbe) -> UIProbeResult:
        result = self.results.get(probe.key)
        if result is None or result.status != "ok":
            raise EvidenceUnavailable(f"UI probe {probe.kind}: {result.status if result else 'missing'}")
        return result

    def semantic_data(self) -> dict:
        """Cache identity excludes capture time, execution IDs and document nonce."""
        return self.model_dump(exclude={"evaluation_id", "captured_at", "step", "document_id"})


def probe_for_check(check: dict) -> UIProbe | None:
    method = check.get("method")
    if method == "element_exists":
        return UIProbe(kind="count", selector=check["selector"])
    if method == "text_contains":
        return UIProbe(kind="first_text", selector=check.get("selector", "body"))
    return None


def build_ui_evidence_plan(evaluation: dict) -> UIEvidencePlan:
    """Collect requirements recursively, including nested tiered strategies."""
    probes = {}

    def visit(kind, config):
        if kind == "tiered":
            for strategy in config.get("strategies", []):
                visit(strategy.get("type"), strategy.get("config", {}))
        elif kind == "ui_state":
            for check in config.get("checks", []):
                probe = probe_for_check(check)
                if probe is not None:
                    probes[probe.key] = probe
        elif kind == "nextcloud_reaction_ui" or (kind == "nextcloud_saved_state" and config.get("reaction_ui")):
            probe = UIProbe(kind="nextcloud_reactions")
            probes[probe.key] = probe

    for node in evaluation.get("nodes", []):
        visit(node.get("type"), node.get("eval_config", {}))
    return UIEvidencePlan(probes=[probes[key] for key in sorted(probes)])


def parse_ui_evidence(value) -> UIEvidence:
    if isinstance(value, UIEvidence):
        # Revalidate mutable containers even when the envelope is frozen.
        value = value.model_dump()
    if not isinstance(value, dict):
        raise EvidenceUnavailable("no captured UI evidence")
    try:
        return UIEvidence.model_validate(value)
    except (ValueError, TypeError) as error:
        raise EvidenceUnavailable("invalid captured UI evidence") from error


def require_ui_evidence(context) -> UIEvidence:
    evidence = parse_ui_evidence(context.ui_evidence)
    if evidence.status != "ok":
        raise EvidenceUnavailable(f"UI capture is {evidence.status}")
    for field, expected in (
        ("evaluation_id", context.evaluation_id),
        ("step", context.evaluation_step),
        ("tab_id", context.evaluation_tab_id),
    ):
        if expected is not None and getattr(evidence, field) != expected:
            raise EvidenceUnavailable(f"UI capture {field} mismatch")
    obs = (context.last_step_output or {}).get("obs") or {}
    if isinstance(obs, dict) and obs.get("url") and evidence.url != obs["url"]:
        raise EvidenceUnavailable("UI capture URL mismatch")
    return evidence


def semantic_ui_evidence(context):
    try:
        return require_ui_evidence(context).semantic_data()
    except EvidenceUnavailable as error:
        return {"status": "unavailable", "reason": str(error)}


def restore_ui_evidence(context, record: dict) -> None:
    """Restore trusted, saved evaluator evidence (never agent observation text).

    Callers must select the record for the evaluation cutoff being replayed.
    Missing legacy evidence remains unavailable, rather than being inferred
    from HTML, screenshots or accessibility text.
    """
    evidence = parse_ui_evidence(record)
    context.ui_evidence = evidence
    context.evaluation_id = evidence.evaluation_id
    context.evaluation_step = evidence.step
    context.evaluation_tab_id = evidence.tab_id
