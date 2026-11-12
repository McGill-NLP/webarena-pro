"""Video selection, resource bounds, and authenticated source cache regressions."""

import base64
import json
from pathlib import Path
import shutil
import struct
import subprocess
from types import SimpleNamespace

import pytest

from webarena_pro_media import cache, clips, watch


@pytest.fixture
def ffmpeg(monkeypatch):
    executable, probe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not executable or not probe:
        pytest.skip("real video tests require ffmpeg and ffprobe on PATH")
    monkeypatch.setattr(watch, "ffmpeg_binary", lambda: executable)
    monkeypatch.setattr(watch, "ffprobe_binary", lambda: probe)
    monkeypatch.setattr(clips, "ffmpeg_binary", lambda: executable)
    monkeypatch.setattr(clips, "ffprobe_binary", lambda: probe)
    return executable, probe


def make_video(ffmpeg, path, *, audio=True):
    command = [
        ffmpeg, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x48:r=10:d=4",
    ]
    if audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4"]
    command += ["-c:v", "mpeg4"]
    if audio:
        command += ["-c:a", "aac", "-shortest"]
    subprocess.run(command + [str(path)], check=True)
    return path


def use_source(monkeypatch, source):
    source_object = cache.MediaSource(source, "test-source-sha256", source.stat().st_size, {}, False)
    monkeypatch.setattr(watch, "media_source_cache", lambda page: SimpleNamespace(
        get=lambda *a, **kw: source_object,
        _prune=lambda **kw: None,
    ))


def test_validated_video_source_bypasses_downloaders(ffmpeg, tmp_path, monkeypatch):
    from webarena_pro_media import video

    source = make_video(ffmpeg[0], tmp_path / "source.mp4")

    def forbidden(*args, **kwargs):
        raise AssertionError("Adapter-supplied media must not be downloaded again")

    monkeypatch.setattr(watch, "media_source_cache", forbidden)
    monkeypatch.setattr(video, "fetch_media_bytes", forbidden)
    frames = video.extract_video_frames("https://metadata-only.test/video", 2, 0, 1,
                                         source_bytes=source.read_bytes())
    assert len(frames) == 2 and all(frame["image_b64"] for frame in frames)
    result = watch.extract_watch_clip("https://metadata-only.test/video", 0, 1, mode="detail",
                                      source=cache.MediaSource(source, "verified", source.stat().st_size, {}))
    assert result["video_b64"] and result["source_version"] == "verified"


@pytest.mark.parametrize("audio", [False, True])
def test_detail_is_a_real_mp4_with_requested_audio_and_source_timing(ffmpeg, tmp_path, monkeypatch, audio):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4", audio=audio)
    use_source(monkeypatch, source)
    result = watch.extract_watch_clip("https://example.test/video", 1, 3, mode="detail", include_audio=True, fps=2)
    output = tmp_path / "result.mp4"
    output.write_bytes(base64.b64decode(result["video_b64"]))
    decoded = json.loads(subprocess.check_output([
        ffmpeg[1], "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output),
    ]))
    assert result["representation"] == "video"
    assert (result["start"], result["end"], result["duration"]) == (1, 3, 2)
    assert result["frames"] == []
    assert result["audio_included"] == audio
    assert any(s["codec_type"] == "audio" for s in decoded["streams"]) == audio
    video = next(s for s in decoded["streams"] if s["codec_type"] == "video")
    assert video["avg_frame_rate"] == "2/1"
    assert float(decoded["format"]["duration"]) == pytest.approx(2, abs=0.1)
    assert "source t=1s" in result["sampling"]
    assert result["estimated_input_tokens"] <= result["media_token_budget"]


def test_detail_drops_audio_by_default_and_clamps_eof_explicitly(ffmpeg, tmp_path, monkeypatch):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4")
    use_source(monkeypatch, source)
    result = watch.extract_watch_clip("https://example.test/video", 2, 8, mode="detail")
    assert result["audio_included"] is False
    assert result["source_has_audio"] is True
    assert result["clamped_to_eof"] is True
    assert (result["requested_end"], result["end"]) == (8, 4)
    with pytest.raises(watch.MediaClipError, match="outside"):
        watch.extract_watch_clip("https://example.test/video", 5, 6, mode="detail")


