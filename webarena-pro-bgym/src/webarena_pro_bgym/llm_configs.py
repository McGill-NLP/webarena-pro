import os
import logging
import time
from dataclasses import dataclass, replace
from functools import partial

from agentlab.llm.base_api import BaseModelArgs
from agentlab.llm.chat_api import (
    AIMessage,
    AnthropicChatModel,
    ChatModel,
    OpenAIModelArgs,
    RetryError,
    SelfHostedModelArgs,
    handle_error,
)
from agentlab.llm import tracking
from openai import OpenAI
import openai

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class GeminiChatModel(ChatModel):
    def __init__(
        self,
        model_name,
        temperature=1.0,
        max_tokens=4096,
        log_probs=False,
        reasoning_effort=None,
    ):
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retry=4,
            min_retry_wait_time=60,
            api_key_env_var="GEMINI_API_KEY",
            client_class=OpenAI,
            client_args={"base_url": GEMINI_BASE_URL},
        )
        self.reasoning_effort = reasoning_effort

    def __call__(
        self,
        messages: list[dict],
        n_samples: int = 1,
        temperature: float = None,
    ) -> dict:
        self.retries = 0
        self.success = False
        self.error_types = []

        completion = None
        e = None
        for itr in range(self.max_retry):
            self.retries += 1
            _temperature = temperature if temperature is not None else self.temperature
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "n": n_samples,
                    "temperature": _temperature,
                    "max_completion_tokens": self.max_tokens,
                    # logprobs is not supported by Gemini's OpenAI-compatible endpoint
                }
                if self.reasoning_effort is not None:
                    kwargs["reasoning_effort"] = self.reasoning_effort

                completion = self.client.chat.completions.create(**kwargs)
                self.success = True
                break
            except openai.OpenAIError as e:
                error_type = handle_error(e, itr, self.min_retry_wait_time, self.max_retry)
                self.error_types.append(error_type)

        if not completion:
            raise RetryError(
                f"Failed to get a response from the API after {self.max_retry} retries\n"
                f"Last error: {error_type}"
            )

        def as_message(choice):
            if choice.message is None or choice.message.content is None:
                finish = getattr(choice, "finish_reason", "unknown")
                logging.warning(
                    "[GeminiChatModel] Empty response, finish_reason=%s", finish,
                )
                # AgentLab retries empty answers when its action parser rejects
                # them. Raising here would bypass that parser retry loop.
                return AIMessage("")
            return AIMessage(choice.message.content)

        if n_samples == 1:
            return as_message(completion.choices[0])
        return [as_message(choice) for choice in completion.choices]


class OpenRouterChatModel(ChatModel):
    def __init__(
        self,
        model_name,
        temperature=1.0,
        max_tokens=4096,
        max_retry=4,
        log_probs=False,
        extra_body: dict | None = None,
    ):
        super().__init__(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retry=max_retry,
            min_retry_wait_time=60,
            api_key_env_var="OPENROUTER_API_KEY",
            client_class=OpenAI,
            client_args={"base_url": OPENROUTER_BASE_URL},
            log_probs=log_probs,
        )
        self.extra_body = extra_body

    def __call__(
        self,
        messages: list[dict],
        n_samples: int = 1,
        temperature: float = None,
    ) -> dict:
        self.retries = 0
        self.success = False
        self.error_types = []

        completion = None
        error_type = None
        for itr in range(self.max_retry):
            self.retries += 1
            _temperature = temperature if temperature is not None else self.temperature
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "n": n_samples,
                    "temperature": _temperature,
                    "max_tokens": self.max_tokens,
                }
                if self.extra_body is not None:
                    kwargs["extra_body"] = self.extra_body

                completion = self.client.chat.completions.create(**kwargs)
                self.success = True
                break
            except openai.OpenAIError as e:
                error_type = handle_error(e, itr, self.min_retry_wait_time, self.max_retry)
                self.error_types.append(error_type)

        if not completion:
            raise RetryError(
                f"Failed to get a response from the API after {self.max_retry} retries\n"
                f"Last error: {error_type}"
            )

        if n_samples == 1:
            return AIMessage(completion.choices[0].message.content or "")
        return [AIMessage(c.message.content or "") for c in completion.choices]


