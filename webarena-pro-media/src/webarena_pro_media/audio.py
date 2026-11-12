"""Reusable audio capture and transcription helpers.

Captures audio from <audio> and <video> elements in the browser using
JavaScript's MediaRecorder API via a synchronous Playwright-compatible page.

Provides:

- Raw audio bytes (for omni models that accept audio input)
- Whisper transcription (for LLM agents)
- URL-based transcription, including authenticated browser fetches

Example::

    # Capture audio from the active page
    audio_bytes = extract_audio(page, duration=5.0)

    # Transcribe it
    transcript = transcribe_audio(audio_bytes)

    transcript = transcribe_media(
        "http://host/audio.mp3", start_seconds=30, end_seconds=60, page=page
    )
"""

from __future__ import annotations

import base64
import io
import logging
import math
import os
import re
from pathlib import Path
import subprocess
import tempfile
import wave
from typing import Any

from .binaries import ffmpeg_binary
from .fetch import fetch_media_bytes

logger = logging.getLogger(__name__)

# Whisper model is lazy-loaded
_whisper_model = None
_whisper_model_name = None

# 10 minutes of 16 kHz mono PCM16 is 19.2 MB, safely below the reported
# 25 MiB proxy limit, including WAV headers and multipart overhead.
_SAMPLE_RATE = 16_000
_CHUNK_SECONDS = 600
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_MIN_AUDIO_SECONDS = 0.1


class TranscriptionError(RuntimeError):
    """Media preparation or transcription failed (distinct from no speech)."""


def _get_whisper_model():
    """Lazy-load the Whisper model."""
    global _whisper_model, _whisper_model_name
    model_name = os.environ.get("WEBARENA_PRO_WHISPER_MODEL", "base")
    if _whisper_model is None or _whisper_model_name != model_name:
        try:
            import whisper

            _whisper_model = whisper.load_model(model_name)
            _whisper_model_name = model_name
            logger.info("Loaded Whisper model: %s", model_name)
        except ImportError as error:
            raise ImportError(
                "openai-whisper is required for audio transcription. "
                "Install webarena-pro-media[local]."
            ) from error
    return _whisper_model


# ---------------------------------------------------------------------------
# JavaScript for in-browser audio capture
# ---------------------------------------------------------------------------

AUDIO_CAPTURE_INSTALL_JS = """
() => {
    if (window.__webarena_pro_audio_installed) return true;

    window.__webarena_pro_audio_capture = {
        recorder: null,
        chunks: [],
        resolve: null,
        recording: false,
    };

    /**
     * Find the first <audio> or <video> element that has a media source.
     */
    window.__webarena_pro_find_media_element = function() {
        const candidates = [
            ...document.querySelectorAll('video'),
            ...document.querySelectorAll('audio'),
        ];
        for (const el of candidates) {
            // Skip muted or silent elements
            if (el.muted && !el.src && !el.srcObject) continue;
            if (el.readyState >= 2) return el;  // HAVE_CURRENT_DATA or better
        }
        // Fallback: return first media element found
        return candidates[0] || null;
    };

    window.__webarena_pro_audio_installed = true;
    return true;
}
"""

