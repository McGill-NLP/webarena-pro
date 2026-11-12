"""Transcription regressions; ffmpeg fixtures use no paid API or model downloads."""

import io
import shutil
import subprocess
import sys
from types import SimpleNamespace
import wave

import pytest

from webarena_pro_media.sync_api import TranscriptionError
from webarena_pro_media import audio


def wav_bytes(seconds=1, rate=16000, channels=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\0" * round(seconds * rate) * channels * 2)
    return output.getvalue()


def wav_info(data):
    with wave.open(io.BytesIO(data)) as wav:
        return wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()


@pytest.fixture
def ffmpeg(monkeypatch):
    executable = shutil.which("ffmpeg")
    if executable is None:
        pytest.skip("real-media regression requires a system ffmpeg binary")
    monkeypatch.setattr(audio, "ffmpeg_binary", lambda: executable)
    return executable


@pytest.fixture
def uploads(monkeypatch):
    calls = []

    def transcribe(data, language):
        calls.append((data, language))
        return f"part {len(calls)}"

    monkeypatch.setattr(audio, "_transcribe_api", transcribe)
    return calls


@pytest.mark.parametrize("source_bytes", [26_900_000, 28_200_000, 54_900_000])
def test_report_sized_full_files_are_downsampled_before_upload(ffmpeg, uploads, monkeypatch, source_bytes):
    media = wav_bytes(source_bytes / (48000 * 4), rate=48000, channels=2)
    assert len(media) > 25 * 1024 * 1024
    monkeypatch.setattr(audio, "fetch_media_bytes", lambda *a, **kw: media)

    assert audio.transcribe_media("https://example.test/full.wav", language="en") == "part 1"
    assert len(uploads) == 1
    data, language = uploads[0]
    assert language == "en"
    assert len(data) < 20 * 1024 * 1024
    assert wav_info(data)[:3] == (16000, 1, 2)
    assert wav_info(data)[3] == pytest.approx(len(media[44:]) / 12, abs=1)


def test_long_audio_chunks_remain_ordered_and_do_not_upload_tiny_tail(ffmpeg, uploads):
    # 600.01 seconds would leave a 10 ms final upload with naive fixed chunks.
    sample_count = 600 * 16000 + 160
    assert audio.transcribe_audio(wav_bytes(sample_count / 16000)) == "part 1\npart 2"
    assert len(uploads) == 2
    assert sum(wav_info(data)[3] for data, _ in uploads) == sample_count
    assert all(0.1 <= wav_info(data)[3] / 16000 <= 600 for data, _ in uploads)
    assert all(len(data) < 20 * 1024 * 1024 for data, _ in uploads)


@pytest.mark.parametrize("start,end,frames", [(-5, 0.5, 8000), (0.5, 10, 8000), (0.5, -1, 8000)])
def test_partial_overlaps_clamp_to_actual_audio_samples(ffmpeg, uploads, monkeypatch, start, end, frames):
    monkeypatch.setattr(audio, "fetch_media_bytes", lambda *a, **kw: wav_bytes())
    assert audio.transcribe_media("https://example.test/clip.wav", start, end) == "part 1"
    assert wav_info(uploads[0][0])[3] == frames


@pytest.mark.parametrize("start,end,diagnostic", [
    (360, 600, "outside the available audio duration of 1s"),
    (1, -1, "outside"),
    (0, 0, "end must be greater"),
    (0.5, 0.2, "end must be greater"),
    (0, -2, "end must be greater"),
    (0.95, -1, "shorter than 0.1s"),
    (float("nan"), -1, "finite numbers"),
    (0, float("inf"), "finite numbers"),
])
def test_invalid_ranges_never_call_transcriber(ffmpeg, uploads, monkeypatch, start, end, diagnostic):
    monkeypatch.setattr(audio, "fetch_media_bytes", lambda *a, **kw: wav_bytes())
    with pytest.raises(TranscriptionError, match=diagnostic):
        audio.transcribe_media("https://example.test/short.wav", start, end)
    assert uploads == []


def test_video_audio_extraction_and_out_of_range_clip(ffmpeg, uploads, monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    subprocess.run([
        ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
        "color=c=blue:s=32x32:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(video),
    ], check=True)
    monkeypatch.setattr(audio, "fetch_media_bytes", lambda *a, **kw: video.read_bytes())
    assert audio.transcribe_media("https://example.test/video.mp4") == "part 1"
    assert wav_info(uploads[0][0])[:3] == (16000, 1, 2)
    with pytest.raises(TranscriptionError, match="outside"):
        audio.transcribe_media("https://example.test/video.mp4", 360, 600)
    assert len(uploads) == 1


@pytest.mark.parametrize("data", [None, b"", b"not audio", wav_bytes(0)])
def test_missing_empty_and_invalid_audio_are_errors(ffmpeg, uploads, data):
    with pytest.raises(TranscriptionError):
        audio.transcribe_audio(data)
    assert uploads == []


def test_silent_success_is_empty_text(ffmpeg, monkeypatch):
    monkeypatch.setattr(audio, "_transcribe_api", lambda *a: "")
    assert audio.transcribe_audio(wav_bytes()) == ""


def test_second_chunk_error_does_not_return_partial_transcript(ffmpeg, monkeypatch):
    calls = []

    def transcribe(*args):
        calls.append(args)
        if len(calls) == 2:
            raise TranscriptionError("HTTP 413: provider upload limit")
        return "first chunk"

    monkeypatch.setattr(audio, "_transcribe_api", transcribe)
    with pytest.raises(TranscriptionError, match=r"Chunk 2/2 \(300.5-601s\).*HTTP 413.*No complete"):
        audio.transcribe_audio(wav_bytes(601))


class ProviderError(Exception):
    def __init__(self, status=None, code=None):
        super().__init__("sensitive provider body with sk-test-secret")
        self.status_code = status
        self.code = code


def fake_openai(monkeypatch, create):
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    client.closed = False
    client.close = lambda: setattr(client, "closed", True)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client))
    return client


