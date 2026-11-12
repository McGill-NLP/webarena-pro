"""Tier-2 ``llm_judge`` DAG node: grade a *single* rubric with an LLM.

This is the fallback of last resort in the tiered evaluator — used only for
rubrics that no deterministic check can resolve (subjective / visual outcomes),
or when Tier-0/1 strategies came back inconclusive.

The judge is **equivalent to the original LLM-judge approach**
(``eval/evaluators.py`` / ``eval/judge``): it sees the same evidence — the
full step history (URL, action, agent reasoning per step), the final
screenshot, and the final accessibility tree — uses the same prompt templates,
model endpoint conventions, and ``<answer>Successful/Unsuccessful`` protocol.
The only difference is that the question is scoped to ONE rubric instead of the
whole task goal.

The actual model call goes through a module-level hook ``_JUDGE_HOOK`` so it
can be swapped out in experiments and tests (``set_llm_judge_hook``) without
real API keys.

Config shape::

    {"rubric": "A file named X exists ...", "model": "qwen/qwen3.6-27b",
     "max_retries": 3}
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import date
from io import BytesIO
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

if TYPE_CHECKING:
    from webarena_pro_core.eval.dag import EvalContext

logger = logging.getLogger(__name__)

# A judge hook returns (verdict, reason) where verdict is "pass" | "fail".
JudgeHook = Callable[[str, "EvalContext", Optional[str]], Tuple[str, str]]

_JUDGE_HOOK: Optional[JudgeHook] = None

_MAX_TOKENS = 4096
_DEFAULT_MODEL = "qwen/qwen3.6-27b"
_DEFAULT_MAX_RETRIES = 3

_SYSTEM_PROMPT = """
You are a Language Model specialized in judging the performance of web agents in web navigation tasks. For a certain website, you are given the goal of a navigation task, the current URL of the webpage, the actions taken by the agent, and the thought process of the agent. Additionally, you may have access to the last screenshot and the last accessibility tree. Your task is to provide a single answer about the agent's performance in the task.

Question 1: Was the sequence of actions below successful in achieving the goal?
Choices: <answer>Successful</answer>, <answer>Unsuccessful</answer>, <answer>In Progress</answer>

You should provide your reasoning process for each question, and you can refer to the screenshots and the accessibility tree to support your answers. Your answer must follow the following format:

