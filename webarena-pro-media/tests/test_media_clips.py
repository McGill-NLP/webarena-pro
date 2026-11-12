"""Real clip decoding and failure bounds; no model API calls."""

import base64
import io
import shutil
import struct
import subprocess
from types import SimpleNamespace
import wave

import pytest

from webarena_pro_media import clips, fetch


@pytest.fixture
def ffmpeg(monkeypatch):
    executable, probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not executable or not probe:
        pytest.skip("real media tests require ffmpeg and ffprobe on PATH")
    monkeypatch.setattr(clips, "ffmpeg_binary", lambda: executable)
    monkeypatch.setattr(clips, "ffprobe_binary", lambda: probe)
    return executable


def source_audio():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        for amplitude in (1000, 2000, 3000):
            audio.writeframes(struct.pack("<hh", amplitude, -amplitude) * 24000)
    return buffer.getvalue()


def test_validated_audio_bytes_bypass_network(ffmpeg, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Adapter-supplied media must not be downloaded again")

    monkeypatch.setattr(clips, "fetch_media_bytes", forbidden)
    result = clips.extract_media_clip("https://metadata-only.test/audio", 0, 1,
                                      n_frames=0, source_bytes=source_audio())
    assert result["duration"] == 1
    assert base64.b64decode(result["audio_b64"]).startswith(b"RIFF")


def test_selected_audio_samples_and_actual_eof_timing(ffmpeg, monkeypatch):
    monkeypatch.setattr(clips, "fetch_media_bytes", lambda *a, **kw: source_audio())
    clip = clips.extract_media_clip("https://example.test/music.wav", 1, 2)
    with wave.open(io.BytesIO(base64.b64decode(clip["audio_b64"]))) as audio:
        assert (audio.getframerate(), audio.getnchannels(), audio.getnframes()) == (
            24000,
            2,
            24000,
        )
        assert audio.readframes(24000) == struct.pack("<hh", 2000, -2000) * 24000
    assert (clip["start"], clip["end"], clip["duration"], clip["format"]) == (
        1,
        2,
        1,
        "wav",
    )
    assert clip["frames"] == []
    clamped = clips.extract_media_clip("https://example.test/music.wav", 2, 5)
    assert (clamped["start"], clamped["end"], clamped["requested_end"]) == (2, 3, 5)


def test_video_delivers_audio_and_synchronized_jpegs_from_one_fetch(
    ffmpeg, tmp_path, monkeypatch
):
    source = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=64x48:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    calls = []
    page = object()

    def download(url, **kwargs):
        calls.append((url, kwargs))
        return source.read_bytes()

    monkeypatch.setattr(clips, "fetch_media_bytes", download)
    clip = clips.extract_media_clip(
        "https://example.test/video.mp4", 1, 2, n_frames=3, page=page
    )
    assert [f["timestamp"] for f in clip["frames"]] == pytest.approx([1.25, 1.5, 1.75])
    assert all(
        base64.b64decode(f["image_b64"]).startswith(b"\xff\xd8") for f in clip["frames"]
    )
    assert base64.b64decode(clip["audio_b64"]).startswith(b"RIFF")
    assert calls == [
        (
            "https://example.test/video.mp4",
            {"page": page, "max_bytes": clips.MAX_SOURCE_BYTES},
        )
    ]


@pytest.mark.parametrize(
    "start,end,n_frames",
    [
        (-1, 5, 3),
        (0, -1, 3),
        (0, 61, 3),
        (2, 1, 3),
        (0, 0.01, 3),
        (float("nan"), 5, 3),
        (0, float("inf"), 3),
        ("bad", 5, 3),
        (0, 1, 6),
        (0, 1, -1),
        (0, 1, 1.5),
    ],
)
def test_invalid_requests_fail_before_download(monkeypatch, start, end, n_frames):
    monkeypatch.setattr(
        clips,
        "fetch_media_bytes",
        lambda *a, **kw: pytest.fail("downloaded invalid range"),
    )
    with pytest.raises(clips.MediaClipError):
        clips.extract_media_clip(
            "https://example.test/a", start, end, n_frames=n_frames
        )


def test_missing_corrupt_out_of_range_and_oversize_media(ffmpeg, monkeypatch):
    for data in (None, b"", b"not a media file"):
        monkeypatch.setattr(clips, "fetch_media_bytes", lambda *a, **kw: data)
        with pytest.raises(clips.MediaClipError):
            clips.extract_media_clip("https://example.test/a")
    monkeypatch.setattr(clips, "fetch_media_bytes", lambda *a, **kw: source_audio())
    with pytest.raises(clips.MediaClipError, match="less than 0.1"):
        clips.extract_media_clip("https://example.test/a", 4, 5)
    monkeypatch.setattr(clips, "MAX_SOURCE_BYTES", 10)
    with pytest.raises(clips.MediaClipError, match="100 MiB"):
        clips.extract_media_clip("https://example.test/a")


def test_silent_video_and_attachment_size_failure_are_explicit(
    ffmpeg, tmp_path, monkeypatch
):
    source = tmp_path / "silent.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=32x32:d=1",
            "-c:v",
            "mpeg4",
            str(source),
        ],
        check=True,
    )
    monkeypatch.setattr(
        clips, "fetch_media_bytes", lambda *a, **kw: source.read_bytes()
    )
    with pytest.raises(clips.MediaClipError, match="no audio track"):
        clips.extract_media_clip("https://example.test/a")
    monkeypatch.setattr(clips, "fetch_media_bytes", lambda *a, **kw: source_audio())
    monkeypatch.setattr(clips, "MAX_ATTACHMENT_BYTES", 10)
    with pytest.raises(clips.MediaClipError, match="attachments exceed"):
        clips.extract_media_clip("https://example.test/a")