class VLLMEndpointChatModel(ChatModel):
    def __init__(
        self,
        model_name,
        model_url=None,
        api_key=None,
        temperature=1.0,
        max_tokens=4096,
        n_retry_server=4,
        log_probs=False,
        extra_body: dict | None = None,
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retry=n_retry_server,
            min_retry_wait_time=60,
            api_key_env_var="VLLM_API_KEY",
            client_class=OpenAI,
            client_args={
                "base_url": model_url
                or os.getenv("VLLM_API_URL", "http://localhost:8000/v1"),
            },
            pricing_func=None,
            log_probs=log_probs,
        )
        self.extra_body = extra_body

    def __call__(self, messages: list[dict], n_samples: int = 1, temperature: float = None) -> dict:
        self.retries = 0
        self.success = False
        self.error_types = []

        completion = None
        e = None
        for itr in range(self.max_retry):
            self.retries += 1
            _temperature = temperature if temperature is not None else self.temperature
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "n": n_samples,
                    "temperature": _temperature,
                    "max_completion_tokens": self.max_tokens,
                    "logprobs": self.log_probs,
                }
                if self.extra_body is not None:
                    kwargs["extra_body"] = self.extra_body

                completion = self.client.chat.completions.create(**kwargs)
                self.success = True
                break
            except openai.OpenAIError as e:
                error_type = handle_error(e, itr, self.min_retry_wait_time, self.max_retry)
                self.error_types.append(error_type)

        if not completion:
            raise RetryError(
                f"Failed to get a response from the API after {self.max_retry} retries\n"
                f"Last error: {error_type}"
            )

        if n_samples == 1:
            return AIMessage(completion.choices[0].message.content or "")
        else:
            return [AIMessage(c.message.content or "") for c in completion.choices]


class OpenAIReasoningChatModel(ChatModel):
    def __init__(
        self,
        model_name,
        api_key=None,
        temperature=1.0,
        max_tokens=4096,
        max_retry=4,
        min_retry_wait_time=60,
        log_probs=False,
        reasoning_effort="high",
        verbosity=None,
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            max_retry=max_retry,
            min_retry_wait_time=min_retry_wait_time,
            api_key_env_var="OPENAI_API_KEY",
            client_class=OpenAI,
            pricing_func=partial(tracking.get_pricing_litellm, model_name=model_name),
            log_probs=log_probs,
        )
        self.reasoning_effort = reasoning_effort
        self.verbosity = verbosity

    def __call__(
        self,
        messages: list[dict],
        n_samples: int = 1,
        temperature: float = None,
    ) -> dict:
        self.retries = 0
        self.success = False
        self.error_types = []

        completion = None
        error_type = None
        for itr in range(self.max_retry):
            self.retries += 1
            _temperature = temperature if temperature is not None else self.temperature
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": messages,
                    "n": n_samples,
                    "temperature": _temperature,
                    "max_completion_tokens": self.max_tokens,
                    "reasoning_effort": self.reasoning_effort,
                    "logprobs": self.log_probs,
                }
                if self.verbosity is not None:
                    kwargs["verbosity"] = self.verbosity

                completion = self.client.chat.completions.create(**kwargs)
                self.success = True
                break
            except openai.OpenAIError as e:
                error_type = handle_error(e, itr, self.min_retry_wait_time, self.max_retry)
                self.error_types.append(error_type)

        if not completion:
            raise RetryError(
                f"Failed to get a response from the API after {self.max_retry} retries\n"
                f"Last error: {error_type}"
            )

        if completion.usage is not None:
            input_tokens = completion.usage.prompt_tokens
            output_tokens = completion.usage.completion_tokens
            cost = input_tokens * self.input_cost + output_tokens * self.output_cost
            if hasattr(tracking.TRACKER, "instance") and isinstance(
                tracking.TRACKER.instance, tracking.LLMTracker
            ):
                tracking.TRACKER.instance(input_tokens, output_tokens, cost)

        if n_samples == 1:
            res = AIMessage(completion.choices[0].message.content or "")
            if self.log_probs:
                res["log_probs"] = completion.choices[0].log_probs
            return res
        return [AIMessage(c.message.content or "") for c in completion.choices]


