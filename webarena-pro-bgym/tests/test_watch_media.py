"""Action-to-native-request coverage; live paid evidence is recorded separately."""

from copy import deepcopy
import json

import httpx
import pytest
from browsergym.utils.obs import flatten_axtree_to_str

from webarena_pro_bgym.benchmark import env
from webarena_pro_bgym.benchmark.benchmark import WebArenaProActionSetArgs
from webarena_pro_bgym.gemini_media import GeminiMediaChatModel
from webarena_pro_bgym.llm_configs import (
    GeminiModelArgs, OpenRouterModelArgs, WEBARENA_PRO_CHAT_MODEL_ARGS_DICT,
    validate_video_support,
)
from webarena_pro_media import sync_api as media
from tests.test_omni_media import agent_args, clip_fixture, execute, observation


def video_fixture(mode="detail", audio=True):
    return {
        "url": "https://example.test/video", "start": 1200.0, "end": 1230.0,
        "duration": 30.0, "source_duration": 3600.0, "mode": mode,
        "representation": "sampled_frames" if mode == "overview" else "video",
        "audio_included": audio if mode != "overview" else False,
        "fps": 1.0, "video_b64": "bXA0", "estimated_input_tokens": 32000,
        "frames": [{"timestamp": 1215.0, "image_b64": "anBlZw=="}] if mode == "overview" else [],
    }


@pytest.fixture(autouse=True)
def clear_results():
    env._drain_listen_results()
    env._drain_watch_results()
    yield
    env._drain_listen_results()
    env._drain_watch_results()


def test_audio_only_listen_and_explicit_removed_argument(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "extract_media_clip", lambda *a, **kw: calls.append(kw) or clip_fixture())
    actions = WebArenaProActionSetArgs(subsets=("custom",), audio_support=True).make_action_set()
    execute(actions, 'listen("https://example.test/media", 1, 2)')
    assert calls[0]["n_frames"] == 0
    with pytest.raises(TypeError, match="n_frames"):
        execute(actions, 'listen("https://example.test/media", 1, 2, n_frames=3)')


def test_capabilities_are_explicit_and_preset_is_unchanged():
    plain = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.5-flash"]
    omni = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.5-flash-omni"]
    assert not plain.audio_support and not plain.video_support
    assert omni.audio_support and omni.video_support and omni.model_name == plain.model_name
    assert "watch" in agent_args(omni).flags.action.action_set.make_action_set().action_set
    assert "watch" not in agent_args(plain).flags.action.action_set.make_action_set().action_set
    other = OpenRouterModelArgs(model_name="unverified")
    other.video_support = True
    with pytest.raises(ValueError, match="native media adapter"):
        validate_video_support(other)


def test_per_agent_limits_and_audio_capabilities_reach_action(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "extract_watch_clip", lambda *a, **kw: calls.append(kw) or video_fixture())
    video_only = WebArenaProActionSetArgs(subsets=("custom",), video_support=True, watch_token_budget=8192).make_action_set()
    omni = WebArenaProActionSetArgs(subsets=("custom",), video_support=True, audio_support=True, watch_token_budget=16384).make_action_set()
    execute(video_only, 'watch("https://example.test/video", 0, 10, mode="detail", include_audio=True)')
    assert "no audio support" in env._drain_watch_results()[0]["error"]
    assert calls == []
    execute(omni, 'watch("https://example.test/video", 0, 10, mode="detail", include_audio=True)')
    assert calls[-1]["max_input_tokens"] == 16384
    env._drain_watch_results()
    execute(video_only, 'watch("https://example.test/video")')
    assert calls[-1]["max_input_tokens"] == 2048
    execute(video_only, 'watch("https://example.test/video")')
    assert "one video" in env._drain_watch_results()[-1]["error"]