@pytest.mark.parametrize(
    "failure,match",
    [
        (FileNotFoundError(), "required"),
        (subprocess.TimeoutExpired("ffmpeg", 60), "timeout"),
    ],
)
def test_missing_decoder_and_timeout(monkeypatch, failure, match):
    def run(*a, **kw):
        raise failure

    monkeypatch.setattr(clips.subprocess, "run", run)
    with pytest.raises(clips.MediaClipError, match=match):
        clips._run(["ffmpeg"])


@pytest.mark.parametrize("headers", [{"content-length": "20"}, {}])
def test_bounded_http_download_stops_and_closes(monkeypatch, headers):
    import requests

    closed = []
    response = SimpleNamespace(
        ok=True,
        headers=headers,
        iter_content=lambda **kw: iter([b"12345", b"678901"]),
        close=lambda: closed.append(True),
    )
    monkeypatch.setattr(requests, "get", lambda *a, **kw: response)
    page = SimpleNamespace(evaluate=lambda *a: pytest.fail("retried oversized source"))
    with pytest.raises(fetch.MediaFetchError, match="limit"):
        fetch.fetch_media_bytes("https://example.test/a", max_bytes=10, page=page)
    assert closed == [True]


def test_bounded_authenticated_and_browser_fetch(monkeypatch):
    import requests

    monkeypatch.setattr(
        requests, "get", lambda *a, **kw: (_ for _ in ()).throw(OSError())
    )
    disposed = []
    response = SimpleNamespace(
        ok=True,
        headers={},
        body=lambda: b"12345",
        dispose=lambda: disposed.append(True),
    )
    page = SimpleNamespace(
        context=SimpleNamespace(request=SimpleNamespace(get=lambda *a, **kw: response))
    )
    assert (
        fetch.fetch_media_bytes("https://example.test/a", page=page, max_bytes=5)
        == b"12345"
    )
    with pytest.raises(fetch.MediaFetchError):
        fetch.fetch_media_bytes("https://example.test/a", page=page, max_bytes=4)
    assert disposed == [True, True]
    page = SimpleNamespace(
        evaluate=lambda *a: {"base64": base64.b64encode(b"blob").decode()}
    )
    assert (
        fetch.fetch_media_bytes("blob:https://example.test/a", page=page, max_bytes=5)
        == b"blob"
    )
    page.evaluate = lambda *a: {"tooLarge": True}
    with pytest.raises(fetch.MediaFetchError):
        fetch.fetch_media_bytes("blob:https://example.test/a", page=page, max_bytes=5)


def test_late_audio_keeps_video_timeline_and_decimal_minimum(
    ffmpeg, tmp_path, monkeypatch
):
    source = tmp_path / "delayed.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=3",
            "-itsoffset",
            "1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )
    monkeypatch.setattr(
        clips, "fetch_media_bytes", lambda *a, **kw: source.read_bytes()
    )
    clip = clips.extract_media_clip(
        "https://example.test/delayed.mp4", 0.2, 0.3, n_frames=1
    )
    assert clip["duration"] == pytest.approx(0.1)
    assert clip["frames"][0]["timestamp"] == pytest.approx(0.25)
    with wave.open(io.BytesIO(base64.b64decode(clip["audio_b64"]))) as audio:
        samples = audio.readframes(audio.getnframes())
    assert samples and set(samples) == {0}
