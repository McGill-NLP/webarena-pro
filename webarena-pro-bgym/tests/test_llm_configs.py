from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agentlab.llm.chat_api import SelfHostedModelArgs
from agentlab.llm.llm_utils import ParseError, parse_html_tags_raise, retry

from webarena_pro_bgym.llm_configs import (
    OPENROUTER_BASE_URL,
    OPENROUTER_CHAT_MODEL_ARGS_DICT,
    VLLM_CHAT_MODEL_ARGS_DICT,
    WEBARENA_PRO_CHAT_MODEL_ARGS_DICT,
    GeminiChatModel,
)


@pytest.fixture
def gemini_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "EMPTY")
    model = GeminiChatModel("gemini-test")
    model.client = Mock()
    return model


@pytest.mark.parametrize("message", [None, SimpleNamespace(content=None)])
def test_gemini_filtered_message_uses_empty_response_fallback(gemini_model, message, caplog):
    gemini_model.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message, finish_reason="content_filter")],
    )

    response = gemini_model([{"role": "user", "content": "ping"}])

    assert response["content"] == ""
    assert "finish_reason=content_filter" in caplog.text


def test_gemini_normalizes_each_sample_independently(gemini_model):
    gemini_model.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(message=None, finish_reason="content_filter"),
            SimpleNamespace(message=SimpleNamespace(content="pong")),
            SimpleNamespace(message=SimpleNamespace(content=None), finish_reason="length"),
            SimpleNamespace(message=None, finish_reason="content_filter"),
        ],
    )

    responses = gemini_model([{"role": "user", "content": "ping"}], n_samples=4)

    assert [response["content"] for response in responses] == ["", "pong", "", ""]
    assert gemini_model.client.chat.completions.create.call_args.kwargs["n"] == 4


def test_gemini_filtered_message_recovers_through_agentlab_parser_retry(gemini_model):
    gemini_model.client.chat.completions.create.side_effect = [
        SimpleNamespace(choices=[SimpleNamespace(message=None, finish_reason="content_filter")]),
        SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content="<action>noop()</action>"),
        )]),
    ]
    messages = [{"role": "user", "content": "Return an action."}]

    answer = retry(
        gemini_model, messages, n_retry=2,
        parser=lambda content: parse_html_tags_raise(content, keys=("action",)),
    )

    assert answer["action"] == "noop()"
    assert gemini_model.client.chat.completions.create.call_count == 2
    assert messages[1]["content"] == ""
    assert "Missing the key <action>" in messages[2]["content"]


def test_gemini_filtered_message_exhausts_agentlab_parser_retry(gemini_model):
    gemini_model.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=None, finish_reason="content_filter")],
    )

    with pytest.raises(ParseError, match="after 2 retries"):
        retry(
            gemini_model, [{"role": "user", "content": "Return an action."}], n_retry=2,
            parser=lambda content: parse_html_tags_raise(content, keys=("action",)),
        )

    assert gemini_model.client.chat.completions.create.call_count == 2


def test_vllm_configs_match_self_hosted_endpoints():
    thinking_extra_body = {"chat_template_kwargs": {"enable_thinking": True}}
    expected = {
        "vllm/qwen35-9b": (
            "Qwen/Qwen3.5-9B",
            "https://vllm-qwen35-9b-sn.mcgill-nlp.org/v1",
        ),
        "vllm/qwen36-27b": (
            "Qwen/Qwen3.6-27B",
            "https://vllm-qwen36-27b-sn.mcgill-nlp.org/v1",
        ),
        "vllm/qwen36-35b-a3b": (
            "Qwen/Qwen3.6-35B-A3B",
            "https://vllm-qwen36-35b-a3b-sn.mcgill-nlp.org/v1",
        ),
        "vllm/qwen36-36b-moe": (
            "Qwen/Qwen3.6-36B-MoE",
            "https://vllm-qwen36-36b-moe-sn.mcgill-nlp.org/v1",
        ),
        "vllm/gemma4-26b-a4b": (
            "google/gemma-4-26B-A4B-it",
            "https://vllm-gemma4-26b-a4b-sn.mcgill-nlp.org/v1",
        ),
        "vllm/gemma4-31b": (
            "google/gemma-4-31B-it",
            "https://vllm-gemma4-31b-sn.mcgill-nlp.org/v1",
        ),
    }

    assert set(VLLM_CHAT_MODEL_ARGS_DICT) == set(expected)

    for key, (model_name, model_url) in expected.items():
        args = VLLM_CHAT_MODEL_ARGS_DICT[key]

        assert isinstance(args, SelfHostedModelArgs)
        assert args.backend == "vllm"
        assert args.model_name == model_name
        assert args.model_url == model_url
        assert args.max_total_tokens == 262_144
        assert args.max_input_tokens == 245_760
        assert args.max_new_tokens == 16_384
        assert args.extra_body == thinking_extra_body
        assert WEBARENA_PRO_CHAT_MODEL_ARGS_DICT[key] is args