@pytest.mark.parametrize("mode,audio", [("detail", True), ("detail", False), ("overview", False)])
def test_watch_reaches_native_sdk_and_is_not_replayed(monkeypatch, mode, audio):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    args = agent_args(GeminiModelArgs(model_name="gemini-3.5-flash", audio_support=audio,
                                    video_support=True, vision_support=True,
                                    max_input_tokens=1_000_000, max_new_tokens=1000))
    agent = args.make_agent()
    requests = []

    def respond(request):
        assert request.url.path == "/v1beta/models/gemini-3.5-flash:generateContent"
        assert request.headers["x-goog-api-key"] == "test"
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "modelVersion": "provider-served-version", "usageMetadata": {"promptTokenCount": 123, "candidatesTokenCount": 20},
            "candidates": [{"content": {"parts": [{"text": "<think>Inspected the evidence.</think><action>done()</action>"}]}, "finishReason": "STOP"}],
        })

    agent.chat_llm.native_client.close()
    agent.chat_llm.native_client = httpx.Client(base_url="https://fixture.test/v1beta", headers={"x-goog-api-key": "test"}, transport=httpx.MockTransport(respond))
    clip = video_fixture(mode, audio)
    monkeypatch.setattr(media, "extract_watch_clip", lambda *a, **kw: deepcopy(clip))
    execute(agent.action_set, f'watch("https://example.test/video", 1200, 1230, mode="{mode}", include_audio={audio})')
    obs = observation("Describe the video's movement and sound")
    env.WebArenaProBrowserEnv._inject_watch_results_into_axtree(None, obs)
    obs["axtree_txt"] = flatten_axtree_to_str(obs["axtree_object"])
    action, info = agent.get_action(agent.obs_preprocessor(obs))
    assert action == "done()"
    parts = [part for content in requests[0]["contents"] for part in content["parts"]]
    inline = [p for p in parts if "inlineData" in p]
    expected_mime = "image/jpeg" if mode == "overview" else "video/mp4"
    assert [p["inlineData"]["mimeType"] for p in inline] == [expected_mime]
    if mode != "overview":
        assert inline[0]["videoMetadata"] == {"fps": 1.0}
        assert inline[0]["inlineData"]["data"] == clip["video_b64"]
    text = "\n".join(p.get("text", "") for p in parts)
    assert "1200.0--1230.0" in text
    assert f"audio included: {audio}" in text
    assert agent.chat_llm.last_response_metadata["served_model"] == "provider-served-version"
    next_obs = observation()
    env.WebArenaProBrowserEnv._inject_watch_results_into_axtree(None, next_obs)
    agent.get_action(agent.obs_preprocessor(next_obs))
    assert not any("inlineData" in p for c in requests[1]["contents"] for p in c["parts"])
    assert "bXA0" not in str(info.chat_messages)
    agent.chat_llm.native_client.close()


