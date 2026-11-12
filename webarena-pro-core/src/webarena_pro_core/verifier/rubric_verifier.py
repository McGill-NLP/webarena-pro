"""Rubric-driven multimodal verifier (shipped reference implementation).

Requires the optional `[verifier]` extra: jinja2, pydantic, openai, Pillow.
Loads `tool_schema.json` and `system_prompt.jinja2` from the package via
`importlib.resources.files("webarena_pro_core.verifier")`.

See doc/rfcs/step_verifier.md §9 for the design rationale and §7 for the
on-disk eval_results.json format produced on every final step."""

from __future__ import annotations

import base64
import importlib.resources
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import jinja2
import numpy as np
import yaml
from openai import OpenAI
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field

from .types import StepRecord

logger = logging.getLogger(__name__)

# Internal rubric state has three values; the tool only emits two of them.
# `pending` is only ever produced by initialisation and `_reset_state`,
# never by the judge LLM (the tool schema's `verdict` enum is restricted
# to pass/fail — see verifier/tool_schema.json).
Verdict = Literal["pass", "fail", "pending"]
ToolVerdict = Literal["pass", "fail"]


class RationaleEntry(BaseModel):
    step: int
    rationale: str
    verdict: ToolVerdict


class Rubric(BaseModel):
    id: int
    description: str
    verdict: Verdict = "pending"
    rationales: list[RationaleEntry] = Field(default_factory=list)


class _ToolCallRecord(BaseModel):
    step: int
    name: str
    arguments: dict


_RESOURCES = importlib.resources.files("webarena_pro_core.verifier")
DEFAULT_RUBRIC_VERIFIER_MODEL = "vllm/qwen36-27b"
_MODEL_CONFIG_ALIASES = {
    "qwen3.6-27b": "vllm/qwen36-27b",
    "qwen3_6_27b": "vllm/qwen36-27b",
    "qwen36-27b": "vllm/qwen36-27b",
    "kimi-k2.5": "openrouter/kimi-k2.5",
    "kimi_k2_5": "openrouter/kimi-k2.5",
    "kimi-k2.6": "openrouter/kimi-k2.6",
    "kimi_k2_6": "openrouter/kimi-k2.6",
}


