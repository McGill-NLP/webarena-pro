"""Regression coverage for evidence, error classification and frozen replays."""
import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from openai.types.chat import ChatCompletion

from webarena_pro_core.eval import judge_audit, llm_judge
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext, parse_eval_dag


def response(text, **kwargs):
    return ChatCompletion(id="returned-id", object="chat.completion", created=1, model="resolved-model-v2",
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, **kwargs)


@pytest.fixture
def client(monkeypatch):
    import openai
    client = Mock()
    client.base_url = "https://judge.example/v1/"
    client.max_retries = 2
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(openai, "OpenAI", Mock(return_value=client))
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MODEL", "gemini-test")
    monkeypatch.delenv("WEBARENAPRO_LLM_JUDGE_SAMPLING", raising=False)
    monkeypatch.delenv("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", raising=False)
    monkeypatch.delenv("WEBARENAPRO_LLM_JUDGE_STREAM", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET_KEY_MUST_NOT_BE_SAVED")
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", None)
    return client


def context():
    return EvalContext(
        task_config={"task_id": "382", "original_task_id": "20260504022131958379", "intent": "Watch the video"},
        trajectory=[{"obs": {"url": "http://yt-lite/watch/1"}, "action": "click('play')", "agent_info": {"think": "play video"}}],
        last_step_output={"obs": {"axtree_txt": "VIDEO PLAYING", "screenshot": np.zeros((2, 2, 3), dtype=np.uint8)}},
        task_start_date="2026-10-19",
    )


@pytest.mark.parametrize("answer,status", [("Successful", "positive"), ("Unsuccessful", "negative")])
def test_real_sdk_assembles_stream_before_scoring(answer, status):
    import httpx
    from openai import OpenAI

    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "", "reasoning_content": "Check "}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"reasoning_content": "evidence.", "content": "<answer>"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {"content": answer + "</answer>"}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
    ]
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        content = "".join("data: " + json.dumps({"id": "stream-id", "model": "resolved-model", "created": 1,
            "object": "chat.completion.chunk", **chunk}) + "\n\n" for chunk in chunks)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=content + "data: [DONE]\n\n")

    kwargs = {"stream": True, "stream_options": {"include_usage": True}, "temperature": 0.6, "max_tokens": 4096}
    with OpenAI(api_key="test-secret", http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk:
        attempt = judge_audit.record_attempt(sdk, "requested-model", [{"role": "user", "content": "Judge"}], kwargs, "regular")
    assert attempt["status"] == status
    assert attempt["request"] == requests[0]
    assert attempt["response"]["choices"][0]["message"]["reasoning_content"] == "Check evidence."
    assert attempt["response"]["usage"]["total_tokens"] == 15
    assert "test-secret" not in json.dumps(attempt)


@pytest.mark.parametrize("finish,content,status", [
    (None, "<answer>Successful</answer>", "model_error"),
    ("length", "Incomplete answer", "parse_error"),
])
def test_incomplete_stream_cannot_publish_partial_verdict(finish, content, status):
    import httpx
    from openai import OpenAI

    chunk = {"id": "partial", "model": "test", "created": 1, "object": "chat.completion.chunk",
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": finish}]}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"},
        text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n"))
    with OpenAI(api_key="test", http_client=httpx.Client(transport=transport)) as sdk:
        attempt = judge_audit.record_attempt(sdk, "test", [], {"stream": True}, "regular")
    assert attempt["status"] == status and attempt["verdict"] is None


def test_streaming_is_opt_in_and_frozen_replay_retains_transport(client, monkeypatch):
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_STREAM", "1")
    completed = response("<answer>Successful</answer>")
    client.chat.completions.stream.return_value = nullcontext(SimpleNamespace(
        until_done=lambda: None, current_completion_snapshot=completed,
    ))
    ctx = context()
    assert llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    audit = ctx.judge_audits[0]
    request = audit["attempts"][0]["request"]
    assert request["stream"] and request["stream_options"] == {"include_usage": True}
    client.chat.completions.create.assert_not_called()
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_STREAM", "0")
    replay = judge_audit.replay_audit(audit, repeats=1)
    assert replay["attempts"][0]["request"] == request
    assert replay["attempts"][0]["status"] == "positive"


def test_invalid_stream_setting_is_a_configuration_error(client, monkeypatch):
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_STREAM", "invalid")
    ctx = context()
    assert not llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    assert ctx.judge_audits[0]["status"] == "configuration_error"
    client.chat.completions.create.assert_not_called()
    client.chat.completions.stream.assert_not_called()


def test_persists_exact_evidence_raw_explanation_and_effective_config(client):
    raw = "<reasoning>Video is still playing; no end observed.</reasoning><answer>Unsuccessful</answer>"
    client.chat.completions.create.return_value = response(raw)
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "Watch the full video"}, ctx)
    audit = ctx.judge_audits[0]
    attempt = audit["attempts"][0]
    assert not result.passed and "negative" in result.reason
    assert audit["task_id"] == "382"
    assert "original_task_id" not in audit
    assert audit["task_start_date"] == "2026-10-19"
    assert audit["completion_kwargs"] == {"temperature": 1.0, "top_p": 0.95, "max_tokens": 4096}
    assert attempt["request"] == client.chat.completions.create.call_args.kwargs
    assert attempt["response"]["choices"][0]["message"]["content"] == raw
    assert attempt["response"]["model"] == "resolved-model-v2"
    assert attempt["parsed_answer"] == "unsuccessful"
    assert "data:image/png;base64," in json.dumps(attempt["request"])
    assert "VIDEO PLAYING" in json.dumps(attempt["request"])
    assert "SECRET_KEY_MUST_NOT_BE_SAVED" not in json.dumps(audit)
    assert len(attempt["request_sha256"]) == 64


