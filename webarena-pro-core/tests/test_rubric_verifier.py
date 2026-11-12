from types import SimpleNamespace

import numpy as np

import webarena_pro_core.verifier.rubric_verifier as rubric_verifier
from webarena_pro_core.verifier.rubric_verifier import RubricVerifier


def test_rubric_verifier_qwen_alias_uses_vllm_endpoint(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setattr(rubric_verifier, "OpenAI", FakeOpenAI)
    monkeypatch.delenv("VLLM_API_KEY", raising=False)

    verifier = RubricVerifier.with_model_config(
        ["A criterion"],
        model_config_name="qwen3.6-27b",
    )

    assert (
        RubricVerifier.normalize_model_config_name("qwen3.6-27b")
        == "vllm/qwen36-27b"
    )
    assert verifier.model_name == "Qwen/Qwen3.6-27B"
    assert verifier.completion_kwargs == {
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    }
    assert calls == [
        {
            "api_key": "EMPTY",
            "base_url": "https://vllm-qwen36-27b-sn.mcgill-nlp.org/v1",
        }
    ]


def test_rubric_verifier_kimi_alias_uses_openrouter(monkeypatch):
    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.chat = SimpleNamespace(completions=SimpleNamespace())

    monkeypatch.setattr(rubric_verifier, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    verifier = RubricVerifier.with_model_config(
        ["A criterion"],
        model_config_name="kimi-k2.6",
    )

    assert (
        RubricVerifier.normalize_model_config_name("kimi-k2.6")
        == "openrouter/kimi-k2.6"
    )
    assert verifier.model_name == "moonshotai/kimi-k2.6"
    assert verifier.completion_kwargs == {
        "extra_body": {"reasoning": {"effort": "high"}},
    }
    assert calls == [
        {
            "api_key": "test-key",
            "base_url": "https://openrouter.ai/api/v1",
        }
    ]


def test_rubric_verifier_forwards_completion_kwargs():
    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(tool_calls=[])),
                ],
            )

    fake_completions = FakeCompletions()
    verifier = RubricVerifier(
        ["A criterion"],
        openai_client=SimpleNamespace(
            chat=SimpleNamespace(completions=fake_completions),
        ),
        model_name="Qwen/Qwen3.6-27B",
        completion_kwargs={
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
        },
    )

    screenshot = np.zeros((2, 2, 3), dtype=np.uint8)
    verifier.on_agent_step_end(
        {
            "step": 0,
            "action": "noop",
            "screenshot_before": screenshot,
            "screenshot_after": screenshot,
            "is_final_step": False,
        }
    )

    assert fake_completions.kwargs["model"] == "Qwen/Qwen3.6-27B"
    assert fake_completions.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": True},
    }
    assert fake_completions.kwargs["tools"] == verifier.tool_schema
