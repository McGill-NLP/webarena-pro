"""Execution-local reuse of valid judge requests with identical inputs.

This is deliberately not a success latch. Any observed evidence change clears
all earlier entries, and only an unrepaired regular response is reusable.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any
from uuid import uuid4


def _json_default(value: Any):
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError("unsupported evidence value")


def input_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        default=_json_default, separators=(",", ":"),
    ).encode()).hexdigest()


class JudgeVerdictCache:
    """One bounded, in-memory cache per task execution, never checkpointed.

    Adapters replace this object on setup/reset. A changed evidence digest
    clears all entries, including those belonging to dependency-skipped nodes.
    Credentials and live browser objects are never cached or serialized.
    """

    def __init__(self) -> None:
        self.scope_id = uuid4().hex
        self._evidence_digest: str | None = None
        self._entries: dict[str, tuple[str, dict]] = {}

    @property
    def evidence_sha256(self) -> str | None:
        return self._evidence_digest

    def clear(self) -> None:
        self._evidence_digest = None
        self._entries.clear()

    def observe(self, context) -> str | None:
        from webarena_pro_core.eval.llm_judge import build_judge_messages
        from webarena_pro_core.eval.ui_evidence import semantic_ui_evidence

        obs = (context.last_step_output or {}).get("obs")
        if not isinstance(obs, dict) or not (
            obs.get("axtree_txt") or obs.get("screenshot") is not None
        ):
            self.clear()
            return "missing_current_observation"
        try:
            messages = build_judge_messages("", context)
            if obs.get("screenshot") is not None and not any(
                part.get("type") == "image_url"
                for part in messages["regular"][1]["content"]
            ):
                self.clear()
                return "unencoded_screenshot"
            digest = input_digest({
                "task": context.task_config,
                "dag": context.judge_dag_config,
                "task_start_date": context.task_start_date,
                "messages": messages,
                "current_url": obs.get("url"),
                "ui_evidence": semantic_ui_evidence(context),
                "last_action": context.last_action,
                "baselines": context.baselines,
                "chat_messages": context.chat_messages,
                "downloads": context.downloads,
            })
        except (TypeError, ValueError):
            self.clear()
            return "unsupported_evidence"
        if digest != self._evidence_digest:
            self._entries.clear()
            self._evidence_digest = digest
        return None

    def discard(self, slot: str) -> None:
        self._entries.pop(slot, None)

    def get(self, slot: str, fingerprint: str) -> dict | None:
        previous = self._entries.pop(slot, None)
        if previous is not None and previous[0] == fingerprint:
            self._entries[slot] = previous
            return copy.deepcopy(previous[1])
        return None

    def put(self, slot: str, fingerprint: str, audit: dict) -> None:
        # Bound retained multimodal evidence even for malformed unbounded DAGs.
        if len(self._entries) >= 128 and slot not in self._entries:
            del self._entries[next(iter(self._entries))]
        self._entries[slot] = (fingerprint, copy.deepcopy(audit))