def _anthropic_image_source(image_url: str | dict) -> dict:
    if isinstance(image_url, dict):
        image_url = image_url.get("url", "")

    if image_url.startswith("data:"):
        header, separator, data = image_url.partition(",")
        if not separator or ";base64" not in header:
            raise ValueError("Anthropic image blocks require base64 data URLs or image URLs")
        media_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
        return {
            "type": "base64",
            "media_type": media_type,
            "data": data,
        }

    return {
        "type": "url",
        "url": image_url,
    }


def _convert_openai_content_block_to_anthropic(block: dict) -> dict:
    block_type = block.get("type")
    if block_type == "image_url":
        return {
            "type": "image",
            "source": _anthropic_image_source(block.get("image_url", "")),
        }
    if block_type == "input_image":
        return {
            "type": "image",
            "source": _anthropic_image_source(block.get("image_url", "")),
        }
    if block_type == "input_text":
        return {
            "type": "text",
            "text": block.get("text", ""),
        }
    return block


def _convert_openai_content_to_anthropic(content):
    if isinstance(content, list):
        return [
            _convert_openai_content_block_to_anthropic(block)
            if isinstance(block, dict)
            else {"type": "text", "text": str(block)}
            for block in content
        ]
    return content


class AnthropicThinkingChatModel(AnthropicChatModel):
    def __init__(
        self,
        model_name,
        api_key=None,
        max_tokens=4096,
        max_retry=4,
        thinking=None,
        output_config=None,
    ):
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            temperature=0.1,
            max_tokens=max_tokens,
            max_retry=max_retry,
            pricing_func=partial(tracking.get_pricing_litellm, model_name=model_name),
        )
        self.thinking = thinking
        self.output_config = output_config

    def __call__(
        self,
        messages: list[dict],
        n_samples: int = 1,
        temperature: float = None,
    ) -> dict:
        self.retries = 0
        self.success = False
        self.error_types = []

        system_message = None
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = _convert_openai_content_to_anthropic(msg["content"])
            else:
                anthropic_messages.append(
                    {
                        "role": msg["role"],
                        "content": _convert_openai_content_to_anthropic(msg["content"]),
                    }
                )

        for attempt in range(self.max_retry):
            self.retries += 1
            try:
                kwargs = {
                    "model": self.model_name,
                    "messages": anthropic_messages,
                    "max_tokens": self.max_tokens,
                }

                if system_message:
                    kwargs["system"] = system_message
                if self.thinking is not None:
                    kwargs["thinking"] = self.thinking
                if self.output_config is not None:
                    kwargs["output_config"] = self.output_config

                response = self.client.messages.create(**kwargs)
                self.success = True

                usage = getattr(response, "usage", {})
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
                cost = input_tokens * self.input_cost + output_tokens * self.output_cost
                if hasattr(tracking.TRACKER, "instance") and isinstance(
                    tracking.TRACKER.instance, tracking.LLMTracker
                ):
                    tracking.TRACKER.instance(input_tokens, output_tokens, cost)

                text_blocks = [
                    block.text
                    for block in response.content
                    if getattr(block, "type", None) == "text"
                ]
                return AIMessage("".join(text_blocks))

            except Exception as e:
                self.error_types.append(type(e).__name__)
                if getattr(e, "status_code", None) == 400 or attempt == self.max_retry - 1:
                    raise e
                logging.warning("Anthropic API error (attempt %s): %s", attempt + 1, e)
                time.sleep(60)

        raise RetryError(f"Failed to get a response from the API after {self.max_retry} retries")