<reasoning>your reasoning here</reasoning>
<answer>answer</answer>
""".strip()

_STEP_TEMPLATE = """
-----
Step: {step_number}
URL: {url}
Action: {action}
Reasoning: {reasoning}
""".strip()

_GOAL_TEMPLATE = "The user goal is: {goal}\n"

_ACTION_TEMPLATE = """
The agent performed the following actions:
{steps}
-----
""".strip()

_AXTREE_TEMPLATE = """
The last accessibility tree is:
{axtree}
""".strip()


def set_llm_judge_hook(hook: Optional[JudgeHook]) -> None:
    """Install a custom judge implementation (or None to restore default).

    Used by experiments/tests to inject scripted verdicts so the tiered
    engine can be exercised end-to-end without network access.
    """
    global _JUDGE_HOOK
    _JUDGE_HOOK = hook


# ---------------------------------------------------------------------------
# Evidence extraction (mirrors eval/evaluators.py format_step_info/trajectory)
# ---------------------------------------------------------------------------


def _step_field(step: Any, field: str) -> Any:
    if isinstance(step, dict):
        return step.get(field)
    return getattr(step, field, None)


def _valid_steps(context: "EvalContext") -> list[Any]:
    episode = context.trajectory or (
        (context.last_step_output or {}).get("episode_info") or []
    )
    return [s for s in episode if isinstance(_step_field(s, "obs"), dict)]


def _step_record(step: Any, number: int) -> dict[str, Any]:
    obs = _step_field(step, "obs") or {}
    agent_info = _step_field(step, "agent_info") or {}
    if isinstance(agent_info, dict):
        think = str(agent_info.get("think") or "")
    else:
        think = str(getattr(agent_info, "think", "") or "")
    return {
        "step_number": number,
        "url": str(obs.get("url") or ""),
        "action": str(_step_field(step, "action") or ""),
        "reasoning": think,
    }


def _convert_numpy_array_to_base64(array: Any) -> str:
    from PIL import Image

    image = Image.fromarray(array)
    image = image.convert("RGB")
    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)
    encoded = base64.b64encode(image_buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def build_judge_messages(rubric: str, context: "EvalContext") -> dict[str, list[Any]]:
    """Build the judge chat messages exactly like the original judge does.

    Returns ``{"regular": [...], "pruned": [...]}`` — ``pruned`` drops the
    accessibility tree, used as a retry when the full prompt is too large.
    """
    intent = ""
    if context.task_config:
        intent = str(context.task_config.get("intent") or "")

    steps = _valid_steps(context)
    step_blocks = "\n".join(
        _STEP_TEMPLATE.format(**_step_record(step, index + 1))
        for index, step in enumerate(steps)
    )
    action_msg = _ACTION_TEMPLATE.format(steps=step_blocks or "(no steps recorded)")

    goal_msg = _GOAL_TEMPLATE.format(goal=intent or "(not recorded)")
    goal_msg += (
        "\nYou are judging ONE specific rubric (success criterion) for this "
        f"task:\n<rubric>\n{rubric}\n</rubric>\n"
        "Question 1: Based on the agent's actions and the final state, was "
        "this rubric satisfied?\n"
        "Choices: <answer>Successful</answer>, <answer>Unsuccessful</answer>"
    )

    start_date = context.task_start_date
    if isinstance(start_date, str):
        try:
            start_date = date.fromisoformat(start_date)
        except ValueError:
            start_date = None
    if isinstance(start_date, date):
        goal_msg += (
            f"\n\nTask execution date: {start_date.isoformat()} ({start_date:%A}). "
            "Resolve dates relative to the task execution against this date, "
            "not the date when grading occurs. An explicit application-specific "
            "reference date in the rubric takes precedence."
        )

    # Online runners can provide the action's resulting observation before the
    # pending trajectory step has been populated. Replay callers can continue
    # using the last completed step when no explicit observation is available.
    obs = (context.last_step_output or {}).get("obs")
    if not isinstance(obs, dict):
        obs = _step_field(steps[-1], "obs") if steps else {}
    img_content: list[Any] = []
    axtree_msg = None
    if obs:
        screenshot = obs.get("screenshot")
        if screenshot is not None:
            try:
                img_content = [{
                    "type": "image_url",
                    "image_url": {"url": _convert_numpy_array_to_base64(screenshot)},
                }]
            except Exception:
                logger.debug("could not encode final screenshot for judge", exc_info=True)
        axtree_txt = obs.get("axtree_txt")
        if axtree_txt:
            axtree_msg = _AXTREE_TEMPLATE.format(axtree=axtree_txt)

    final_msg = (
        "Provide your reasoning and answer Question 1 using the specified "
        "format: <reasoning>...</reasoning> then <answer>Successful</answer> "
        "or <answer>Unsuccessful</answer>."
    )

    def _messages(axtree: str | None) -> list[Any]:
        user_content: list[Any] = [
            {"type": "text", "text": goal_msg},
            {"type": "text", "text": action_msg},
        ]
        if axtree:
            user_content.append({"type": "text", "text": axtree})
        user_content.extend(img_content)
        user_content.append({"type": "text", "text": final_msg})
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    return {"regular": _messages(axtree_msg), "pruned": _messages(None)}


# ---------------------------------------------------------------------------
# Default judge — same model plumbing as the original evaluator
# ---------------------------------------------------------------------------


def _uses_openrouter(model: str) -> bool:
    # Match the exact OpenRouter ID; Qwen/Qwen3.6-27B is a vLLM/Hugging Face ID.
    normalized = model.lower()
    return model == _DEFAULT_MODEL or "kimi" in normalized or "openrouter" in normalized


def _client_config(model: str) -> dict[str, str | None]:
    """Resolve an OpenAI-compatible endpoint without integration dependencies."""
    normalized = model.lower()
    if _uses_openrouter(model):
        return {
            "api_key": os.environ.get("OPENROUTER_API_KEY"),
            "base_url": os.environ.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            ),
        }
    if "gemini" in normalized:
        return {
            "api_key": os.environ.get("GEMINI_API_KEY"),
            "base_url": os.environ.get("GEMINI_BASE_URL"),
        }
    if any(name in normalized for name in ("qwen", "gemma", "olmo")):
        return {
            "api_key": os.environ.get("VLLM_API_KEY"),
            "base_url": os.environ.get("VLLM_BASE_URL"),
        }
    return {
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "base_url": os.environ.get("OPENAI_BASE_URL"),
    }


def _qwen_completion_kwargs(enable_thinking: bool) -> dict[str, Any]:
    if enable_thinking:
        return {
            "temperature": 0.6,
            "top_p": 0.95,
        }
    return {
        "temperature": 0.7,
        "top_p": 0.8,
    }


def _completion_kwargs(model: str, enable_thinking: bool) -> dict[str, Any]:
    normalized = model.lower()
    if "qwen" in normalized:
        kwargs = _qwen_completion_kwargs(enable_thinking)
        if not _uses_openrouter(model):
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": enable_thinking}
            }
        return kwargs
    if "gemini" in normalized:
        return {"temperature": 1.0, "top_p": 0.95}
    return {}


def _resolve_max_retries(override: int | None = None) -> int:
    """Resolve retries after the initial call, with per-node precedence."""
    value = override
    if value is None:
        raw = os.environ.get("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES")
        value = _DEFAULT_MAX_RETRIES if raw is None else int(raw)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("judge max_retries must be a non-negative integer")
    return value


def _default_judge(
    rubric: str, context: "EvalContext", model: Optional[str], sampling: dict | None = None,
    max_retries: int | None = None, reuse: str | None = None,
) -> Tuple[str, str]:
    """Retry judge errors, retaining every request/response in the context.

    Valid positive and negative judgments are final. Exhausted errors receive a
    conservative failed score with a distinct audit status.
    """
    from webarena_pro_core.eval.judge_audit import (
        new_audit, record_attempt, resolve_sampling, response_text, safe_endpoint,
    )

    model = model or os.environ.get("WEBARENAPRO_LLM_JUDGE_MODEL") or _DEFAULT_MODEL
    audit = new_audit(rubric, context, model)
    audit["node_id"] = context.judge_node_id
    cache = context.judge_cache
    cache_key = None
    cache_slot = context.judge_node_id or "__standalone__"
    context.judge_audits.append(audit)
    try:
        from openai import OpenAI

        reuse = reuse if reuse is not None else os.environ.get("WEBARENAPRO_LLM_JUDGE_REUSE", "identical_input")
        if reuse not in {"identical_input", "none"}:
            raise ValueError("judge reuse must be identical_input or none")
        audit["reuse"] = {"policy": reuse, "status": "disabled" if reuse == "none" else "unavailable"}
        max_retries = _resolve_max_retries(max_retries)
        audit["max_retries"] = max_retries
        kwargs = {"max_tokens": _MAX_TOKENS, **_completion_kwargs(model, True)}
        kwargs.update(resolve_sampling(sampling))
        stream = os.environ.get("WEBARENAPRO_LLM_JUDGE_STREAM", "0").strip().lower()
        if stream not in {"0", "1", "false", "true"}:
            raise ValueError("judge stream must be 0, 1, false, or true")
        if stream in {"1", "true"}:
            kwargs.update(stream=True, stream_options={"include_usage": True})
        audit["completion_kwargs"] = kwargs
        config = _client_config(model)
        audit["endpoint"] = safe_endpoint(config["base_url"])
        messages = build_judge_messages(rubric, context)
        # Credentials are used only here, never included in the audit record.
        client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        audit["endpoint"] = safe_endpoint(str(client.base_url))
        audit["sdk_max_retries"] = client.max_retries
        if cache is not None:
            if reuse == "none":
                cache.clear()
            else:
                from webarena_pro_core.eval.judge_cache import input_digest
                unavailable = cache.observe(context)
                audit["reuse"].update(status=unavailable or "miss", scope_id=cache.scope_id)
                if unavailable is None:
                    cache_key = input_digest({
                        "evidence_sha256": cache.evidence_sha256,
                        "prompt_version": audit["prompt_version"],
                        "node_id": context.judge_node_id,
                        "strategy_trace": context.judge_strategy_trace,
                        "model": model, "endpoint": str(client.base_url),
                        "completion_kwargs": kwargs, "max_retries": max_retries,
                        "sdk_max_retries": client.max_retries,
                        "messages": messages,
                    })
                    audit["reuse"]["input_sha256"] = cache_key
                    source = cache.get(cache_slot, cache_key)
                    if source is not None:
                        client.close()
                        audit.update(status=source["status"], verdict=source["verdict"], source_audit=source)
                        audit["reuse"].update(status="hit", source_audit_id=source["audit_id"])
                        return source["verdict"], (
                            f"llm({model}) status={source['status']} -> {source['verdict']} "
                            f"reuse=identical_input source_audit_id={source['audit_id']}"
                        )
    except Exception as error:
        if cache is not None:
            cache.clear()
        audit.update(status="configuration_error", error_type=type(error).__name__)
        return "fail", "configuration_error: check judge model, credentials, sampling and retry configuration"

    variant = "regular"
    retry_messages: list[dict[str, str]] = []
    with client:
        for attempt_index in range(max_retries + 1):
            attempt = record_attempt(
                client, model, [*messages[variant], *retry_messages], kwargs, variant,
            )
            audit["attempts"].append(attempt)
            audit["status"] = attempt["status"]
            audit["verdict"] = attempt.get("verdict")
            if attempt["status"] not in {"parse_error", "model_error"} or attempt_index == max_retries:
                break
            # Keep all evidence for parse repairs. Model errors retain the
            # existing no-axtree fallback, within the same total retry budget.
            if attempt["status"] == "model_error":
                variant = "pruned"
            text = response_text(attempt.get("response"))
            if text:
                retry_messages.append({"role": "assistant", "content": text})
            retry_messages.append({
                "role": "user",
                "content": (
                    f"The previous judge attempt failed: {attempt['error_message']}\n"
                    "Please judge the same rubric again using the supplied evidence. "
                    "Return <reasoning>...</reasoning> followed by exactly one "
                    "<answer>Successful</answer> or <answer>Unsuccessful</answer>."
                ),
            })
            logger.info(
                "llm_judge: retry %s/%s after %s (%s prompt)",
                attempt_index + 1, max_retries, attempt["status"], variant,
            )

    if cache_key is not None:
        attempts = audit["attempts"]
        if len(attempts) == 1 and attempts[0]["variant"] == "regular" and audit["status"] in {"positive", "negative"}:
            cache.put(cache_slot, cache_key, audit)
        else:
            audit["reuse"]["status"] = "not_stored_after_error"
    verdict = audit["verdict"] or "fail"
    return verdict, f"llm({model}) status={audit['status']} -> {verdict}"


class LLMJudgeEvaluator:
    """Grade one rubric with the configured LLM judge hook.

    The evaluator builds a compact multimodal judging prompt from the task
    context and calls either a test hook installed with
    :func:`set_llm_judge_hook` or the default OpenAI-compatible judge. It
    returns a :class:`~webarena_pro_core.eval.dag.NodeResult` whose reason
    records the model/hook verdict for DAG traces.
    """

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult

        rubric = eval_config.get("rubric", "") or eval_config.get("intent", "")
        model = eval_config.get("model")
        if _JUDGE_HOOK is not None:
            if context.judge_cache is not None:
                context.judge_cache.clear()
            verdict, reason = _JUDGE_HOOK(rubric, context, model)
        else:
            verdict, reason = _default_judge(
                rubric, context, model, eval_config.get("sampling"), eval_config.get("max_retries"), eval_config.get("reuse"),
            )
        return NodeResult(passed=(verdict == "pass"), reason=f"[llm_judge] {reason}")