@pytest.mark.parametrize("status,code,hint", [
    (400, "audio_too_short", "duration, format"),
    (413, "request_too_large", "upload size"),
    (401, "invalid_api_key", "OPENAI_API_KEY"),
    (403, "permission_denied", "transcription access"),
    (429, "rate_limit_exceeded", "quota/rate limit"),
    (500, "internal_error", "retry"),
    (None, None, "connectivity"),
])
def test_api_failures_preserve_actionable_diagnostics_without_secrets(monkeypatch, status, code, hint):
    def create(**kwargs):
        raise ProviderError(status, code)

    client = fake_openai(monkeypatch, create)
    with pytest.raises(TranscriptionError) as exc:
        audio._transcribe_api(wav_bytes())
    assert hint in str(exc.value)
    assert "ProviderError" in str(exc.value)
    if status:
        assert f"HTTP {status}" in str(exc.value)
        assert f"code={code}" in str(exc.value)
    assert "sk-test-secret" not in str(exc.value)
    assert client.closed


def test_api_upload_has_wav_filename_and_language(monkeypatch):
    calls = []

    def create(**kwargs):
        calls.append((kwargs["model"], kwargs["language"], kwargs["file"].name, kwargs["file"].read()))
        return SimpleNamespace(text="  hello  ")

    fake_openai(monkeypatch, create)
    data = wav_bytes()
    assert audio._transcribe_api(data, "en") == "hello"
    assert calls == [("whisper-1", "en", "audio.wav", data)]


def test_api_client_configuration_failure_has_setup_advice(monkeypatch):
    def create_client():
        raise RuntimeError("private configuration")

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=create_client))
    with pytest.raises(TranscriptionError, match="OPENAI_API_KEY.*OPENAI_BASE_URL.*use_api=False") as exc:
        audio._transcribe_api(wav_bytes())
    assert "private configuration" not in str(exc.value)


def test_oversized_prepared_chunk_cannot_be_uploaded(monkeypatch):
    fake_openai(monkeypatch, lambda **kw: pytest.fail("must not upload"))
    with pytest.raises(TranscriptionError, match="20 MiB"):
        audio._transcribe_api(b"x" * (20 * 1024 * 1024 + 1))


def test_local_model_is_explicit_configurable_and_reused(monkeypatch):
    names = []
    model = SimpleNamespace(transcribe=lambda *a, **kw: {"text": "local text"})
    monkeypatch.setitem(sys.modules, "whisper", SimpleNamespace(load_model=lambda name: names.append(name) or model))
    monkeypatch.setattr(audio, "_whisper_model", None)
    monkeypatch.setattr(audio, "_whisper_model_name", None)
    monkeypatch.delenv("WEBARENA_PRO_WHISPER_MODEL", raising=False)
    assert audio._transcribe_local(wav_bytes()) == "local text"
    assert audio._transcribe_local(wav_bytes()) == "local text"
    monkeypatch.setenv("WEBARENA_PRO_WHISPER_MODEL", "tiny")
    assert audio._transcribe_local(wav_bytes()) == "local text"
    assert names == ["base", "tiny"]


def test_local_failure_is_not_silence(monkeypatch):
    def fail():
        raise ImportError("not installed")

    monkeypatch.setattr(audio, "_get_whisper_model", fail)
    with pytest.raises(TranscriptionError, match=r"media\[local\].*WEBARENA_PRO_WHISPER_MODEL"):
        audio._transcribe_local(wav_bytes())
