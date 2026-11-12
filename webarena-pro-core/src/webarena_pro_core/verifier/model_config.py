"""Small model endpoint registry used by the core rubric verifier.

The BrowserGym integration has richer AgentLab ``ChatModel`` definitions. Core
only needs the OpenAI-compatible endpoint metadata required to issue tool-call
requests directly, so this module deliberately stays independent from AgentLab.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class VerifierModelConfig:
    model_name: str
    model_url: str | None = None
    token: str | None = None
    extra_body: dict[str, Any] | None = None
    reasoning_effort: str | None = None


GEMINI_CHAT_MODEL_ARGS_DICT: dict[str, VerifierModelConfig] = {
    "gemini/gemini-2.5-pro": VerifierModelConfig(
        model_name="gemini-2.5-pro",
    ),
    "gemini/gemini-2.5-flash": VerifierModelConfig(
        model_name="gemini-2.5-flash",
    ),
    "gemini/gemini-3-flash-preview": VerifierModelConfig(
        model_name="gemini-3-flash-preview",
    ),
    "gemini/gemini-3.1-pro-preview": VerifierModelConfig(
        model_name="gemini-3.1-pro-preview",
        reasoning_effort="high",
    ),
    "gemini/gemini-3.1-flash-lite-preview": VerifierModelConfig(
        model_name="gemini-3.1-flash-lite-preview",
        reasoning_effort="high",
    ),
}

OPENROUTER_CHAT_MODEL_ARGS_DICT: dict[str, VerifierModelConfig] = {
    "openrouter/kimi-k2.5": VerifierModelConfig(
        model_name="moonshotai/kimi-k2.5",
        reasoning_effort="high",
    ),
    "openrouter/kimi-k2.6": VerifierModelConfig(
        model_name="moonshotai/kimi-k2.6",
        reasoning_effort="high",
    ),
}

VLLM_CHAT_MODEL_ARGS_DICT: dict[str, VerifierModelConfig] = {
    "vllm/qwen35-9b": VerifierModelConfig(
        model_name="Qwen/Qwen3.5-9B",
        model_url="https://vllm-qwen35-9b-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    "vllm/qwen36-27b": VerifierModelConfig(
        model_name="Qwen/Qwen3.6-27B",
        model_url="https://vllm-qwen36-27b-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    "vllm/qwen36-35b-a3b": VerifierModelConfig(
        model_name="Qwen/Qwen3.6-35B-A3B",
        model_url="https://vllm-qwen36-35b-a3b-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    "vllm/qwen36-36b-moe": VerifierModelConfig(
        model_name="Qwen/Qwen3.6-36B-MoE",
        model_url="https://vllm-qwen36-36b-moe-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    "vllm/gemma4-26b-a4b": VerifierModelConfig(
        model_name="google/gemma-4-26B-A4B-it",
        model_url="https://vllm-gemma4-26b-a4b-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
    "vllm/gemma4-31b": VerifierModelConfig(
        model_name="google/gemma-4-31B-it",
        model_url="https://vllm-gemma4-31b-sn.mcgill-nlp.org/v1",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    ),
}

WEBARENA_PRO_VERIFIER_MODEL_CONFIGS: dict[str, VerifierModelConfig] = {
    **GEMINI_CHAT_MODEL_ARGS_DICT,
    **OPENROUTER_CHAT_MODEL_ARGS_DICT,
    **VLLM_CHAT_MODEL_ARGS_DICT,
}