AUDIO_CAPTURE_FULL_JS = """
(durationMs) => {
    return new Promise(async (resolve) => {
        const state = window.__webarena_pro_audio_capture;
        if (state.recording) {
            resolve({error: 'Already recording'});
            return;
        }

        const el = window.__webarena_pro_find_media_element();
        if (!el) {
            resolve({error: 'No media element found on page'});
            return;
        }

        let stream;
        try {
            stream = el.captureStream();
        } catch (e) {
            resolve({error: 'captureStream failed: ' + e.message});
            return;
        }

        const audioTracks = stream.getAudioTracks();
        if (audioTracks.length === 0) {
            resolve({error: 'No audio tracks in media stream'});
            return;
        }

        const audioStream = new MediaStream(audioTracks);
        const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
            ? 'audio/webm;codecs=opus'
            : MediaRecorder.isTypeSupported('audio/webm')
                ? 'audio/webm'
                : '';

        const recorder = new MediaRecorder(audioStream, mimeType ? {mimeType} : {});
        const chunks = [];
        state.recording = true;

        recorder.ondataavailable = (e) => {
            if (e.data.size > 0) chunks.push(e.data);
        };

        recorder.onstop = () => {
            state.recording = false;
            const blob = new Blob(chunks, {type: recorder.mimeType});
            const reader = new FileReader();
            reader.onloadend = () => {
                const base64 = reader.result.split(',')[1];
                resolve({
                    audio_base64: base64,
                    mime_type: recorder.mimeType,
                    duration_ms: durationMs,
                });
            };
            reader.readAsDataURL(blob);
        };

        // Ensure media is playing
        if (el.paused) {
            el.play().catch(() => {});
        }

        recorder.start();
        setTimeout(() => {
            if (recorder.state === 'recording') {
                recorder.stop();
            }
        }, durationMs);
    });
}
"""


# ---------------------------------------------------------------------------
# Python API
# ---------------------------------------------------------------------------


def install_audio_capture(page: Any) -> None:
    """
    Install the audio capture scripts into the page.
    Safe to call multiple times (idempotent).
    """
    try:
        page.evaluate(AUDIO_CAPTURE_INSTALL_JS)
    except Exception as e:
        logger.warning(f"Failed to install audio capture scripts: {e}")


def extract_audio(page: Any, duration: float = 5.0) -> bytes | None:
    """
    Capture audio from the active page's media elements.

    Uses JavaScript MediaRecorder API to capture audio from <audio>/<video>
    elements. No system dependencies required.

    Args:
        page: Playwright page object.
        duration: Duration to record in seconds.

    Returns:
        Audio bytes (webm/opus format), or None if no audio is available.
    """
    install_audio_capture(page)

    try:
        result = page.evaluate(
            AUDIO_CAPTURE_FULL_JS,
            int(duration * 1000),
        )
    except Exception as e:
        logger.warning(f"Audio capture failed: {e}")
        return None

    if isinstance(result, dict) and "error" in result:
        logger.debug(f"Audio capture: {result['error']}")
        return None

    if isinstance(result, dict) and "audio_base64" in result:
        audio_bytes = base64.b64decode(result["audio_base64"])
        if len(audio_bytes) > 0:
            logger.info(
                f"Captured {len(audio_bytes)} bytes of audio "
                f"({result.get('mime_type', 'unknown')}, {duration}s)"
            )
            return audio_bytes

    return None


def transcribe_audio(
    audio_bytes: bytes | None,
    language: str | None = None,
    use_api: bool = True,
) -> str:
    """Transcribe decoded audio in chronological, bounded chunks.

    Returns text (empty only when the backend reports no speech). Raises
    :class:`TranscriptionError` for empty/invalid audio or backend failures.
    ``use_api=False`` explicitly selects local Whisper; there is no automatic
    fallback from the API to a local model.
    """
    return _transcribe_prepared(audio_bytes, language, use_api, 0, -1)


def _validate_range(start_seconds: float, end_seconds: float) -> tuple[float, float]:
    try:
        start, end = float(start_seconds), float(end_seconds)
    except (TypeError, ValueError, OverflowError) as error:
        raise TranscriptionError("Audio range must contain finite numbers.") from error
    if not math.isfinite(start) or not math.isfinite(end):
        raise TranscriptionError("Audio range must contain finite numbers.")
    start = max(0.0, start)
    if end != -1 and end <= start:
        raise TranscriptionError(
            "Audio range end must be greater than start, or -1 for the end of the media."
        )
    return start, end


