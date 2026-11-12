import base64
from pathlib import Path
from types import SimpleNamespace
import sys

from webarena_pro_media import audio as audio_module
from webarena_pro_media import fetch as fetch_module
from webarena_pro_media import video as video_module


class AudioPage:
    def __init__(self, audio_bytes: bytes):
        self.audio_bytes = audio_bytes
        self.calls = []

    def evaluate(self, script, *args):
        self.calls.append((script, args))
        if args:
            return {
                "audio_base64": base64.b64encode(self.audio_bytes).decode(),
                "mime_type": "audio/webm;codecs=opus",
            }
        return True


def test_extract_audio_works_with_playwright_compatible_page():
    page = AudioPage(b"captured audio")

    assert audio_module.extract_audio(page, duration=1.25) == b"captured audio"
    assert len(page.calls) == 2
    assert page.calls[1][1] == (1250,)


def test_fetch_media_bytes_uses_playwright_context_request(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "requests",
        SimpleNamespace(get=lambda *args, **kwargs: (_ for _ in ()).throw(OSError())),
    )

    class Response:
        ok = True
        status = 200

        @staticmethod
        def body():
            return b"authenticated media"

    class Request:
        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    request = Request()
    page = SimpleNamespace(context=SimpleNamespace(request=request))

    assert (
        fetch_module.fetch_media_bytes(
            "https://example.test/protected.mp4",
            page=page,
            timeout=7,
        )
        == b"authenticated media"
    )
    assert request.calls == [("https://example.test/protected.mp4", {"timeout": 7000})]


def test_transcribe_media_delegates_full_file_to_preparation(monkeypatch):
    media_bytes = b"RIFF" + b"\x00" * 20
    monkeypatch.setattr(
        audio_module,
        "fetch_media_bytes",
        lambda url, **kwargs: media_bytes,
    )
    calls = []
    monkeypatch.setattr(
        audio_module,
        "_transcribe_prepared",
        lambda data, language, use_api, start, end: (
            calls.append((data, language, use_api, start, end)) or "hello world"
        ),
    )

    assert (
        audio_module.transcribe_media(
            "https://example.test/audio.wav",
            language="en",
            use_api=False,
        )
        == "hello world"
    )
    assert calls == [(media_bytes, "en", False, 0, -1)]


def test_extract_video_frames_returns_evenly_spaced_images(monkeypatch):
    monkeypatch.setattr(
        video_module,
        "fetch_media_bytes",
        lambda url, **kwargs: b"video" * 20,
    )
    monkeypatch.setattr(video_module, "probe_video_duration", lambda path: 12.0)
    timestamps = []

    def fake_extract(source, timestamp, destination, width=1280):
        timestamps.append((timestamp, width))
        Path(destination).write_bytes(f"frame-{timestamp}".encode())
        return True

    monkeypatch.setattr(video_module, "extract_video_frame", fake_extract)

    frames = video_module.extract_video_frames(
        "https://example.test/video.mp4",
        n_frames=3,
        start_seconds=2,
        end_seconds=10,
        width=640,
    )

    assert timestamps == [(4.0, 640), (6.0, 640), (8.0, 640)]
    assert [frame["timestamp"] for frame in frames] == [4.0, 6.0, 8.0]
    assert base64.b64decode(frames[0]["image_b64"]) == b"frame-4.0"


def test_media_modules_do_not_import_browsergym():
    for module in (audio_module, fetch_module, video_module):
        assert "browsergym" not in Path(module.__file__).read_text().lower()