@pytest.mark.parametrize("text,status,passed", [
    ("<answer>Successful</answer>", "positive", True),
    ("<answer>Unsuccessful</answer>", "negative", False),
    ("<answer>In Progress</answer>", "negative", False),
    ("no answer tag", "parse_error", False),
    ("<answer>maybe</answer>", "parse_error", False),
    ("<answer>Successful</answer><answer>Unsuccessful</answer>", "parse_error", False),
    (None, "parse_error", False),
])
def test_negative_parse_and_positive_are_distinct_without_changing_score(client, text, status, passed):
    client.chat.completions.create.return_value = response(text)
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "max_retries": 0}, ctx)
    assert result.passed is passed
    assert ctx.judge_audits[0]["status"] == status
    assert client.chat.completions.create.call_count == 1


def test_failed_and_pruned_requests_both_saved_without_exception_secrets(client):
    client.chat.completions.create.side_effect = [RuntimeError("SECRET in request"), response("<answer>Successful</answer>")]
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    attempts = ctx.judge_audits[0]["attempts"]
    assert [a["status"] for a in attempts] == ["model_error", "positive"]
    assert "VIDEO PLAYING" in json.dumps(attempts[0]["request"])
    assert "VIDEO PLAYING" not in json.dumps(attempts[1]["request"])
    assert "data:image/png" in json.dumps(attempts[1]["request"])
    assert "SECRET" not in json.dumps(attempts)


def test_model_error_is_failed_score_not_negative_judgment(client):
    client.chat.completions.create.side_effect = RuntimeError("hidden request body")
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    assert not result.passed and "model_error" in result.reason
    assert ctx.judge_audits[0]["verdict"] is None
    assert len(ctx.judge_audits[0]["attempts"]) == 4


@pytest.mark.parametrize("sampling", [{"temperature": 0}, {"top_p": 0.4, "seed": 5, "max_tokens": 32}])
def test_sampling_is_configurable_with_node_precedence(client, monkeypatch, sampling):
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_SAMPLING", '{"temperature":0.2}')
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "sampling": sampling}, ctx)
    effective = ctx.judge_audits[0]["completion_kwargs"]
    assert effective.items() >= sampling.items()
    assert effective["temperature"] == sampling.get("temperature", 0.2)


@pytest.mark.parametrize("sampling", [{"temperature": -1}, {"temperature": float("nan")}, {"top_p": 0}, {"max_tokens": 0}, {"seed": True}, {"seed": 1.2}, {"api_key": "secret"}, []])
def test_bad_config_never_calls_model_or_exposes_config_contents(client, sampling):
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "sampling": sampling}, ctx)
    assert not result.passed and "configuration_error" in result.reason
    assert not ctx.judge_audits[0]["attempts"]
    assert "secret" not in json.dumps(ctx.judge_audits)
    client.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("environment_model", [None, ""])
