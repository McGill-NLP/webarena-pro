import json
from types import SimpleNamespace

import httpx
import pytest

from webarena_pro_bgym.gemini_media import GeminiMediaChatModel
from webarena_pro_bgym.model_requests import EpisodeTrace
from webarena_pro_core.model_requests import ModelRequest, normalize_usage


def test_native_gemini_modality_splits_and_transport_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-key")
    model = GeminiMediaChatModel("gemini-test")
    model.native_client.close()
    calls = 0

    def serve(request):
        nonlocal calls
        calls += 1
        pending = ModelRequest.model_validate_json((tmp_path / "model_requests.jsonl").read_text().splitlines()[-1])
        assert pending.status == "unresolved" and pending.raw_response_path is None
        assert json.loads((tmp_path / pending.raw_request_path).read_text())["contents"]
        if calls == 1:
            raise httpx.ReadTimeout("no response", request=request)
        return httpx.Response(200, json={
            "responseId": "response-1", "modelVersion": "gemini-served",
            "candidates": [{"content": {"parts": [{"text": "hello"}]}, "finishReason": "STOP"}],
            "usageMetadata": {
                "promptTokenCount": 1000, "cachedContentTokenCount": 400,
                "promptTokensDetails": [{"modality": "TEXT", "tokenCount": 750},
                                        {"modality": "IMAGE", "tokenCount": 250}],
                "cacheTokensDetails": [{"modality": "TEXT", "tokenCount": 300},
                                       {"modality": "IMAGE", "tokenCount": 100}],
                "candidatesTokenCount": 10, "thoughtsTokenCount": 2,
            },
        })

    with httpx.Client(base_url="https://test.invalid", transport=httpx.MockTransport(serve)) as client:
        model.native_client = client
        agent = SimpleNamespace(chat_llm=model)
        with EpisodeTrace(tmp_path).step(agent, 7):
            messages = [{"role": "user", "content": "hello"}]
            with pytest.raises(httpx.ReadTimeout):
                agent.chat_llm(messages)
            assert agent.chat_llm(messages)["content"] == "hello"
        assert agent.chat_llm is model
    failed, ok = [ModelRequest.model_validate_json(line)
                  for line in (tmp_path / "model_requests.jsonl").read_text().splitlines()]
    assert failed.error_type == "ReadTimeout" and failed.raw_response_path is None
    assert json.loads((tmp_path / failed.raw_request_path).read_text())["contents"]
    assert ok.completion_id == "response-1" and ok.finish_reason == "STOP"
    inputs = ok.usage.input_tokens
    assert (inputs.regular, inputs.cached, inputs.total) == (600, 400, 1000)
    assert inputs.by_modality["text"].model_dump() == {"regular": 450, "cached": 300, "total": 750}
    assert inputs.by_modality["image"].model_dump() == {"regular": 150, "cached": 100, "total": 250}
    assert ok.usage.output_tokens.total == 12 and ok.usage.output_tokens.reasoning == 2


def test_partial_counter_coverage():
    inputs = normalize_usage("chat", {"usage": {
        "prompt_tokens": 1000, "prompt_tokens_details": {"audio_tokens": 80},
    }}).input_tokens
    assert inputs.regular is inputs.cached is None
    assert inputs.by_modality["audio"].model_dump() == {"total": 80, "regular": None, "cached": None}
    usage = normalize_usage("anthropic", {"usage": {
        "input_tokens": 2, "cache_creation_input_tokens": 4582, "cache_read_input_tokens": 12859,
        "output_tokens": 231, "output_tokens_details": {"thinking_tokens": 0},
    }})
    assert usage.input_tokens.model_dump() == {
        "regular": 4584, "cached": 12859, "total": 17443, "cache_write": 4582, "by_modality": {},
    }
    assert usage.output_tokens.reasoning == 0


def test_redaction_keeps_provider_payload_shape():
    from webarena_pro_bgym.model_requests import _redact

    payload = {
        "metadata": {"accessToken": "abc", "clientSecret": "def"},
        "content": 'https://name:pass@example.org/x?key=ghi&v=1\nAuthorization: Bearer jkl',
        "tool_calls": [{"arguments": '{"password":"mno","count":42}'}],
        "usage": {"cached_tokens": 400},
    }
    result = _redact(payload, [])
    assert result["metadata"] == {"accessToken": "[REDACTED]", "clientSecret": "[REDACTED]"}
    assert result["content"] == 'https://[REDACTED]@example.org/x?key=[REDACTED]&v=1\nAuthorization: [REDACTED]'
    assert result["usage"] == payload["usage"]
    assert json.loads(result["tool_calls"][0]["arguments"]) == {"password": "[REDACTED]", "count": 42}
