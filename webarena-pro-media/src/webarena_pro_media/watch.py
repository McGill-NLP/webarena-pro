"""Bounded video observations with source timing and explicit representations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any

from .binaries import ffmpeg_binary, ffprobe_binary
from .cache import MediaSource, media_source_cache
from .clips import MediaClipError
from .fetch import MediaFetchError

MAX_VIDEO_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_OVERVIEW_FRAMES = 120
MAX_RESOLUTION = 768
DEFAULT_MEDIA_TOKEN_BUDGET = 131_072
# Conservative planning estimates, not provider token accounting. Adapters must
# also enforce their actual request limits and reserve text/output context.
ESTIMATED_FRAME_TOKENS = 1024
ESTIMATED_AUDIO_TOKENS_PER_SECOND = 64
METADATA_TOKEN_RESERVE = 128


def _run(command: list[str], timeout: float = 120) -> subprocess.CompletedProcess:
    command = [command[0], "-protocol_whitelist", "file,pipe", *command[1:]]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as error:
        raise MediaClipError("watch() requires ffmpeg and ffprobe; install webarena-pro-media or system binaries.") from error
    except subprocess.TimeoutExpired as error:
        raise MediaClipError("Video processing timed out; select a shorter interval or fewer overview frames.") from error
    if result.returncode:
        raise MediaClipError("Could not decode the video; check the URL, tracks, and requested interval.")
    return result


def _probe(path: Path) -> dict:
    result = _run([ffprobe_binary(), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], timeout=30)
    try:
        metadata = json.loads(result.stdout)
        videos = [s for s in metadata["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
        duration = float(metadata["format"]["duration"])
        if not videos or not math.isfinite(duration) or duration <= 0:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise MediaClipError("Media has no readable video track/duration; use listen() for audio-only sources.") from error
    return {
        "duration": duration,
        "has_audio": any(s["codec_type"] == "audio" for s in metadata["streams"]),
        "frame_count": int(videos[0]["nb_frames"]) if str(videos[0].get("nb_frames", "")).isdigit() else None,
    }


def _complete_jpeg(path: Path) -> bool:
    """Reject interrupted cache writes before reusing a sampled frame."""
    try:
        if path.stat().st_size < 4:
            return False
        with path.open("rb") as image:
            if image.read(2) != b"\xff\xd8":
                return False
            image.seek(-2, 2)
            return image.read(2) == b"\xff\xd9"
    except OSError:
        return False


def extract_watch_clip(
    url: str,
    start_seconds: float = 0,
    end_seconds: float | None = None,
    *,
    mode: str = "overview",
    include_audio: bool = False,
    page: Any | None = None,
    max_frames: int = MAX_OVERVIEW_FRAMES,
    fps: float = 1.0,
    max_input_tokens: int = DEFAULT_MEDIA_TOKEN_BUDGET,
    source: MediaSource | None = None,
) -> dict[str, Any]:
    """Return video evidence for a subsequent model observation.

    Overview explicitly returns sparse JPEGs, up to one per 30 seconds and at
    most ``max_frames`` within the media token allowance; it never includes
    audio. Detail returns an MP4 (30 seconds by default), and full explicitly
    requests the complete selected interval. Both native modes preserve real
    playback speed while sampling video at ``fps``. A requested audio track is
    included when present; silent videos are valid and disclose its absence.

    Times are seconds on the source timeline. Ends beyond EOF clamp explicitly;
    all other limits produce errors, never a silently shortened clip. Sources
    are streamed/cached separately from the 8 MiB attachment limit. Estimates
    bound planning but cannot predict every provider's tokenization.
    ``source`` supplies an already fetched, validated local source, bypassing
    the downloader. Its parent directory holds the derived clip cache.
    """
    start, requested_end, rate = _validate_watch_request(mode, start_seconds, end_seconds, fps, max_frames, include_audio, max_input_tokens)
    try:
        cache = media_source_cache(page) if source is None else None
        source = source if source is not None else cache.get(url, page=page)
    except MediaFetchError as error:
        raise MediaClipError(str(error)) from error
    metadata = _probe(source.path)
    source_duration = metadata["duration"]
    end = requested_end
    if end is None:
        end = start + 30 if mode == "detail" else source_duration
    end = min(end, source_duration)
    duration = end - start
    if duration < 0.1 - 1e-9:
        raise MediaClipError(f"Requested interval is outside the {source_duration:g}-second video; choose an earlier start.")
    if mode != "overview" and duration < 1 / rate - 1e-9:
        raise MediaClipError(f"Available video has less than one frame interval at {rate:g} fps; increase fps or use extract_frames().")
    audio_included = include_audio and metadata["has_audio"]
    if mode == "overview":
        frame_count = min(max_frames, max(1, math.ceil(duration / 30)), (max_input_tokens - METADATA_TOKEN_RESERVE) // ESTIMATED_FRAME_TOKENS)
        effective_fps = frame_count / duration
    else:
        frame_count = max(1, math.ceil(duration * rate))
        effective_fps = rate
    estimated_tokens = METADATA_TOKEN_RESERVE + frame_count * ESTIMATED_FRAME_TOKENS
    if audio_included:
        estimated_tokens += math.ceil(duration * ESTIMATED_AUDIO_TOKENS_PER_SECOND)
    if estimated_tokens > max_input_tokens:
        allowed_seconds = max(0, (max_input_tokens - METADATA_TOKEN_RESERVE) / (rate * ESTIMATED_FRAME_TOKENS + (ESTIMATED_AUDIO_TOKENS_PER_SECOND if audio_included else 0)))
        raise MediaClipError(
            f"Video needs approximately {estimated_tokens} media tokens, above the {max_input_tokens} allowance. "
            f"Select at most {allowed_seconds:.1f} seconds at {rate:g} fps, lower fps, or request an overview."
        )
    result = {
        "url": url,
        "mode": mode,
        "representation": "sampled_frames" if mode == "overview" else "video",
        "start": start,
        "end": end,
        "duration": duration,
        "requested_start": start,
        "requested_end": requested_end,
        "source_duration": source_duration,
        "source_version": source.version,
        "source_cached": source.cached,
        "source_bytes": source.size,
        "clamped_to_eof": requested_end is not None and requested_end > source_duration,
        "audio_requested": include_audio,
        "audio_included": audio_included,
        "source_has_audio": metadata["has_audio"],
        "fps": effective_fps,
        "max_resolution": MAX_RESOLUTION,
        "estimated_input_tokens": estimated_tokens,
        "media_token_budget": max_input_tokens,
        "frame_count": frame_count,
        "frames": [],
    }
    identity = json.dumps([mode, start, end, frame_count, effective_fps, audio_included, MAX_RESOLUTION], separators=(",", ":"))
    output_directory = source.path.parent / hashlib.sha256(identity.encode()).hexdigest()
    output_directory.mkdir(exist_ok=True)
    deadline = time.monotonic() + 180
    if mode == "overview":
        total_bytes = 0
        for index in range(frame_count):
            timestamp = start + duration * (index + 0.5) / frame_count
            frame = output_directory / f"{index}.jpg"
            if not _complete_jpeg(frame):
                frame.unlink(missing_ok=True)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MediaClipError("Overview processing exceeded 180 seconds; request fewer frames or a shorter interval.")
                temporary = output_directory / f"{index}.part.jpg"
                try:
                    _run([
                        ffmpeg_binary(), "-nostdin", "-y", "-v", "error", "-ss", str(timestamp), "-i", str(source.path),
                        "-map", "0:V:0", "-frames:v", "1", "-vf", f"scale={MAX_RESOLUTION}:{MAX_RESOLUTION}:force_original_aspect_ratio=decrease", "-q:v", "4", str(temporary),
                    ], timeout=min(60, remaining))
                    if not _complete_jpeg(temporary):
                        raise MediaClipError("No complete video frame at the selected timestamp; choose an earlier interval.")
                    temporary.replace(frame)
                finally:
                    temporary.unlink(missing_ok=True)
            total_bytes += frame.stat().st_size
            if total_bytes > MAX_VIDEO_ATTACHMENT_BYTES:
                raise MediaClipError("Overview attachments exceed 8 MiB; reduce max_frames or select a shorter interval.")
            result["frames"].append({"timestamp": timestamp, "image_b64": base64.b64encode(frame.read_bytes()).decode("ascii")})
        result["attachment_bytes"] = total_bytes
        result["sampling"] = "Sparse images at the reported source timestamps; intervening events and audio were not supplied."
    else:
        output = output_directory / "clip.mp4"
        if not output.exists():
            temporary = output_directory / "clip.part.mp4"
            command = [
                ffmpeg_binary(), "-nostdin", "-y", "-v", "error", "-ss", str(start), "-i", str(source.path), "-t", str(duration),
                "-map", "0:V:0", "-vf", f"fps={rate}:start_time=0,scale={MAX_RESOLUTION}:{MAX_RESOLUTION}:force_original_aspect_ratio=decrease:force_divisible_by=2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
            ]
            if audio_included:
                command += ["-map", "0:a:0", "-af", "aresample=async=1:first_pts=0", "-c:a", "aac", "-b:a", "64k", "-ar", "24000", "-ac", "2"]
            else:
                command += ["-an"]
            command += ["-movflags", "+faststart", str(temporary)]
            try:
                _run(command, timeout=180)
                if not temporary.exists() or not temporary.stat().st_size:
                    raise MediaClipError("Video decoder returned no clip; choose a longer or earlier interval.")
                if temporary.stat().st_size > MAX_VIDEO_ATTACHMENT_BYTES:
                    raise MediaClipError("Video attachment exceeds 8 MiB; choose a shorter interval or lower fps.")
                _probe(temporary)
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
        if output.stat().st_size > MAX_VIDEO_ATTACHMENT_BYTES:
            raise MediaClipError("Video attachment exceeds 8 MiB; choose a shorter interval or lower fps.")
        encoded = _probe(output)
        result.update({
            "format": "mp4",
            "mime_type": "video/mp4",
            "video_b64": base64.b64encode(output.read_bytes()).decode("ascii"),
            "attachment_bytes": output.stat().st_size,
            "encoded_duration": encoded["duration"],
            "encoded_frame_count": encoded["frame_count"],
            "sampling": f"Video sampled at {rate:g} fps; clip t=0 corresponds to source t={start:g}s. Evidence ends at source t={end:g}s; encoded duration is {encoded['duration']:g}s (the final sampled frame can be held to its frame boundary).",
        })
    # Bound transformed variants too; retain the source currently in use.
    variants = sorted((p for p in source.path.parent.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime)
    if len(variants) > 16:
        import shutil
        removable = [variant for variant in variants if variant != output_directory]
        for variant in removable[:len(variants) - 16]:
            shutil.rmtree(variant)
    if cache is not None:
        cache._prune(keep=source.path.parent)
    return result


def _validate_watch_request(mode, start_seconds, end_seconds, fps, max_frames, include_audio, max_input_tokens):
    if mode not in {"overview", "detail", "full"}:
        raise MediaClipError("mode must be overview, detail, or full.")
    if type(include_audio) is not bool:
        raise MediaClipError("include_audio must be a boolean.")
    if mode == "overview" and include_audio:
        raise MediaClipError("Overview supplies sampled images without audio; use detail or full with include_audio=True.")
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_OVERVIEW_FRAMES:
        raise MediaClipError(f"max_frames must be an integer from 1 to {MAX_OVERVIEW_FRAMES}.")
    if type(max_input_tokens) is not int or max_input_tokens <= METADATA_TOKEN_RESERVE + ESTIMATED_FRAME_TOKENS:
        raise MediaClipError("Video input allowance is too small; reserve at least 1153 media tokens.")
    try:
        start = float(start_seconds)
        requested_end = None if end_seconds is None else float(end_seconds)
        rate = float(fps)
    except (TypeError, ValueError, OverflowError) as error:
        raise MediaClipError("Video times and fps must be finite numbers.") from error
    if not math.isfinite(start) or start < 0:
        raise MediaClipError("start_seconds must be finite and nonnegative.")
    if requested_end is not None and (not math.isfinite(requested_end) or requested_end - start < 0.1 - 1e-9):
        raise MediaClipError("Select a video interval of at least 0.1 seconds; use end_seconds=None for the default range.")
    if not math.isfinite(rate) or not 0.1 <= rate <= 5:
        raise MediaClipError("fps must be between 0.1 and 5; use a shorter interval for higher detail.")
    if mode != "overview" and requested_end is not None and requested_end - start < 1 / rate - 1e-9:
        raise MediaClipError(f"Native video needs at least {1 / rate:g} seconds at {rate:g} fps; increase fps or use extract_frames() for a shorter interval.")
    return start, requested_end, rate
