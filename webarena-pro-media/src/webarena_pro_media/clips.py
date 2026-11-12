"""Bounded, timestamped media evidence for audio-capable models."""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
import subprocess
import tempfile
from typing import Any
import wave

from .audio import audio_bytes_to_base64
from .binaries import ffmpeg_binary, ffprobe_binary
from .fetch import MediaFetchError, fetch_media_bytes
from .cache import MediaSource

MAX_CLIP_SECONDS = 60
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024  # decoded WAV + JPEGs, before base64
MAX_FRAMES = 5
SAMPLE_RATE = 24_000


class MediaClipError(RuntimeError):
    """A requested clip could not be delivered; this does not imply silence."""


def _run(command: list) -> subprocess.CompletedProcess:
    # All inputs are local, already fetched bytes. Decoders must not open
    # secondary network URLs embedded in a media container.
    command = [command[0], "-protocol_whitelist", "file,pipe", *command[1:]]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except FileNotFoundError as error:
        raise MediaClipError(
            "ffmpeg and ffprobe are required; install webarena-pro-media "
            "or system binaries."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise MediaClipError(
            "Media processing exceeded the 60 second timeout."
        ) from error
    if result.returncode:
        raise MediaClipError(
            "Could not decode the requested media. Check the URL, media format, "
            "tracks, and time range."
        )
    return result


def extract_media_clip(
    url: str,
    start_seconds: float = 0,
    end_seconds: float = 30,
    *,
    n_frames: int = 3,
    page: Any | None = None,
    source_bytes: bytes | None = None,
    source: MediaSource | None = None,
) -> dict[str, Any]:
    """Fetch once and return WAV audio plus synchronized JPEG video samples.

    Times are seconds on the source timeline. Request an explicit interval of
    0.1--60 seconds (no unbounded ``-1`` end). Ends past EOF clamp to decoded
    audio. Video is sampled at up to five points inside the delivered interval;
    ``n_frames=0`` explicitly requests audio alone. Audio-only files have no
    frames. No transcription service or model key is used.
    ``source_bytes`` lets an adapter supply policy-validated bytes without a
    second fetch; ``source`` accepts a validated disk source with its own download
    limits. The URL then serves only as source metadata.
    """
    start, end = _validate_clip_request(url, start_seconds, end_seconds, n_frames)
    try:
        data = None if source is not None else (source_bytes if source_bytes is not None else fetch_media_bytes(url, page=page, max_bytes=MAX_SOURCE_BYTES))
    except MediaFetchError as error:
        raise MediaClipError(str(error)) from error
    if source is None and not data:
        raise MediaClipError(
            "Could not fetch media. Check the URL and browser authentication."
        )
    if source is None and len(data) > MAX_SOURCE_BYTES:
        raise MediaClipError("Media source exceeds the 100 MiB limit.")

    with tempfile.TemporaryDirectory(prefix="webarena-pro-clip-") as directory:
        source_path = source.path if source is not None else Path(directory) / "source.media"
        if source is None:
            source_path.write_bytes(data)
        probe = _run(
            [
                ffprobe_binary(),
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                str(source_path),
            ]
        )
        try:
            streams = json.loads(probe.stdout)["streams"]
            has_audio = any(s["codec_type"] == "audio" for s in streams)
            has_video = any(
                s["codec_type"] == "video"
                and not s.get("disposition", {}).get("attached_pic")
                for s in streams
            )
        except (ValueError, KeyError, TypeError) as error:
            raise MediaClipError("Could not read the media track metadata.") from error
        if not has_audio:
            raise MediaClipError(
                "Media has no audio track. Use extract_frames() for silent video."
            )

        audio_path = Path(directory) / "audio.wav"
        _run(
            [
                ffmpeg_binary(),
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(source_path),
                "-ss",
                str(start),
                "-t",
                str(end - start),
                "-map",
                "0:a:0",
                "-vn",
                # Preserve gaps/offsets on the video timeline instead of shifting
                # late-starting audio to the beginning of the requested interval.
                "-af",
                "aresample=async=1:first_pts=0",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ]
        )
        try:
            with wave.open(str(audio_path), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
        except (wave.Error, EOFError, OSError) as error:
            raise MediaClipError(
                "Decoder did not return readable WAV audio."
            ) from error
        if duration < 0.1:
            raise MediaClipError(
                "Requested range has less than 0.1 seconds of audio; check its timing."
            )
        end = start + duration
        total_bytes = audio_path.stat().st_size
        if total_bytes > MAX_ATTACHMENT_BYTES:
            raise MediaClipError(
                "Media attachments exceed 8 MiB; select a shorter interval."
            )
        frames = []
        if has_video:
            for index in range(n_frames):
                timestamp = start + duration * (index + 1) / (n_frames + 1)
                destination = Path(directory) / f"frame-{index}.jpg"
                _run(
                    [
                        ffmpeg_binary(),
                        "-nostdin",
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        str(timestamp),
                        "-i",
                        str(source_path),
                        "-map",
                        "0:V:0",
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=768:768:force_original_aspect_ratio=decrease",
                        str(destination),
                    ]
                )
                if not destination.exists() or not destination.stat().st_size:
                    raise MediaClipError(
                        "No video frame at the requested time; select an earlier interval."
                    )
                total_bytes += destination.stat().st_size
                if total_bytes > MAX_ATTACHMENT_BYTES:
                    raise MediaClipError(
                        "Media attachments exceed 8 MiB; request fewer frames."
                    )
                frames.append(
                    {
                        "timestamp": timestamp,
                        "image_b64": base64.b64encode(destination.read_bytes()).decode(
                            "ascii"
                        ),
                    }
                )
        return {
            "url": url,
            "start": start,
            "end": end,
            "duration": duration,
            "requested_start": float(start_seconds),
            "requested_end": float(end_seconds),
            "format": "wav",
            "mime_type": "audio/wav",
            "sample_rate": SAMPLE_RATE,
            "channels": 2,
            "audio_b64": audio_bytes_to_base64(audio_path.read_bytes()),
            "frames": frames,
        }


def _validate_clip_request(url, start_seconds, end_seconds, n_frames):
    try:
        start, end = float(start_seconds), float(end_seconds)
    except (ValueError, TypeError, OverflowError) as error:
        raise MediaClipError("Clip times must be finite numbers.") from error
    if not math.isfinite(start) or not math.isfinite(end):
        raise MediaClipError("Clip times must be finite numbers.")
    if start < 0 or not 0.1 - 1e-9 <= end - start <= MAX_CLIP_SECONDS + 1e-9:
        raise MediaClipError(
            "Select a nonnegative start and a 0.1--60 second interval."
        )
    if type(n_frames) is not int or not 0 <= n_frames <= MAX_FRAMES:
        raise MediaClipError("n_frames must be an integer from 0 to 5.")
    if not url:
        raise MediaClipError("A media URL is required.")
    return start, end