@dataclass
class GeminiModelArgs(BaseModelArgs):
    audio_support: bool = False
    video_support: bool = False
    reasoning_effort: str | None = None

    def make_model(self):
        if self.video_support:
            from webarena_pro_bgym.gemini_media import GeminiMediaChatModel
            return GeminiMediaChatModel(
                model_name=self.model_name,
                temperature=self.temperature,
                max_tokens=self.max_new_tokens,
                max_input_tokens=self.max_input_tokens or self.max_total_tokens,
                reasoning_effort=self.reasoning_effort,
                audio_support=self.audio_support,
            )
        return GeminiChatModel(
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
            log_probs=self.log_probs,
            reasoning_effort=self.reasoning_effort,
        )


@dataclass
class OpenAIReasoningModelArgs(BaseModelArgs):
    reasoning_effort: str = "high"
    verbosity: str | None = None

    def make_model(self):
        return OpenAIReasoningChatModel(
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
            log_probs=self.log_probs,
            reasoning_effort=self.reasoning_effort,
            verbosity=self.verbosity,
        )


@dataclass
class OpenRouterModelArgs(BaseModelArgs):
    audio_support: bool = False
    reasoning_effort: str | None = None
    extra_body: dict | None = None

    def make_model(self):
        extra_body = dict(self.extra_body or {})
        if self.reasoning_effort is not None:
            extra_body["reasoning"] = {"effort": self.reasoning_effort}
        return OpenRouterChatModel(
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
            log_probs=self.log_probs,
            extra_body=extra_body or None,
        )


@dataclass
class AnthropicThinkingModelArgs(BaseModelArgs):
    thinking: dict | None = None
    output_config: dict | None = None

    def make_model(self):
        return AnthropicThinkingChatModel(
            model_name=self.model_name,
            max_tokens=self.max_new_tokens,
            thinking=self.thinking,
            output_config=self.output_config,
        )


@dataclass
class VLLMEndpointModelArgs(SelfHostedModelArgs):
    audio_support: bool = False
    extra_body: dict | None = None

    def make_model(self):
        api_key = self.token or os.getenv("VLLM_API_KEY", "EMPTY")
        if self.backend != "vllm":
            return super().make_model()

        return VLLMEndpointChatModel(
            model_name=self.model_name,
            model_url=self.model_url,
            api_key=api_key,
            temperature=self.temperature,
            max_tokens=self.max_new_tokens,
            n_retry_server=self.n_retry_server,
            log_probs=self.log_probs,
            extra_body=self.extra_body,
        )


@dataclass
class OpenAIAudioModelArgs(OpenAIModelArgs):
    """Chat Completions audio input with text action output (no reasoning args)."""

    audio_support: bool = True


def validate_audio_support(model_args) -> bool:
    """Negotiate the adapter separately from the model's declared capability."""
    enabled = getattr(model_args, "audio_support", False)
    if not enabled:
        return False
    if not isinstance(model_args, (GeminiModelArgs, OpenRouterModelArgs, VLLMEndpointModelArgs, OpenAIAudioModelArgs)):
        raise ValueError("audio_support requires a supported Chat Completions audio adapter.")
    if isinstance(model_args, VLLMEndpointModelArgs) and model_args.backend != "vllm":
        raise ValueError("audio_support for self-hosted models requires backend='vllm'.")
    return True


def validate_video_support(model_args) -> bool:
    """Video input requires a verified adapter, not merely image capability."""
    if not getattr(model_args, "video_support", False):
        return False
    if not isinstance(model_args, GeminiModelArgs):
        raise ValueError("video_support requires the Gemini native media adapter.")
    return True