@pytest.mark.parametrize("base_url", [None, "https://router.example/v1"])
def test_default_judge_uses_qwen_on_openrouter(client, monkeypatch, environment_model, base_url):
    import openai

    monkeypatch.delenv("WEBARENAPRO_LLM_JUDGE_MODEL")
    if environment_model is not None:
        monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MODEL", environment_model)
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    if base_url is not None:
        monkeypatch.setenv("OPENROUTER_BASE_URL", base_url)
    endpoint = base_url or "https://openrouter.ai/api/v1"
    client.base_url = endpoint
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    assert llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    openai.OpenAI.assert_called_once_with(api_key="router-secret", base_url=endpoint)
    audit = ctx.judge_audits[0]
    assert audit["model"] == "qwen/qwen3.6-27b"
    assert audit["endpoint"] == endpoint
    assert audit["completion_kwargs"] == {"temperature": 0.6, "top_p": 0.95, "max_tokens": 4096}
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == "qwen/qwen3.6-27b"
    assert "extra_body" not in request
    assert "router-secret" not in json.dumps(audit)


@pytest.mark.parametrize("environment_model,node_model,expected_model,provider", [
    ("gemini-test", None, "gemini-test", "GEMINI"),
    ("gemini-test", "gpt-test", "gpt-test", "OPENAI"),
    ("gemini-test", "qwen/qwen3.6-27b", "qwen/qwen3.6-27b", "OPENROUTER"),
    ("qwen/qwen3.6-27b", "Qwen/Qwen3.6-27B", "Qwen/Qwen3.6-27B", "VLLM"),
    ("vllm/qwen36-27b", None, "vllm/qwen36-27b", "VLLM"),
])
def test_model_overrides_preserve_provider_configuration(client, monkeypatch, environment_model, node_model, expected_model, provider):
    import openai

    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MODEL", environment_model)
    monkeypatch.setenv(f"{provider}_API_KEY", "provider-secret")
    monkeypatch.setenv(f"{provider}_BASE_URL", "https://provider.example/v1")
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    assert llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "model": node_model}, ctx).passed
    openai.OpenAI.assert_called_once_with(api_key="provider-secret", base_url="https://provider.example/v1")
    assert ctx.judge_audits[0]["model"] == expected_model
    request = client.chat.completions.create.call_args.kwargs
    assert request["model"] == expected_model
    if provider == "VLLM":
        assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
    else:
        assert "extra_body" not in request


def test_default_judge_replay_uses_openrouter_credentials(client, monkeypatch):
    import openai

    monkeypatch.delenv("WEBARENAPRO_LLM_JUDGE_MODEL")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")
    client.base_url = "https://openrouter.ai/api/v1"
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    audit = ctx.judge_audits[0]
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MODEL", "gemini-test")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://changed.example/v1")
    openai.OpenAI.reset_mock()
    client.chat.completions.create.reset_mock()
    judge_audit.replay_audit(audit, repeats=1)
    openai.OpenAI.assert_called_once_with(
        api_key="router-secret", base_url="https://openrouter.ai/api/v1", max_retries=2,
    )
    assert client.chat.completions.create.call_args.kwargs == audit["attempts"][0]["request"]