def test_native_rejects_unsupported_blocks_and_budget_before_network(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    model = GeminiMediaChatModel("gemini-3.5-flash", max_input_tokens=100, max_tokens=10)
    model.native_client.close()
    model.native_client = httpx.Client(transport=httpx.MockTransport(lambda request: pytest.fail("No request allowed")))
    with pytest.raises(ValueError, match="context allowance"):
        model([{"role": "user", "content": "a" * 101}])
    with pytest.raises(ValueError, match="Unsupported"):
        model([{"role": "user", "content": [{"type": "video_url"}]}])
    with pytest.raises(ValueError, match="audio_support"):
        model([{"role": "user", "content": [{"type": "input_audio", "input_audio": {"format": "wav", "data": ""}}]}])
    model.native_client.close()


def test_watch_error_is_observable_without_axtree(monkeypatch):
    def fail(*args, **kwargs):
        raise media.MediaClipError("Select a shorter interval")
    monkeypatch.setattr(media, "extract_watch_clip", fail)
    actions = WebArenaProActionSetArgs(subsets=("custom",), video_support=True).make_action_set()
    execute(actions, 'watch("https://example.test/video", 1, 99999, mode="detail")')
    obs = {}
    env.WebArenaProBrowserEnv._inject_watch_results_into_axtree(None, obs)
    assert obs["video_clips"][0]["error"] == "Select a shorter interval"


def test_combined_attachment_limit_is_an_action_error(monkeypatch):
    clip = video_fixture()
    clip["attachment_bytes"] = 8 * 1024 * 1024
    monkeypatch.setattr(media, "extract_watch_clip", lambda *a, **kw: deepcopy(clip))
    monkeypatch.setattr(media, "extract_media_clip", lambda *a, **kw: clip_fixture())
    actions = WebArenaProActionSetArgs(subsets=("custom",), video_support=True, audio_support=True).make_action_set()
    execute(actions, 'listen("https://example.test/audio", 1, 2)')
    execute(actions, 'watch("https://example.test/video", mode="detail")')
    result = env._drain_watch_results()[0]
    assert "Combined media attachments" in result["error"]
    assert "video_b64" not in result


def test_overview_reserves_image_token_allowance(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "extract_watch_clip", lambda *a, **kw: calls.append(kw) or video_fixture("overview", False))
    actions = WebArenaProActionSetArgs(subsets=("custom",), video_support=True, watch_token_budget=16384).make_action_set()
    execute(actions, 'watch("https://example.test/video", max_frames=4)')
    assert calls[0]["max_input_tokens"] == 4096
    assert calls[0]["max_frames"] == 4


def test_native_audio_and_size_limit_are_not_silently_dropped(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    model = GeminiMediaChatModel("gemini-3.5-flash", audio_support=True,
                                max_input_tokens=100000, max_tokens=100)
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "heard"}]}}]})
    model.native_client.close()

    model.native_client = httpx.Client(base_url="https://fixture.test/v1beta", transport=httpx.MockTransport(respond))
    audio = clip_fixture()["audio_b64"]
    messages = [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": audio, "format": "wav"}}]}]
    model(messages)
    part = requests[0]["contents"][0]["parts"][0]
    assert part["inlineData"] == {"mimeType": "audio/wav", "data": audio}
    monkeypatch.setattr("webarena_pro_bgym.gemini_media.MAX_REQUEST_BYTES", 10)
    with pytest.raises(ValueError, match="20 MiB"):
        model(messages)
    assert len(requests) == 1
    assert model.get_stats()["native_cost_unavailable"] == 1
    model.native_client.close()


@pytest.mark.parametrize("finish,retry", [("MALFORMED_RESPONSE", True), ("SAFETY", False)])
def test_native_empty_response_retry_is_bounded_and_accounts_usage(monkeypatch, finish, retry):
    from agentlab.llm import tracking
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    model = GeminiMediaChatModel("gemini-3.5-flash", max_tokens=100)
    calls = []
    def respond(request):
        calls.append(request)
        candidate = {"finishReason": finish} if len(calls) == 1 else {
            "content": {"parts": [{"text": "done"}]}, "finishReason": "STOP",
        }
        return httpx.Response(200, json={"candidates": [candidate],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 2}})
    model.native_client.close()
    model.native_client = httpx.Client(base_url="https://fixture.test/v1beta", transport=httpx.MockTransport(respond))
    with tracking.set_tracker() as tracked:
        if retry:
            assert model([{"role": "user", "content": "test"}])["content"] == "done"
        else:
            with pytest.raises(RuntimeError, match=finish):
                model([{"role": "user", "content": "test"}])
    assert len(calls) == (2 if retry else 1)
    assert tracked.input_tokens == len(calls) * 10
    assert tracked.output_tokens == len(calls) * 2
    assert len(model.last_response_metadata["attempts"]) == len(calls)
    model.native_client.close()


def test_native_repeated_malformed_response_stops_after_one_retry(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    model = GeminiMediaChatModel("gemini-3.5-flash", max_tokens=100)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"candidates": [{"finishReason": "MALFORMED_RESPONSE"}]})
    model.native_client.close()
    model.native_client = httpx.Client(base_url="https://fixture.test/v1beta", transport=httpx.MockTransport(respond))
    with pytest.raises(RuntimeError, match="MALFORMED_RESPONSE"):
        model([{"role": "user", "content": "test"}])
    assert len(calls) == 2
    model.native_client.close()