def test_late_audio_keeps_its_offset_after_input_seek(ffmpeg, tmp_path, monkeypatch):
    source = tmp_path / "delayed.mp4"
    subprocess.run([
        ffmpeg[0], "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32:d=4",
        "-itsoffset", "2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac", str(source),
    ], check=True)
    use_source(monkeypatch, source)
    result = watch.extract_watch_clip("https://example.test/delayed", 1, 3, mode="detail", include_audio=True)
    output = tmp_path / "out.mp4"
    output.write_bytes(base64.b64decode(result["video_b64"]))
    samples = subprocess.check_output([ffmpeg[0], "-v", "error", "-i", str(output), "-map", "0:a:0", "-ar", "8000", "-ac", "1", "-f", "s16le", "-"])
    values = struct.unpack(f"<{len(samples) // 2}h", samples)
    assert max(abs(value) for value in values[:6000]) <= 2
    assert max(abs(value) for value in values[10000:14000]) > 100
    assert (result["start"], result["end"]) == (1, 3)


def test_late_hour_interval_seeks_before_decode(ffmpeg, tmp_path, monkeypatch):
    source = tmp_path / "hour.mp4"
    subprocess.run([
        ffmpeg[0], "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=1:d=3600",
        "-c:v", "libx264", "-preset", "ultrafast", str(source),
    ], check=True, timeout=30)
    use_source(monkeypatch, source)
    run = watch._run
    commands = []

    def capture(command, **kwargs):
        commands.append(command)
        return run(command, **kwargs)

    monkeypatch.setattr(watch, "_run", capture)
    result = watch.extract_watch_clip("https://example.test/hour", 3500, 3502, mode="detail")
    decode = next(command for command in commands if "libx264" in command)
    assert decode.index("-ss") < decode.index("-i")
    assert (result["start"], result["end"], result["source_duration"]) == (3500, 3502, 3600)
    assert result["encoded_duration"] == pytest.approx(2)


def test_short_native_intervals_error_and_encoded_tail_is_disclosed(ffmpeg, tmp_path, monkeypatch):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4")
    use_source(monkeypatch, source)
    with pytest.raises(watch.MediaClipError, match="at least 1 seconds"):
        watch.extract_watch_clip("https://example.test/video", 0, 0.1, mode="detail")
    result = watch.extract_watch_clip("https://example.test/video", 0, 1.7, mode="detail")
    assert result["end"] == 1.7
    assert result["encoded_duration"] == pytest.approx(2)
    assert "Evidence ends at source t=1.7s" in result["sampling"]


def test_overview_jpegs_have_actual_source_timestamps(ffmpeg, tmp_path, monkeypatch):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4")
    use_source(monkeypatch, source)
    result = watch.extract_watch_clip("https://example.test/video", 1, 3)
    assert result["representation"] == "sampled_frames"
    assert [frame["timestamp"] for frame in result["frames"]] == [2]
    assert base64.b64decode(result["frames"][0]["image_b64"]).startswith(b"\xff\xd8")
    assert result["audio_included"] is False
    assert "video_b64" not in result
    assert "intervening" in result["sampling"]