def test_missing_default_judge_credentials_are_audited(monkeypatch):
    monkeypatch.setattr(llm_judge, "_JUDGE_HOOK", None)
    for name in ("WEBARENAPRO_LLM_JUDGE_MODEL", "WEBARENAPRO_LLM_JUDGE_SAMPLING",
                 "WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    ctx = context()
    assert not llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    assert ctx.judge_audits[0]["status"] == "configuration_error"
    assert ctx.judge_audits[0]["model"] == "qwen/qwen3.6-27b"
    assert not ctx.judge_audits[0]["attempts"]


def test_dag_keeps_audits_for_each_tiered_node_and_failed_terminal_score(client):
    client.chat.completions.create.side_effect = [response("<answer>Successful</answer>"), response("malformed")]
    config = {"scoring": "partial", "nodes": [
        {"id": "watched", "type": "tiered", "eval_config": {"strategies": [
            {"tier": 2, "type": "llm_judge", "config": {"rubric": "watched video"}}]}},
        {"id": "answered", "type": "llm_judge", "eval_config": {"rubric": "answered question", "max_retries": 0}},
    ]}
    ctx = context()
    score, results = DAGEvaluator(parse_eval_dag(config)).evaluate(ctx)
    assert score == 0.5
    assert results["watched"]["judge_audits"][0]["status"] == "positive"
    assert results["answered"]["judge_audits"][0]["status"] == "parse_error"
    assert len(results["watched"]["judge_audits"]) == 1
    assert len(judge_audit.find_audits(json.loads(json.dumps(results)))) == 2
    # Reusing a context never attaches old audits to a new node invocation.
    client.chat.completions.create.side_effect = [response("<answer>Unsuccessful</answer>"), response("bad")]
    _, new = DAGEvaluator(parse_eval_dag(config)).evaluate(ctx)
    assert len(new["watched"]["judge_audits"]) == 1
    assert new["watched"]["judge_audits"][0]["status"] == "negative"


def test_replay_freezes_actual_pruned_request_and_reports_errors_separately(client, monkeypatch):
    client.chat.completions.create.side_effect = [RuntimeError(), response("<answer>Successful</answer>")]
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    source = ctx.judge_audits[0]
    # Older saved audits remain replayable without copying their obsolete ID.
    source["original_task_id"] = "20260504022131958379"
    expected = source["attempts"][-1]["request"]
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_SAMPLING", '{"temperature":0}')
    client.chat.completions.create.reset_mock(side_effect=True)
    client.chat.completions.create.side_effect = [response("<answer>Successful</answer>"), response("<answer>Unsuccessful</answer>"), response("malformed"), RuntimeError()]
    replay = judge_audit.replay_audit(source, repeats=4)
    assert replay["task_id"] == "382"
    assert "original_task_id" not in replay
    assert all(call.kwargs == expected for call in client.chat.completions.create.call_args_list)
    assert replay["source_attempt_index"] == 1
    assert replay["agreement"]["pairwise_agreement"] == 0
    assert replay["agreement"]["valid_verdicts"] == 2
    assert replay["agreement"]["status_counts"] == {"positive": 1, "negative": 1, "parse_error": 1, "model_error": 1}
    assert replay["agreement"]["usage"]["total_tokens"] == 45


def test_agreement_denominator_and_unanimity():
    values = [{"verdict": v, "status": "positive" if v == "pass" else "negative", "elapsed_seconds": 1} for v in ["pass", "pass", "fail"]]
    stats = judge_audit.agreement_report(values)
    assert stats["pairwise_agreement"] == 1 / 3
    assert stats["unanimous"] is False
    assert judge_audit.agreement_report(values[:1])["pairwise_agreement"] is None


def test_cli_writes_replay_artifact_and_wont_overwrite(client, tmp_path):
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    source, output = tmp_path / "audit.json", tmp_path / "replay.json"
    source.write_text(json.dumps(ctx.judge_audits))
    args = [str(source), "--output", str(output), "--repeats", "3", "--sampling", '{"temperature":0}']
    judge_audit.main(args)
    saved = json.loads(output.read_text())
    assert saved["cases"][0]["agreement"]["pairwise_agreement"] == 1
    assert saved["cases"][0]["attempts"][0]["request"]["temperature"] == 0
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        judge_audit.main(args)


def test_endpoint_does_not_persist_embedded_credentials():
    assert judge_audit.safe_endpoint("https://user:password@example/v1?api_key=secret#token") == "https://example/v1"


@pytest.mark.parametrize("invalid", [[], False, 0])
def test_replay_rejects_falsey_invalid_sampling_before_any_call(client, invalid):
    client.chat.completions.create.return_value = response("<answer>Successful</answer>")
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    client.chat.completions.create.reset_mock()
    with pytest.raises(ValueError, match="JSON object"):
        judge_audit.replay_audit(ctx.judge_audits[0], sampling=invalid)
    client.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("raw", [
    {"choices": [None]},
    {"choices": "unexpected string"},
    {"choices": [{"message": None}]},
    {"choices": [{"message": "unexpected string"}]},
    {"choices": [{"message": {"content": ["unexpected array"]}}]},
    {"choices": [], "usage": "unexpected string"},
])
def test_malformed_provider_envelope_retains_request_and_response(client, raw):
    # Compatible-provider responses may bypass strict SDK response validation.
    client.chat.completions.create.return_value = Mock(model_dump=Mock(return_value=raw))
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "max_retries": 0}, ctx)
    audit = ctx.judge_audits[0]
    attempt = audit["attempts"][0]
    assert not result.passed and audit["status"] == "parse_error"
    assert attempt["response"] == raw
    assert attempt["request"] == client.chat.completions.create.call_args.kwargs
    assert client.chat.completions.create.call_count == 1
    assert judge_audit.agreement_report([attempt])["valid_verdicts"] == 0


