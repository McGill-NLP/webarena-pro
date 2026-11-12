"""Exercise actions -> observations -> GenericAgent -> actual SDK JSON bodies.

Task intents are real; media and model responses are deterministic fixtures.
These tests establish evidence delivery, not benchmark score improvements.
"""

import base64
from copy import deepcopy
import io
import json
from types import SimpleNamespace
import wave

import httpx
import numpy as np
import pytest
from openai import OpenAI
from agentlab.agents.generic_agent import GenericAgentArgs
from browsergym.utils.obs import flatten_axtree_to_str

from webarena_pro_bgym.agent import configure_media
from webarena_pro_bgym.agent_flags import FLAGS_VISION
from webarena_pro_bgym.benchmark.benchmark import WebArenaProActionSetArgs
from webarena_pro_bgym.benchmark import env
from webarena_pro_bgym.llm_configs import (
    GeminiModelArgs,
    OpenAIAudioModelArgs,
    OpenRouterModelArgs,
    VLLMEndpointModelArgs,
    AnthropicThinkingModelArgs,
    WEBARENA_PRO_CHAT_MODEL_ARGS_DICT,
    validate_audio_support,
)
from webarena_pro_bgym.study import WebArenaProStudy
from webarena_pro_media import sync_api as media
from webarena_pro_core.splits import load_split_tasks