def _transcribe_prepared(
    audio_bytes: bytes | None,
    language: str | None,
    use_api: bool,
    start_seconds: float,
    end_seconds: float,
) -> str:
    start, end = _validate_range(start_seconds, end_seconds)
    if not audio_bytes:
        raise TranscriptionError("No audio data was provided for transcription.")

    with tempfile.TemporaryDirectory(prefix="webarena-pro-audio-") as temp_dir:
        source = Path(temp_dir) / "source.media"
        normalized = Path(temp_dir) / "audio.wav"
        source.write_bytes(audio_bytes)
        # Decode first so duration/ranges refer to actual audio samples, rather
        # than potentially inaccurate video-container duration metadata.
        command = [
            ffmpeg_binary(), "-nostdin", "-y", "-loglevel", "error", "-i", str(source),
            "-map", "0:a:0", "-vn", "-ar", str(_SAMPLE_RATE), "-ac", "1",
            "-c:a", "pcm_s16le", str(normalized),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        except FileNotFoundError as error:
            raise TranscriptionError(
                "ffmpeg is required for transcription; install webarena-pro-media "
                "or a system ffmpeg binary."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise TranscriptionError("Audio decoding timed out after 300 seconds.") from error
        if result.returncode:
            raise TranscriptionError(
                "Could not decode an audio track with ffmpeg. Verify that the URL "
                "returns a valid audio/video file with an audio track. "
                f"Decoder: {result.stderr.strip()[:300]}"
            )

        try:
            with wave.open(str(normalized), "rb") as audio:
                frame_count = audio.getnframes()
                duration = frame_count / _SAMPLE_RATE
                if start >= duration:
                    raise TranscriptionError(
                        f"Audio range starts at {start:g}s, outside the available "
                        f"audio duration of {duration:g}s."
                    )
                end = duration if end == -1 else min(end, duration)
                first_frame = int(start * _SAMPLE_RATE)
                last_frame = min(frame_count, round(end * _SAMPLE_RATE))
                selected_frames = last_frame - first_frame
                if selected_frames < _MIN_AUDIO_SECONDS * _SAMPLE_RATE:
                    raise TranscriptionError(
                        f"Audio range {start:g}-{end:g}s is empty or shorter than "
                        f"{_MIN_AUDIO_SECONDS:g}s; select a longer overlapping range."
                    )
                audio.setpos(first_frame)
                chunk_count = math.ceil(selected_frames / (_CHUNK_SECONDS * _SAMPLE_RATE))
                # Balance chunks so a tiny tail never becomes an audio_too_short
                # upload. Sample boundaries remain contiguous with no overlap.
                chunk_frames = math.ceil(selected_frames / chunk_count)
                parts = []
                position = first_frame
                for index in range(chunk_count):
                    frames = min(chunk_frames, last_frame - position)
                    pcm = audio.readframes(frames)
                    if len(pcm) != frames * 2:
                        raise TranscriptionError("Decoded audio is truncated; cannot transcribe it.")
                    buffer = io.BytesIO()
                    with wave.open(buffer, "wb") as chunk:
                        chunk.setnchannels(1)
                        chunk.setsampwidth(2)
                        chunk.setframerate(_SAMPLE_RATE)
                        chunk.writeframes(pcm)
                    data = buffer.getvalue()
                    backend = _transcribe_api if use_api else _transcribe_local
                    try:
                        text = backend(data, language)
                    except TranscriptionError as error:
                        raise TranscriptionError(
                            f"Chunk {index + 1}/{chunk_count} "
                            f"({position / _SAMPLE_RATE:g}-{(position + frames) / _SAMPLE_RATE:g}s): "
                            f"{error} No complete transcript was produced."
                        ) from error
                    if text:
                        parts.append(text)
                    position += frames
                return "\n".join(parts)
        except (wave.Error, EOFError) as error:
            raise TranscriptionError("ffmpeg did not produce readable PCM audio.") from error


def _api_error_message(error: Exception) -> str:
    """Keep useful diagnostics without echoing credentials or response bodies."""
    status = getattr(error, "status_code", None)
    code = getattr(error, "code", None)
    details = [type(error).__name__]
    if isinstance(status, int):
        details.append(f"HTTP {status}")
    if isinstance(code, str) and re.fullmatch(r"[a-zA-Z0-9_.-]{1,80}", code):
        details.append(f"code={code}")
    if status in (401, 403):
        hint = "Check OPENAI_API_KEY and transcription access at OPENAI_BASE_URL."
    elif status == 413:
        hint = "The provider rejected the upload size; check its audio upload limit."
    elif status == 400:
        hint = "The provider rejected the audio; check its duration, format, and model support."
    elif status == 429:
        hint = "Check the provider quota/rate limit and retry later."
    else:
        hint = "Check connectivity and OPENAI_BASE_URL, then retry."
    return f"Whisper API transcription failed ({', '.join(details)}). {hint}"


def _transcribe_api(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe one prepared WAV chunk using the OpenAI Whisper API."""
    if len(audio_bytes) > _MAX_UPLOAD_BYTES:
        raise TranscriptionError("Prepared audio exceeds the safe 20 MiB upload bound.")
    try:
        from openai import OpenAI
    except ImportError as error:
        raise TranscriptionError(
            "openai is required for Whisper API transcription. "
            "Install webarena-pro-media[transcription]."
        ) from error
    try:
        client = OpenAI()
    except Exception as error:
        raise TranscriptionError(
            "Could not configure the Whisper API client. Set OPENAI_API_KEY and, "
            "for a compatible proxy, OPENAI_BASE_URL. Select use_api=False "
            "explicitly to use an installed local Whisper model."
        ) from error

    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.wav"
    kwargs = {"model": "whisper-1", "file": audio_file}
    if language:
        kwargs["language"] = language
    try:
        result = client.audio.transcriptions.create(**kwargs)
        return result.text.strip()
    except Exception as error:
        raise TranscriptionError(_api_error_message(error)) from error
    finally:
        client.close()


def _transcribe_local(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe one prepared WAV chunk using the configured local model."""
    try:
        model = _get_whisper_model()
        with tempfile.TemporaryDirectory(prefix="webarena-pro-audio-") as temp_dir:
            audio_path = Path(temp_dir) / "audio.wav"
            audio_path.write_bytes(audio_bytes)
            result = model.transcribe(str(audio_path), language=language)
            return result["text"].strip()
    except Exception as error:
        raise TranscriptionError(
            "Local Whisper transcription failed. Install webarena-pro-media[local] "
            "and check the WEBARENA_PRO_WHISPER_MODEL model (default: base). "
            f"Error type: {type(error).__name__}."
        ) from error


def audio_bytes_to_base64(audio_bytes: bytes | None) -> str | None:
    """
    Convert audio bytes to a base64 string (for sending to omni model APIs).

    Args:
        audio_bytes: Raw audio file bytes.

    Returns:
        Base64-encoded string, or None.
    """
    if audio_bytes is None:
        return None
    return base64.b64encode(audio_bytes).decode("utf-8")


def transcribe_media(
    url: str,
    start_seconds: float = 0,
    end_seconds: float = -1,
    page: Any | None = None,
    language: str | None = None,
    use_api: bool = True,
) -> str:
    """Fetch audio/video, clip to the overlapping range, and transcribe.

    Negative starts clamp to zero; ``end_seconds=-1`` means the end. A range
    extending beyond the audio is clamped, but a wholly out-of-range or less
    than 0.1-second selection raises :class:`TranscriptionError`. Full files
    and selected ranges both use normalized, bounded uploads. An empty text
    result means the backend reported no speech, never a hidden failure.

    ``page`` optionally provides authenticated browser fetching. Set
    ``use_api=False`` to explicitly select local Whisper.
    """
    start, end = _validate_range(start_seconds, end_seconds)
    if not url:
        raise TranscriptionError("No media URL was provided for transcription.")
    audio_bytes = fetch_media_bytes(url, page=page, timeout=15.0)
    if audio_bytes is None:
        raise TranscriptionError(
            "Could not fetch media for transcription. Check the URL and browser authentication."
        )
    return _transcribe_prepared(audio_bytes, language, use_api, start, end)