def _png_data_url(arr: np.ndarray) -> str:
    """H×W×3 uint8 → base64 PNG data URL for OpenAI image blocks."""
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class RubricVerifier:
    """Multimodal step verifier for free-form rubric tasks.

    ``RubricVerifier`` observes normalized step records from a runner, asks an
    OpenAI-compatible model to update pass/fail rationales for each rubric, and
    writes final verdict artifacts at the end of an episode. It is used for
    tasks that do not have a deterministic tiered DAG and therefore still need
    a rubric judge.

    Args:
        rubric_descriptions: Human-readable criteria to judge independently.
        openai_client: OpenAI-compatible client used for chat completions.
        model_name: Model identifier passed to the client.
        completion_kwargs: Extra completion arguments such as temperature or
            provider-specific options.
    """

    def __init__(
        self,
        rubric_descriptions: list[str],
        openai_client: OpenAI,
        model_name: str,
        completion_kwargs: dict[str, Any] | None = None,
    ):
        self.rubrics: list[Rubric] = [
            Rubric(id=i, description=desc)
            for i, desc in enumerate(rubric_descriptions)
        ]
        self.openai_client = openai_client
        self.model_name = model_name
        self.completion_kwargs = dict(completion_kwargs or {})
        self.tool_schema = json.loads(
            _RESOURCES.joinpath("tool_schema.json").read_text()
        )
        self.system_prompt = jinja2.Template(
            _RESOURCES.joinpath("system_prompt.jinja2").read_text()
        ).render(rubric_count=len(self.rubrics))
        self.tool_calls: list[_ToolCallRecord] = []

    @classmethod
    def with_gemini(
        cls,
        rubric_descriptions: list[str],
        model_name: str = "gemini-3-flash-preview",
    ) -> "RubricVerifier":
        """Quick-start factory for Gemini's OpenAI-compatible endpoint.
        Reads `GEMINI_API_KEY` from the environment. Default model matches
        the existing `GEMINI_CHAT_MODEL_ARGS_DICT` entry in model_config.py."""
        from webarena_pro_core.verifier.model_config import GEMINI_BASE_URL

        client = OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_BASE_URL)
        return cls(rubric_descriptions, openai_client=client, model_name=model_name)

    @staticmethod
    def normalize_model_config_name(model_config_name: str) -> str:
        name = model_config_name.strip()
        if not name:
            return DEFAULT_RUBRIC_VERIFIER_MODEL

        lowered = name.lower()
        if lowered in _MODEL_CONFIG_ALIASES:
            return _MODEL_CONFIG_ALIASES[lowered]
        if "/" not in name and lowered.startswith("gemini-"):
            return f"gemini/{name}"
        if "/" not in name and lowered.startswith("qwen"):
            return _MODEL_CONFIG_ALIASES.get(lowered, f"vllm/{name}")
        return name

    @classmethod
    def with_model_config(
        cls,
        rubric_descriptions: list[str],
        model_config_name: str = DEFAULT_RUBRIC_VERIFIER_MODEL,
    ) -> "RubricVerifier":
        """Factory using registered WebArena-Pro LLM configs.

        The verifier calls the OpenAI-compatible endpoint directly because it
        needs tool calls and image blocks, so this uses core's AgentLab-free
        verifier endpoint metadata instead of routing through a runner-specific
        `ChatModel` wrapper.
        """
        from webarena_pro_core.verifier.model_config import (
            GEMINI_BASE_URL,
            GEMINI_CHAT_MODEL_ARGS_DICT,
            OPENROUTER_BASE_URL,
            OPENROUTER_CHAT_MODEL_ARGS_DICT,
            VLLM_CHAT_MODEL_ARGS_DICT,
            WEBARENA_PRO_VERIFIER_MODEL_CONFIGS,
        )

        model_key = cls.normalize_model_config_name(model_config_name)
        if model_key not in WEBARENA_PRO_VERIFIER_MODEL_CONFIGS:
            known = ", ".join(sorted(WEBARENA_PRO_VERIFIER_MODEL_CONFIGS))
            raise ValueError(
                f"Unknown rubric verifier model {model_config_name!r}. Known: {known}"
            )

        if model_key in VLLM_CHAT_MODEL_ARGS_DICT:
            args = VLLM_CHAT_MODEL_ARGS_DICT[model_key]
            api_key = args.token or os.getenv("VLLM_API_KEY", "EMPTY")
            base_url = args.model_url or os.getenv(
                "VLLM_API_URL",
                "http://localhost:8000/v1",
            )
            completion_kwargs: dict[str, Any] = {}
            if args.extra_body is not None:
                completion_kwargs["extra_body"] = args.extra_body
            return cls(
                rubric_descriptions,
                openai_client=OpenAI(api_key=api_key, base_url=base_url),
                model_name=args.model_name,
                completion_kwargs=completion_kwargs,
            )

        if model_key in OPENROUTER_CHAT_MODEL_ARGS_DICT:
            args = OPENROUTER_CHAT_MODEL_ARGS_DICT[model_key]
            completion_kwargs = {}
            if args.reasoning_effort is not None:
                completion_kwargs["extra_body"] = {
                    "reasoning": {"effort": args.reasoning_effort}
                }
            if args.extra_body is not None:
                extra_body = completion_kwargs.setdefault("extra_body", {})
                extra_body.update(args.extra_body)
            return cls(
                rubric_descriptions,
                openai_client=OpenAI(
                    api_key=os.environ["OPENROUTER_API_KEY"],
                    base_url=OPENROUTER_BASE_URL,
                ),
                model_name=args.model_name,
                completion_kwargs=completion_kwargs,
            )

        args = GEMINI_CHAT_MODEL_ARGS_DICT[model_key]
        return cls(
            rubric_descriptions,
            openai_client=OpenAI(
                api_key=os.environ["GEMINI_API_KEY"],
                base_url=GEMINI_BASE_URL,
            ),
            model_name=args.model_name,
        )

    def get_current_rubric_state(self) -> str:
        """Render each rubric as a fenced YAML code block. Keeping each
        rubric in its own block lets the judge parse them independently
        and avoids ambiguity around colons / quotes inside criterion or
        rationale text."""
        blocks: list[str] = []
        for r in self.rubrics:
            payload = {
                "id": r.id,
                "verdict": r.verdict.upper(),
                "criterion": r.description,
                "history": [
                    {
                        "step": e.step,
                        "verdict": e.verdict.upper(),
                        "rationale": e.rationale,
                    }
                    for e in r.rationales
                ],
            }
            body = yaml.safe_dump(
                payload,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            ).rstrip()
            blocks.append(f"```yaml\n{body}\n```")
        return "\n\n".join(blocks)

    def _apply_bbox_highlight(
        self,
        screenshot: np.ndarray,
        bbox: tuple[float, float, float, float] | None,
    ) -> np.ndarray:
        if bbox is None:
            return screenshot
        x, y, w, h = bbox
        img = Image.fromarray(screenshot).copy()
        ImageDraw.Draw(img).rectangle(
            [x, y, x + w, y + h], outline=(255, 0, 0), width=4
        )
        return np.asarray(img)

    def get_step_blocks(self, record: StepRecord) -> list[dict]:
        """Markdown-headed text blocks + before/after image blocks for the
        judge prompt. The 'before' screenshot is annotated with the bbox
        so the judge can see the agent's intended target; 'after' is left
        untouched because the same coordinates may not correspond to the
        same element after the action."""
        bid = record.get("bid")
        action_text = record["action"] + (f"  (target bid={bid})" if bid else "")
        before = self._apply_bbox_highlight(
            record["screenshot_before"], record.get("bbox")
        )
        blocks: list[dict] = [
            {"type": "text", "text": f"## Step {record['step']}"},
        ]
        ts = record.get("timestamp")
        if ts is not None:
            try:
                stamp = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC"
                )
            except (TypeError, ValueError, OverflowError):
                stamp = None
            if stamp:
                blocks.append(
                    {
                        "type": "text",
                        "text": (
                            f"## Reference date\n"
                            f"The agent took this action at **{stamp}**. "
                            f"Resolve relative phrases — \"today\", \"this week\", "
                            f"\"next month\" — against that time, NOT against the "
                            f"clock at grading time."
                        ),
                    }
                )
        if record.get("agent_think"):
            blocks.append(
                {"type": "text", "text": f"## Agent's thinking\n{record['agent_think']}"}
            )
        blocks.extend(
            [
                {"type": "text", "text": f"## Action\n{action_text}"},
                {"type": "text", "text": "## Screenshot before"},
                {
                    "type": "image_url",
                    "image_url": {"url": _png_data_url(before)},
                },
                {"type": "text", "text": "## Screenshot after"},
                {
                    "type": "image_url",
                    "image_url": {"url": _png_data_url(record["screenshot_after"])},
                },
            ]
        )
        return blocks

    def get_final_step_blocks(self, record: StepRecord) -> list[dict]:
        """Closure suffix appended on the last step. Forces the judge to
        resolve any rubric still PENDING into a definite pass/fail."""
        return [
            {"type": "text", "text": "## Trajectory complete — final result"},
            {
                "type": "image_url",
                "image_url": {"url": _png_data_url(record["screenshot_after"])},
            },
            {
                "type": "text",
                "text": (
                    "This is the last step. Any rubric still in PENDING must now be "
                    "graded as either pass or fail based on the trajectory so far "
                    "and this final screenshot — do not leave anything pending."
                ),
            },
        ]

    def on_agent_step_end(self, record: StepRecord) -> None:
        # Called on the verifier's worker thread, not the agent thread.
        # Single-shot prompt per step: one system + one user message; no
        # history is kept across steps. The running rubric state is
        # rendered into the user message and that is the only memory.
        is_final = bool(record.get("is_final_step"))
        user_content = [
            *self.get_step_blocks(record),
            {
                "type": "text",
                "text": f"## Current rubric state\n{self.get_current_rubric_state()}",
            },
        ]
        # Only append the closure-resolve nag when there's actually something
        # left to resolve. If every rubric is already pass/fail, the judge
        # has no mandatory work on the final step and the extra screenshot
        # + instruction would just be prompt noise.
        if is_final and any(r.verdict == "pending" for r in self.rubrics):
            user_content.extend(self.get_final_step_blocks(record))

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        completion_kwargs = {
            "model": self.model_name,
            "messages": messages,
            "tools": self.tool_schema,
            **self.completion_kwargs,
        }
        response = self.openai_client.chat.completions.create(**completion_kwargs)

        for tc in response.choices[0].message.tool_calls or []:
            if tc.function.name != "grade_rubric":
                continue
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "RubricVerifier: tool_call arguments not valid JSON: %r",
                    tc.function.arguments,
                )
                continue
            # Apply (the helper already tolerates missing/invalid fields by
            # logging + no-op).
            self._apply_grade(
                record["step"],
                args.get("rubric_id"),
                args.get("verdict"),
                args.get("rationale", ""),
            )
            self.tool_calls.append(
                _ToolCallRecord(
                    step=record["step"], name=tc.function.name, arguments=args
                )
            )

        # Per RFC §7: on the final step, dump the per-task results next to
        # the trajectory's existing artifacts, then reset internal state so
        # the next task in the study starts clean.
        if is_final:
            self._write_eval_results(record)
            self._reset_state()

    def _apply_grade(
        self,
        step: int,
        rubric_id: int,
        verdict: str,
        rationale: str,
    ) -> None:
        # The tool schema's enum is ("pass", "fail") but real models
        # (notably Gemini preview) occasionally return "pending" or other
        # off-enum values. Treat any non-tool verdict as a no-op so a
        # malformed grade can't corrupt our rubric state. The call still
        # ends up in `self.tool_calls` for audit (caller appends).
        if verdict not in ("pass", "fail"):
            logger.warning(
                "RubricVerifier: ignoring grade_rubric with off-enum verdict=%r "
                "(rubric_id=%s, step=%s)",
                verdict,
                rubric_id,
                step,
            )
            return
        if not isinstance(rubric_id, int) or not (0 <= rubric_id < len(self.rubrics)):
            logger.warning(
                "RubricVerifier: ignoring grade_rubric with invalid "
                "rubric_id=%r (n_rubrics=%d, step=%s)",
                rubric_id,
                len(self.rubrics),
                step,
            )
            return
        rubric = self.rubrics[rubric_id]
        rubric.verdict = verdict  # type: ignore[assignment]
        rubric.rationales.append(
            RationaleEntry(step=step, rationale=rationale, verdict=verdict)  # type: ignore[arg-type]
        )

    def _write_eval_results(self, record: StepRecord) -> None:
        """Atomic write of `<exp_dir>/eval_results.json` (tmp + rename)."""
        exp_dir_str = record.get("exp_dir")
        if exp_dir_str is None:
            logger.warning(
                "RubricVerifier: cannot write eval_results.json — record has no exp_dir"
            )
            return
        exp_dir = Path(exp_dir_str)
        payload = {
            "schema_version": 1,
            "task_name": record.get("task_name"),
            "verifier": {
                "class": type(self).__name__,
                "rubric_count": len(self.rubrics),
                "model_name": self.model_name,
            },
            "final_verdict": self.final_verdict(),
            "rubrics": [r.model_dump() for r in self.rubrics],
            "tool_calls": [tc.model_dump() for tc in self.tool_calls],
            "n_steps_observed": (record.get("step") or 0) + 1,
            "wrote_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        out = exp_dir / "eval_results.json"
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(out)

    def _reset_state(self) -> None:
        """Reset per-episode state. Rubric descriptions, the OpenAI client,
        model name, tool schema, and rendered system prompt are kept;
        verdicts go back to PENDING and rationale / tool-call histories
        are cleared."""
        for r in self.rubrics:
            r.verdict = "pending"
            r.rationales.clear()
        self.tool_calls.clear()

    def final_verdict(self) -> Verdict:
        """Strict-AND aggregation: only `pass` if every rubric is `pass`,
        otherwise `fail`. Pending counts as fail. Call after
        `drain_step_verifiers()` so the final-step LLM call has resolved
        any leftover PENDINGs first."""
        return (
            "pass" if all(r.verdict == "pass" for r in self.rubrics) else "fail"
        )