GEMINI_CHAT_MODEL_ARGS_DICT = {
    "gemini/gemini-2.5-pro": GeminiModelArgs(
        model_name="gemini-2.5-pro",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
    "gemini/gemini-2.5-flash": GeminiModelArgs(
        model_name="gemini-2.5-flash",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
    "gemini/gemini-3-flash-preview": GeminiModelArgs(
        model_name="gemini-3-flash-preview",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
    "gemini/gemini-3.5-flash": GeminiModelArgs(
        model_name="gemini-3.5-flash",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
    "gemini/gemini-3.1-pro-preview": GeminiModelArgs(
        model_name="gemini-3.1-pro-preview",
        temperature=1.0,  # To reduce hallucinated URLs in WebArena-Pro evals
        reasoning_effort="high",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
    "gemini/gemini-3.1-flash-lite-preview": GeminiModelArgs(
        model_name="gemini-3.1-flash-lite-preview",
        reasoning_effort="high",
        max_total_tokens=1_048_576,
        max_input_tokens=1_048_576,
        max_new_tokens=65_536,
        vision_support=True,
    ),
}

OPENAI_CHAT_MODEL_ARGS_DICT = {
    "openai/gpt-5.4": OpenAIReasoningModelArgs(
        model_name="gpt-5.4",
        temperature=1.0,
        reasoning_effort="high",
        max_total_tokens=1_000_000,
        max_input_tokens=872_000,
        max_new_tokens=128_000,
        vision_support=True,
    ),
    "openai/gpt-5.5": OpenAIReasoningModelArgs(
        model_name="gpt-5.5",
        temperature=1.0,
        reasoning_effort="high",
        max_total_tokens=1_000_000,
        max_input_tokens=872_000,
        max_new_tokens=128_000,
        vision_support=True,
    ),
}

OPENROUTER_CHAT_MODEL_ARGS_DICT = {
    "openrouter/kimi-k2.5": OpenRouterModelArgs(
        model_name="moonshotai/kimi-k2.5",
        temperature=1.0,
        reasoning_effort="high",
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "openrouter/kimi-k2.6": OpenRouterModelArgs(
        model_name="moonshotai/kimi-k2.6",
        temperature=1.0,
        reasoning_effort="high",
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
}

ANTHROPIC_CHAT_MODEL_ARGS_DICT = {
    "anthropic/claude-opus-4-7": AnthropicThinkingModelArgs(
        model_name="claude-opus-4-7",
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        max_total_tokens=1_000_000,
        max_input_tokens=984_000,
        max_new_tokens=16_000,
        vision_support=True,
    ),
}

VLLM_CHAT_MODEL_ARGS_DICT = {
    "vllm/qwen35-9b": VLLMEndpointModelArgs(
        model_name="Qwen/Qwen3.5-9B",
        model_url="https://vllm-qwen35-9b-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "vllm/qwen36-27b": VLLMEndpointModelArgs(
        model_name="Qwen/Qwen3.6-27B",
        model_url="https://vllm-qwen36-27b-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "vllm/qwen36-35b-a3b": VLLMEndpointModelArgs(
        model_name="Qwen/Qwen3.6-35B-A3B",
        model_url="https://vllm-qwen36-35b-a3b-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "vllm/qwen36-36b-moe": VLLMEndpointModelArgs(
        model_name="Qwen/Qwen3.6-36B-MoE",
        model_url="https://vllm-qwen36-36b-moe-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "vllm/gemma4-26b-a4b": VLLMEndpointModelArgs(
        model_name="google/gemma-4-26B-A4B-it",
        model_url="https://vllm-gemma4-26b-a4b-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        temperature=1.0,
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
    "vllm/gemma4-31b": VLLMEndpointModelArgs(
        model_name="google/gemma-4-31B-it",
        model_url="https://vllm-gemma4-31b-sn.mcgill-nlp.org/v1",
        backend="vllm",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        temperature=1.0,
        max_total_tokens=262_144,
        max_input_tokens=245_760,
        max_new_tokens=16_384,
        vision_support=True,
    ),
}

WEBARENA_PRO_CHAT_MODEL_ARGS_DICT = {
    **GEMINI_CHAT_MODEL_ARGS_DICT,
    **OPENAI_CHAT_MODEL_ARGS_DICT,
    **OPENROUTER_CHAT_MODEL_ARGS_DICT,
    **ANTHROPIC_CHAT_MODEL_ARGS_DICT,
    **VLLM_CHAT_MODEL_ARGS_DICT,
    # Explicit opt-in aliases; the actual provider model ID stays unchanged.
    **{f"{key}-audio": replace(args, audio_support=True)
       for key, args in GEMINI_CHAT_MODEL_ARGS_DICT.items()},
    **{f"{key}-omni": replace(args, audio_support=True, video_support=True)
       for key, args in GEMINI_CHAT_MODEL_ARGS_DICT.items()},
}