@pytest.mark.parametrize("raw", [None, [], "unexpected JSON scalar"])
def test_non_object_provider_json_is_audited(client, raw):
    client.chat.completions.create.return_value = raw
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    audit = ctx.judge_audits[0]
    assert not result.passed and audit["status"] == "parse_error"
    assert audit["attempts"][0]["response"] == raw
    assert judge_audit.agreement_report(audit["attempts"])["valid_verdicts"] == 0


@pytest.mark.parametrize("malformed,error", [
    ("no answer tag", "Expected exactly one <answer>...</answer> tag."),
    ("<answer>maybe</answer>", "The <answer> value must be Successful, Unsuccessful or In Progress."),
    ("<answer>Successful</answer><answer>Unsuccessful</answer>", "Expected exactly one <answer>...</answer> tag."),
    (None, "Expected text in choices[0].message.content."),
])
def test_parse_retry_passes_response_and_error_with_original_evidence(client, malformed, error):
    client.chat.completions.create.side_effect = [response(malformed), response("<answer>Successful</answer>")]
    ctx = context()
    assert llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    audit = ctx.judge_audits[0]
    first, second = audit["attempts"]
    assert audit["max_retries"] == 3
    assert audit["status"] == "positive"
    assert [a["status"] for a in audit["attempts"]] == ["parse_error", "positive"]
    assert [a["variant"] for a in audit["attempts"]] == ["regular", "regular"]
    messages = second["request"]["messages"]
    assert messages[:2] == first["request"]["messages"]
    assert "VIDEO PLAYING" in json.dumps(messages)
    assert "data:image/png" in json.dumps(messages)
    assert first["error_message"] == error
    assert error in messages[-1]["content"]
    assert messages[-1]["role"] == "user"
    if malformed is not None:
        assert messages[-2] == {"role": "assistant", "content": malformed}
    else:
        assert len(messages) == 3
    assert first["request"] == client.chat.completions.create.call_args_list[0].kwargs
    assert second["request"] == client.chat.completions.create.call_args_list[1].kwargs
    assert first["request_sha256"] != second["request_sha256"]


def test_judge_can_recover_on_third_retry(client):
    client.chat.completions.create.side_effect = [
        response("no tag"), response("<answer>maybe</answer>"), response(None),
        response("<answer>Successful</answer>"),
    ]
    ctx = context()
    assert llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx).passed
    attempts = ctx.judge_audits[0]["attempts"]
    assert len(attempts) == 4
    for previous, current in zip(attempts, attempts[1:]):
        assert previous["error_message"] in current["request"]["messages"][-1]["content"]
    assert attempts[-1]["status"] == "positive"


def test_parse_retries_exhaust_with_distinct_failed_status(client):
    client.chat.completions.create.return_value = response("malformed")
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    audit = ctx.judge_audits[0]
    assert not result.passed and "parse_error" in result.reason
    assert audit["status"] == "parse_error" and audit["verdict"] is None
    assert len(audit["attempts"]) == 4
    assert client.chat.completions.create.call_count == 4


@pytest.mark.parametrize("answer", ["Successful", "Unsuccessful", "In Progress"])
@pytest.mark.parametrize("initial_parse_error", [False, True])
def test_valid_judgments_stop_retries_immediately(client, answer, initial_parse_error):
    replies = [response("malformed")] if initial_parse_error else []
    replies.append(response(f"<answer>{answer}</answer>"))
    client.chat.completions.create.side_effect = replies
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    assert result.passed is (answer == "Successful")
    assert client.chat.completions.create.call_count == len(replies)
    assert ctx.judge_audits[0]["status"] == ("positive" if result.passed else "negative")