def test_one_hour_overview_is_bounded_and_native_full_requires_budget(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    use_source(monkeypatch, source)
    monkeypatch.setattr(watch, "_probe", lambda path: {"duration": 3600, "has_audio": True})

    def extract_frame(command, **kwargs):
        Path(command[-1]).write_bytes(b"\xff\xd8image\xff\xd9")

    monkeypatch.setattr(watch, "_run", extract_frame)
    result = watch.extract_watch_clip("https://example.test/hour")
    assert len(result["frames"]) == 120
    assert result["frames"][0]["timestamp"] == 15
    assert result["frames"][-1]["timestamp"] == 3585
    assert result["source_duration"] == 3600
    assert result["fps"] == pytest.approx(1 / 30)
    lower_budget = watch.extract_watch_clip("https://example.test/hour", max_input_tokens=4096)
    assert len(lower_budget["frames"]) == 3
    with pytest.raises(watch.MediaClipError, match="lower fps, or request an overview"):
        watch.extract_watch_clip("https://example.test/hour", mode="full")
    with pytest.raises(watch.MediaClipError, match="allowance"):
        watch.extract_watch_clip("https://example.test/hour", 0, 120, mode="detail", max_input_tokens=4096)


@pytest.mark.parametrize("partial", [b"", b"\xff\xd8partial"])
def test_overview_retry_redecodes_after_interrupted_frame_write(tmp_path, monkeypatch, partial):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    use_source(monkeypatch, source)
    monkeypatch.setattr(watch, "_probe", lambda path: {"duration": 30, "has_audio": False})
    calls = []
    complete = b"\xff\xd8complete\xff\xd9"

    def extract_frame(command, **kwargs):
        destination = Path(command[-1])
        calls.append(destination)
        destination.write_bytes(partial if len(calls) == 1 else complete)
        if len(calls) == 1:
            raise watch.MediaClipError("Video processing timed out")

    monkeypatch.setattr(watch, "_run", extract_frame)
    with pytest.raises(watch.MediaClipError, match="timed out"):
        watch.extract_watch_clip("https://example.test/video")
    assert not list(tmp_path.glob("*/*.jpg"))
    result = watch.extract_watch_clip("https://example.test/video")
    assert len(calls) == 2
    assert base64.b64decode(result["frames"][0]["image_b64"]) == complete
    assert not list(tmp_path.glob("*/*.part.jpg"))
    assert len(list(tmp_path.glob("*/0.jpg"))) == 1


def test_overview_redecodes_corrupt_existing_cache_entry(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    use_source(monkeypatch, source)
    monkeypatch.setattr(watch, "_probe", lambda path: {"duration": 30, "has_audio": False})
    calls = []

    def extract_frame(command, **kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"\xff\xd8complete\xff\xd9")

    monkeypatch.setattr(watch, "_run", extract_frame)
    watch.extract_watch_clip("https://example.test/video")
    cached = next(tmp_path.glob("*/0.jpg"))
    cached.write_bytes(b"\xff\xd8interrupted")
    result = watch.extract_watch_clip("https://example.test/video")
    assert len(calls) == 2
    assert base64.b64decode(result["frames"][0]["image_b64"]).endswith(b"\xff\xd9")


@pytest.mark.parametrize("kwargs", [
    {"mode": "unknown"}, {"include_audio": True}, {"include_audio": "yes"},
    {"start_seconds": -1}, {"end_seconds": -1}, {"start_seconds": float("nan")},
    {"end_seconds": float("inf")}, {"fps": 0}, {"fps": float("nan")},
    {"max_frames": 121}, {"max_frames": 1.5}, {"max_input_tokens": 1},
])
def test_invalid_watch_request_fails_before_download(monkeypatch, kwargs):
    monkeypatch.setattr(watch, "media_source_cache", lambda *a: pytest.fail("downloaded invalid request"))
    with pytest.raises(watch.MediaClipError):
        watch.extract_watch_clip("https://example.test/video", **kwargs)


def test_output_limit_and_missing_video_fail_explicitly(ffmpeg, tmp_path, monkeypatch):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4")
    use_source(monkeypatch, source)
    monkeypatch.setattr(watch, "MAX_VIDEO_ATTACHMENT_BYTES", 16)
    with pytest.raises(watch.MediaClipError, match="8 MiB"):
        watch.extract_watch_clip("https://example.test/video", mode="detail")
    audio = tmp_path / "audio.wav"
    subprocess.run([ffmpeg[0], "-v", "error", "-f", "lavfi", "-i", "sine=duration=1", str(audio)], check=True)
    use_source(monkeypatch, audio)
    with pytest.raises(watch.MediaClipError, match="listen"):
        watch.extract_watch_clip("https://example.test/audio")


def test_audio_only_extraction_of_video_never_extracts_frames(ffmpeg, tmp_path, monkeypatch):
    source = make_video(ffmpeg[0], tmp_path / "source.mp4")
    monkeypatch.setattr(clips, "fetch_media_bytes", lambda *a, **kw: source.read_bytes())
    result = clips.extract_media_clip("https://example.test/video", 0, 1, n_frames=0)
    assert result["frames"] == []
    assert base64.b64decode(result["audio_b64"]).startswith(b"RIFF")


class Response:
    def __init__(self, data=b"media", *, status=200, headers=None):
        self.data, self.status_code = data, status
        self.ok = status < 400
        self.headers = headers or {"content-type": "video/mp4", "etag": '"v1"'}
        self.closed = False

    def iter_content(self, **kwargs):
        yield self.data[:2]
        yield self.data[2:]

    def close(self):
        self.closed = True


def test_source_cache_revalidates_http_and_reuses_then_invalidates(tmp_path, monkeypatch):
    import requests

    responses = [Response(), Response(status=304), Response(b"new-media", headers={"etag": '"v2"'})]
    calls = []

    def get(url, **kwargs):
        calls.append(kwargs)
        return responses[len(calls) - 1]

    monkeypatch.setattr(requests, "get", get)
    source_cache = cache.MediaSourceCache()
    first = source_cache.get("https://example.test/media")
    second = source_cache.get("https://example.test/media")
    third = source_cache.get("https://example.test/media")
    assert first.path == second.path
    assert second.cached is True
    assert first.version != third.version
    assert third.path.read_bytes() == b"new-media"
    assert calls[1]["headers"] == {"If-None-Match": '"v1"'}
    assert all(response.closed for response in responses)
    source_cache.close()
    assert not first.path.exists()


@pytest.mark.parametrize("headers", [{"content-length": "12"}, {}])
def test_streaming_cache_stops_oversize_source_and_cleans_partial_file(monkeypatch, headers):
    import requests

    response = Response(b"oversize-media", headers=headers)
    monkeypatch.setattr(requests, "get", lambda *a, **kw: response)
    source_cache = cache.MediaSourceCache()
    with pytest.raises(cache.MediaFetchError, match="download limit"):
        source_cache.get("https://example.test/media", max_bytes=10)
    assert response.closed
    assert not list(source_cache.root.iterdir())
    source_cache.close()


def test_context_and_cookie_changes_isolate_cached_media(monkeypatch):
    import requests

    class Context:
        value = "first-user"

        def cookies(self, urls):
            return [{"name": "session", "value": self.value, "domain": "example.test", "path": "/"}]

    requests_seen = []

    def get(url, **kwargs):
        requests_seen.append(kwargs)
        return Response()

    monkeypatch.setattr(requests, "get", get)
    context = Context()
    page = SimpleNamespace(context=context, url="https://example.test/page")
    first_cache = cache.media_source_cache(page)
    first = first_cache.get("https://example.test/media", page=page)
    context.value = "second-user"
    second = first_cache.get("https://example.test/media", page=page)
    other_page = SimpleNamespace(context=Context(), url=page.url)
    other_cache = cache.media_source_cache(other_page)
    assert first.path != second.path
    assert first_cache is not other_cache
    assert "If-None-Match" not in requests_seen[1]["headers"]
    assert requests_seen[1]["cookies"].get("session") == "second-user"
    cache.clear_media_cache(page)
    assert not first.path.exists()
    cache.clear_media_cache()


def test_unvalidated_sources_are_downloaded_again(monkeypatch):
    import requests

    calls = []

    def get(*args, **kwargs):
        calls.append(True)
        return Response(b"old" if len(calls) == 1 else b"new", headers={"content-type": "video/mp4"})

    monkeypatch.setattr(requests, "get", get)
    source_cache = cache.MediaSourceCache()
    first = source_cache.get("https://example.test/media")
    second = source_cache.get("https://example.test/media")
    assert len(calls) == 2
    assert first.version != second.version
    source_cache.close()