def test_vllm_endpoint_args_use_configured_model_url():
    args = replace(VLLM_CHAT_MODEL_ARGS_DICT["vllm/qwen35-9b"], token="EMPTY")

    model = args.make_model()

    assert str(model.client.base_url).rstrip("/") == args.model_url


def test_vllm_endpoint_uses_dummy_api_key_when_unset(monkeypatch):
    monkeypatch.delenv("VLLM_API_KEY", raising=False)

    model = VLLM_CHAT_MODEL_ARGS_DICT["vllm/qwen35-9b"].make_model()

    assert model.api_key == "EMPTY"


def test_gemini_flash_lite_config_is_registered():
    args = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.1-flash-lite-preview"]

    assert args.model_name == "gemini-3.1-flash-lite-preview"
    assert args.vision_support is True


def test_openrouter_kimi_k2_6_config_is_registered():
    args = OPENROUTER_CHAT_MODEL_ARGS_DICT["openrouter/kimi-k2.6"]

    assert args.model_name == "moonshotai/kimi-k2.6"
    assert args.temperature == 1.0
    assert args.reasoning_effort == "high"
    assert args.vision_support is True
    assert WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["openrouter/kimi-k2.6"] is args


def test_openrouter_kimi_k2_5_config_is_registered():
    args = OPENROUTER_CHAT_MODEL_ARGS_DICT["openrouter/kimi-k2.5"]

    assert args.model_name == "moonshotai/kimi-k2.5"
    assert args.temperature == 1.0
    assert args.reasoning_effort == "high"
    assert args.vision_support is True
    assert WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["openrouter/kimi-k2.5"] is args


def test_openrouter_kimi_model_enables_high_reasoning(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "EMPTY")
    args = OPENROUTER_CHAT_MODEL_ARGS_DICT["openrouter/kimi-k2.6"]
    model = args.make_model()
    base_url = str(model.client.base_url).rstrip("/")

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="pong")),
                ],
            )

    fake_completions = FakeCompletions()
    model.client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake_completions),
    )

    response = model([{"role": "user", "content": "ping"}])

    assert response["content"] == "pong"
    assert base_url == OPENROUTER_BASE_URL
    assert fake_completions.kwargs["temperature"] == 1.0
    assert fake_completions.kwargs["extra_body"] == {
        "reasoning": {"effort": "high"},
    }


def test_qwen_vllm_model_enables_thinking_from_config():
    args = replace(VLLM_CHAT_MODEL_ARGS_DICT["vllm/qwen35-9b"], token="EMPTY")
    model = args.make_model()

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="pong")),
                ],
            )

    fake_completions = FakeCompletions()
    model.client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake_completions),
    )

    response = model([{"role": "user", "content": "ping"}])

    assert response["content"] == "pong"
    assert fake_completions.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
    }


def test_vllm_model_forwards_explicit_extra_body():
    extra_body = {"chat_template_kwargs": {"enable_thinking": False}}
    args = replace(
        VLLM_CHAT_MODEL_ARGS_DICT["vllm/qwen35-9b"],
        token="EMPTY",
        extra_body=extra_body,
    )
    model = args.make_model()

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="pong")),
                ],
            )

    fake_completions = FakeCompletions()
    model.client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake_completions),
    )

    response = model([{"role": "user", "content": "ping"}])

    assert response["content"] == "pong"
    assert fake_completions.kwargs["extra_body"] is extra_body