@pytest.mark.parametrize("environment,override,expected_calls", [
    (None, 0, 1), (None, 1, 2), (None, 5, 6), ("0", None, 1),
    ("2", None, 3), ("2", 0, 1), ("0", 2, 3), ("invalid", 0, 1),
])
@pytest.mark.parametrize("failure", ["parse", "model"])
def test_retry_budget_is_configurable_with_node_precedence(client, monkeypatch, environment, override, expected_calls, failure):
    if environment is not None:
        monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", environment)
    if failure == "parse":
        client.chat.completions.create.return_value = response("malformed")
    else:
        client.chat.completions.create.side_effect = RuntimeError()
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "max_retries": override}, ctx)
    assert client.chat.completions.create.call_count == expected_calls
    assert ctx.judge_audits[0]["max_retries"] == expected_calls - 1


@pytest.mark.parametrize("invalid", [-1, True, False, 1.5, "2", [], {}])
def test_invalid_node_retry_budget_fails_before_model_call(client, invalid):
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "max_retries": invalid}, ctx)
    assert not result.passed and "configuration_error" in result.reason
    assert ctx.judge_audits[0]["status"] == "configuration_error"
    assert not ctx.judge_audits[0]["attempts"]
    client.chat.completions.create.assert_not_called()


@pytest.mark.parametrize("invalid", ["-1", "1.5", "true", "", "secret-value"])
def test_invalid_environment_retry_budget_is_not_persisted(client, monkeypatch, invalid):
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", invalid)
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    assert not result.passed and "configuration_error" in result.reason
    assert ctx.judge_audits[0]["status"] == "configuration_error"
    assert "secret-value" not in json.dumps(ctx.judge_audits)
    client.chat.completions.create.assert_not_called()


def test_model_and_parse_errors_share_retry_budget_and_keep_safe_feedback(client):
    error = RuntimeError("SECRET in request headers")
    error.status_code = 503
    client.chat.completions.create.side_effect = [
        error, response("<answer>maybe</answer>"), error, response("<answer>Successful</answer>"),
    ]
    ctx = context()
    result = llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch", "max_retries": 2}, ctx)
    audit = ctx.judge_audits[0]
    assert not result.passed and audit["status"] == "model_error"
    assert [a["status"] for a in audit["attempts"]] == ["model_error", "parse_error", "model_error"]
    assert [a["variant"] for a in audit["attempts"]] == ["regular", "pruned", "pruned"]
    assert client.chat.completions.create.call_count == 3
    retry = audit["attempts"][1]["request"]["messages"][-1]["content"]
    assert "RuntimeError" in retry and "503" in retry
    assert "SECRET" not in json.dumps(audit)


def test_tiered_strategy_uses_its_own_retry_configuration(client, monkeypatch):
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", "5")
    client.chat.completions.create.side_effect = [response("malformed"), response("<answer>Successful</answer>")]
    config = {"nodes": [{
        "id": "watched", "type": "tiered", "eval_config": {"strategies": [
            {"tier": 2, "type": "llm_judge", "config": {"rubric": "watched video", "max_retries": 1}},
        ]},
    }]}
    score, results = DAGEvaluator(parse_eval_dag(config)).evaluate(context())
    audit = results["watched"]["judge_audits"][0]
    assert score == 1
    assert audit["max_retries"] == 1
    assert [a["status"] for a in audit["attempts"]] == ["parse_error", "positive"]


def test_replay_freezes_parse_error_feedback_and_does_not_retry(client, monkeypatch):
    client.chat.completions.create.side_effect = [response("malformed"), response("<answer>Successful</answer>")]
    ctx = context()
    llm_judge.LLMJudgeEvaluator().evaluate({"rubric": "watch"}, ctx)
    audit = ctx.judge_audits[0]
    expected = audit["attempts"][-1]["request"]
    assert "Expected exactly one" in expected["messages"][-1]["content"]
    monkeypatch.setenv("WEBARENAPRO_LLM_JUDGE_MAX_RETRIES", "10")
    client.chat.completions.create.reset_mock(side_effect=True)
    client.chat.completions.create.return_value = response("malformed again")
    replay = judge_audit.replay_audit(audit, repeats=2)
    assert client.chat.completions.create.call_count == 2
    assert all(call.kwargs == expected for call in client.chat.completions.create.call_args_list)
    assert replay["agreement"]["status_counts"] == {"parse_error": 2}
