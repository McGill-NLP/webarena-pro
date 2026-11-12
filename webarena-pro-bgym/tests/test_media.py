import sys
from types import SimpleNamespace

import pytest
from webarena_pro_media import audio as core_audio

from browsergym.core.action.highlevel import HighLevelActionSet

import webarena_pro_bgym.benchmark.env as bgym_env
import webarena_pro_media.sync_api as core_media


def test_bgym_env_imports_core_audio_helpers_directly():
    assert bgym_env.extract_audio is core_media.extract_audio
    assert bgym_env.transcribe_audio is core_media.transcribe_audio


def test_transcribe_action_stashes_core_result(monkeypatch):
    monkeypatch.setattr(bgym_env, "page", object(), raising=False)
    monkeypatch.setattr(
        core_media,
        "transcribe_media",
        lambda *args, **kwargs: "transcribed text",
    )
    bgym_env._drain_transcribe_results()

    assert bgym_env.transcribe("https://example.test/audio.mp3", 3, 9) == (
        "transcribed text"
    )
    assert bgym_env._drain_transcribe_results() == [
        {
            "url": "https://example.test/audio.mp3",
            "start": 3,
            "end": 9,
            "transcript": "transcribed text",
        }
    ]


def test_extract_frames_action_stashes_core_result(monkeypatch):
    frames = [{"timestamp": 2.0, "image_b64": "anBlZw=="}]
    monkeypatch.setattr(bgym_env, "page", object(), raising=False)
    monkeypatch.setattr(
        core_media,
        "extract_video_frames",
        lambda *args, **kwargs: frames,
    )
    bgym_env._drain_frames_results()

    assert bgym_env.extract_frames("https://example.test/video.mp4", 1) == ""
    assert bgym_env._drain_frames_results() == [
        {
            "url": "https://example.test/video.mp4",
            "n_frames": 1,
            "start": 0,
            "end": -1,
            "frames": frames,
        }
    ]


def test_browsergym_exec_supplies_page_to_media_action(monkeypatch):
    monkeypatch.setattr(
        core_media,
        "transcribe_media",
        lambda *args, **kwargs: "from BrowserGym",
    )
    bgym_env._drain_transcribe_results()
    action_set = HighLevelActionSet(
        subsets=("custom",),
        custom_actions=[bgym_env.transcribe, bgym_env.extract_frames],
        multiaction=False,
    )

    code = action_set.to_python_code(
        'transcribe("https://example.test/audio.mp3", 2, 4)'
    )
    exec(code, {"page": object(), "DEMO_MODE": False})

    assert bgym_env._drain_transcribe_results()[0]["transcript"] == ("from BrowserGym")


def _observation():
    return {"axtree_object": {"nodes": [
        {"nodeId": "1", "role": {"value": "RootWebArea"}, "childIds": []},
    ]}}


def _execute_transcribe():
    action_set = HighLevelActionSet(
        subsets=("custom",), custom_actions=[bgym_env.transcribe], multiaction=False,
    )
    code = action_set.to_python_code('transcribe("https://example.test/audio.mp3", 2, 4)')
    exec(code, {"page": object(), "DEMO_MODE": False})


def test_empty_success_is_reported_as_no_speech(monkeypatch):
    monkeypatch.setattr(core_media, "transcribe_media", lambda *a, **kw: "")
    bgym_env._drain_transcribe_results()
    _execute_transcribe()
    obs = _observation()
    bgym_env.WebArenaProBrowserEnv._inject_transcribe_results_into_axtree(None, obs)
    label = obs["axtree_object"]["nodes"][-1]["name"]["value"]
    assert "status=no_speech" in label
    assert "failed" not in label


@pytest.mark.parametrize("status,code,hint", [
    (400, "audio_too_short", "duration, format"),
    (413, "request_too_large", "upload size"),
    (401, "invalid_api_key", "OPENAI_API_KEY"),
    (403, "permission_denied", "transcription access"),
    (None, None, "connectivity"),
])
def test_api_errors_reach_actual_custom_action_observation(monkeypatch, status, code, hint):
    class APIError(Exception):
        status_code = status

    error = APIError("sk-private-provider-response")
    error.code = code

    def create(**kwargs):
        raise error

    client = SimpleNamespace(
        audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)), close=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client))
    monkeypatch.setattr(core_media, "transcribe_media", lambda *a, **kw: core_audio._transcribe_api(b"wav"))
    bgym_env._drain_transcribe_results()
    _execute_transcribe()
    obs = _observation()
    bgym_env.WebArenaProBrowserEnv._inject_transcribe_results_into_axtree(None, obs)
    label = obs["axtree_object"]["nodes"][-1]["name"]["value"]
    assert "status=error" in label
    assert hint in label
    if status:
        assert f"HTTP {status}" in label
        assert f"code={code}" in label
    assert "sk-private" not in label
    assert bgym_env._drain_transcribe_results() == []


def test_inline_capture_transcription_error_is_visible_in_observation(monkeypatch):
    env = object.__new__(bgym_env.WebArenaProBrowserEnv)
    env.page = object()
    monkeypatch.setattr(bgym_env.BrowserEnv, "_get_obs", lambda self: _observation())
    monkeypatch.setattr(bgym_env, "extract_audio", lambda *a, **kw: b"captured audio")
    monkeypatch.setattr(env, "_inject_media_sources_into_axtree", lambda obs: None)
    monkeypatch.setattr(env, "_inject_frames_results_into_axtree", lambda obs: None)

    def fail(*a, **kw):
        raise core_media.TranscriptionError("HTTP 401: Check OPENAI_API_KEY")

    monkeypatch.setattr(bgym_env, "transcribe_audio", fail)
    bgym_env._drain_transcribe_results()
    obs = env._get_obs()
    assert obs["audio_segment"] == b"captured audio"
    assert "HTTP 401" in obs["audio_transcript"]
    label = obs["axtree_object"]["nodes"][-1]["name"]["value"]
    assert "status=error" in label
    assert "HTTP 401" in label