def clip_fixture(video=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x01\x00\xff\xff" * 24000)
    return {
        "url": "https://example.test/media",
        "start": 1.0,
        "end": 2.0,
        "duration": 1.0,
        "requested_start": 1.0,
        "requested_end": 2.0,
        "audio_b64": base64.b64encode(buffer.getvalue()).decode(),
        "format": "wav",
        "mime_type": "audio/wav",
        "sample_rate": 24000,
        "channels": 2,
        "frames": [{"timestamp": 1.5, "image_b64": "anBlZw=="}] if video else [],
    }


def observation(intent="Describe the media"):
    return {
        "axtree_object": {
            "nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "childIds": []}]
        },
        "dom_object": {
            "strings": ["HTML", ""],
            "documents": [
                {
                    "nodes": {
                        "nodeName": [0],
                        "nodeType": [1],
                        "nodeValue": [1],
                        "parentIndex": [-1],
                        "attributes": [[]],
                        "contentDocumentIndex": {"index": [], "value": []},
                    }
                }
            ],
        },
        "extra_element_properties": {},
        "screenshot": np.zeros((8, 8, 3), dtype=np.uint8),
        "axtree_txt": "",
        "pruned_html": "",
        "last_action_error": "",
        "focused_element_bid": "",
        "goal_object": [{"type": "text", "text": intent}],
        "chat_messages": [],
        "open_pages_urls": ["https://example.test"],
        "open_pages_titles": ["Media"],
        "active_page_index": 0,
    }


def agent_args(model_args):
    flags = deepcopy(FLAGS_VISION)
    flags.obs.use_screenshot = flags.obs.use_som = False
    flags.action.action_set = WebArenaProActionSetArgs(
        subsets=("webarena", "custom"), multiaction=False
    )
    args = GenericAgentArgs(chat_model_args=model_args, flags=flags)
    configure_media(args)
    return args


def execute(action_set, action):
    exec(action_set.to_python_code(action), {"page": object(), "DEMO_MODE": False})


@pytest.fixture(autouse=True)
def clear_pending():
    env._drain_listen_results()
    env._drain_watch_results()
    env._drain_frames_results()
    env._drain_transcribe_results()
    yield
    env._drain_listen_results()
    env._drain_watch_results()
    env._drain_frames_results()
    env._drain_transcribe_results()


@pytest.mark.parametrize(
    "task_id,site",
    [
        ("029", "acidwave"),
        ("033", "acidwave"),
        ("356", "yt-lite"),
        ("398", "acidwave"),
    ],
)
@pytest.mark.parametrize(
    "model_type",
    [GeminiModelArgs, VLLMEndpointModelArgs, OpenRouterModelArgs, OpenAIAudioModelArgs],
)
def test_representative_task_evidence_reaches_sdk_json(
    monkeypatch, task_id, site, model_type
):
    task = next(
        t
        for t in load_split_tasks("dev")
        if t["task_id"] == task_id
    )
    assert site in task["sites"]
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    # Avoid remote pricing lookup in AgentLab. The network boundary below is local.
    monkeypatch.setattr(
        "agentlab.llm.tracking.get_pricing_litellm",
        lambda **kw: {"test-omni": {"prompt": 0.0, "completion": 0.0}},
    )
    kwargs = {"backend": "vllm"} if model_type is VLLMEndpointModelArgs else {}
    model_args = model_type(
        model_name="test-omni",
        audio_support=True,
        vision_support=True,
        max_new_tokens=1000,
        **kwargs,
    )
    args = agent_args(model_args)
    agent = args.make_agent()
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-omni",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "<think>I received the media.</think><action>done()</action>",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                },
            },
        )

    agent.chat_llm.client.close()
    agent.chat_llm.client = OpenAI(
        api_key="test",
        base_url="https://fixture.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    clip = clip_fixture()
    monkeypatch.setattr(media, "extract_media_clip", lambda *a, **kw: deepcopy(clip))
    execute(agent.action_set, 'listen("https://example.test/media", 1, 2)')
    obs = observation(task["intent"])
    env.WebArenaProBrowserEnv._inject_listen_results_into_axtree(None, obs)
    obs["axtree_txt"] = flatten_axtree_to_str(obs["axtree_object"])
    obs = agent.obs_preprocessor(obs)
    action, info = agent.get_action(obs)
    assert action == "done()"
    content = requests[0]["messages"][1]["content"]
    audio_blocks = [b for b in content if b["type"] == "input_audio"]
    assert audio_blocks == [
        {
            "type": "input_audio",
            "input_audio": {"data": clip["audio_b64"], "format": "wav"},
        }
    ]
    text = "\n".join(b["text"] for b in content if b["type"] == "text")
    assert "Source interval: 1.0--2.0 seconds" in text
    assert "24000 Hz, 2 channels" in text
    images = [b for b in content if b["type"] == "image_url"]
    assert images == []
    assert env._drain_listen_results() == []
    # Next step can retain text/history but must not replay the clip payload.
    next_obs = observation(task["intent"])
    env.WebArenaProBrowserEnv._inject_listen_results_into_axtree(None, next_obs)
    agent.get_action(next_obs)
    assert not any(
        b["type"] == "input_audio" for b in requests[1]["messages"][1]["content"]
    )
    assert clip["audio_b64"] not in str(info.chat_messages)
    agent.chat_llm.client.close()


def test_text_only_configuration_and_local_transcription_fallback(monkeypatch):
    args = agent_args(
        GeminiModelArgs(model_name="text", audio_support=False, vision_support=False)
    )
    actions = args.flags.action.action_set.make_action_set()
    assert "listen" not in actions.action_set
    assert "extract_frames" not in actions.action_set
    assert "transcribe" in actions.action_set
    calls = []
    monkeypatch.setattr(
        media, "transcribe_media", lambda *a, **kw: calls.append(kw) or "speech only"
    )
    execute(actions, 'transcribe("https://example.test/media", 1, 2, use_api=False)')
    obs = observation()
    env.WebArenaProBrowserEnv._inject_transcribe_results_into_axtree(None, obs)
    assert "speech only" in flatten_axtree_to_str(obs["axtree_object"])
    assert calls[0]["use_api"] is False
    assert "media_clips" not in obs


def test_capability_negotiation_does_not_mutate_preset_and_rejects_unsupported_adapter():
    preset = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.1-pro-preview"]
    enabled = WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.1-pro-preview-audio"]
    assert not preset.audio_support and enabled.audio_support
    assert preset.model_name == enabled.model_name
    assert not FLAGS_VISION.action.action_set.__dict__.get("audio_support", False)
    model = AnthropicThinkingModelArgs(model_name="unsupported")
    model.audio_support = True
    with pytest.raises(ValueError, match="adapter"):
        validate_audio_support(model)
    with pytest.raises(ValueError, match="backend"):
        validate_audio_support(
            VLLMEndpointModelArgs(
                model_name="test", audio_support=True, backend="huggingface"
            )
        )


def test_study_disables_background_transcription_only_for_opted_in_model():
    environment = SimpleNamespace(
        task_name="example", task_seed=0, enable_audio=True, audio_transcribe=True
    )
    benchmark = SimpleNamespace(
        name="webarena-pro-test",
        is_multi_tab=False,
        high_level_action_set_args=WebArenaProActionSetArgs(
            subsets=("webarena", "custom")
        ),
        env_args_list=[environment],
        dependency_graph_over_tasks=lambda: {},
    )
    for enabled in (True, False):
        args = agent_args(GeminiModelArgs(model_name="test", audio_support=enabled))
        study = object.__new__(WebArenaProStudy)
        experiments = study.agents_on_benchmark(
            [args], benchmark, ignore_dependencies=True
        )
        assert experiments[0].env_args.enable_audio is (not enabled)
        assert experiments[0].env_args.audio_transcribe is (not enabled)
        assert args.flags.action.action_set.audio_support is enabled
    assert environment.enable_audio and environment.audio_transcribe


def test_multi_clip_limit_errors_and_missing_axtree(monkeypatch):
    clip = clip_fixture()
    monkeypatch.setattr(media, "extract_media_clip", lambda *a, **kw: deepcopy(clip))
    actions = WebArenaProActionSetArgs(
        subsets=("custom",), audio_support=True
    ).make_action_set()
    for _ in range(3):
        execute(actions, 'listen("https://example.test/media", 1, 2)')
    obs = {}
    env.WebArenaProBrowserEnv._inject_listen_results_into_axtree(None, obs)
    assert len(obs["media_clips"]) == 3
    assert sum("audio_b64" in c for c in obs["media_clips"]) == 2
    assert "two clips" in obs["media_clips"][2]["error"]


def test_clip_errors_are_observable_and_reset_clears_pending(monkeypatch):
    def fail(*a, **kw):
        raise media.MediaClipError("Could not fetch media")

    monkeypatch.setattr(media, "extract_media_clip", fail)
    actions = WebArenaProActionSetArgs(
        subsets=("custom",), audio_support=True
    ).make_action_set()
    execute(actions, 'listen("https://example.test/media", 1, 2)')
    obs = observation()
    env.WebArenaProBrowserEnv._inject_listen_results_into_axtree(None, obs)
    assert "status=error" in flatten_axtree_to_str(obs["axtree_object"])
    assert "Could not fetch" in obs["media_clips"][0]["error"]
    execute(actions, 'listen("https://example.test/media", 1, 2)')
    monkeypatch.setattr(env.WebArenaProBrowserEnv, "reset", lambda self, seed: ({}, {}))
    instance = object.__new__(env.WebArenaProEnv)
    instance.reset()
    assert env._drain_listen_results() == []


@pytest.mark.parametrize(
    "audio_support,vision_support", [(False, False), (False, True), (True, False)]
)
def test_prompt_rechecks_capabilities_for_existing_media(audio_support, vision_support):
    from webarena_pro_bgym.agent import WebArenaProMainPrompt

    args = agent_args(
        GeminiModelArgs(
            model_name="test",
            audio_support=audio_support,
            vision_support=vision_support,
        )
    )
    obs = observation()
    obs["media_clips"] = [clip_fixture(video=True)]
    obs["extracted_frames"] = [{"timestamp": 1.5, "image_b64": "anBlZw=="}]
    prompt = WebArenaProMainPrompt(
        action_set=args.flags.action.action_set.make_action_set(),
        obs_history=[obs],
        actions=[],
        memories=[],
        thoughts=[],
        previous_plan="",
        step=0,
        flags=args.flags,
    ).prompt
    blocks = prompt["content"]
    assert sum(b["type"] == "input_audio" for b in blocks) == int(audio_support)
    # Even old checkpoint listen() results must no longer attach video frames.
    assert sum(b["type"] == "image_url" for b in blocks) == int(vision_support)
    if not audio_support:
        assert "Use transcribe()" in str(prompt)


def test_prompt_shows_invalid_range_error_without_formatting_crash():
    from webarena_pro_bgym.agent import WebArenaProMainPrompt

    args = agent_args(GeminiModelArgs(model_name="test", audio_support=True))
    obs = observation()
    obs["media_clips"] = [
        {
            "url": "https://example.test/media",
            "start": "bad",
            "end": 2,
            "error": "Clip times must be finite numbers.",
        }
    ]
    prompt = WebArenaProMainPrompt(
        action_set=args.flags.action.action_set.make_action_set(),
        obs_history=[obs],
        actions=[],
        memories=[],
        thoughts=[],
        previous_plan="",
        step=0,
        flags=args.flags,
    ).prompt
    assert "Media error: Clip times must be finite numbers." in str(prompt)
    assert not any(b["type"] == "input_audio" for b in prompt["content"])
