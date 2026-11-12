"""Reusable video frame extraction for synchronous Playwright environments.

``extract_video_frames`` downloads a video, optionally through an authenticated
Playwright page, and returns evenly spaced JPEG frames as base64 strings.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
import subprocess
import tempfile
from typing import Any, TypedDict

from .binaries import ffmpeg_binary, ffprobe_binary
from .fetch import fetch_media_bytes
from .cache import MediaSource

logger = logging.getLogger(__name__)


class ExtractedFrame(TypedDict):
    """One JPEG frame produced by :func:`extract_video_frames`."""

    timestamp: float
    image_b64: str


def probe_video_duration(video_path: str | Path) -> float | None:
    """Return the video duration in seconds, or None if probing fails."""
    try:
        result = subprocess.run(
            [
                ffprobe_binary(),
                "-protocol_whitelist", "file,pipe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("extract_frames(): ffprobe not found: %s", e)
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def extract_video_frame(
    video_path: str | Path,
    timestamp: float,
    out_path: str | Path,
    width: int = 1280,
) -> bool:
    """Extract a single frame at ``timestamp`` (seconds) into ``out_path`` (jpg).
    Returns True on success. Resizes width to the given pixel width to control
    token cost when sent to a VLM."""
    cmd = [
        ffmpeg_binary(),
        "-protocol_whitelist", "file,pipe",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        str(timestamp),
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-1",
        out_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("extract_frames(): ffmpeg not found: %s", e)
        return False
    output = Path(out_path)
    return result.returncode == 0 and output.exists() and output.stat().st_size > 0


def extract_video_frames(
    url: str,
    n_frames: int = 5,
    start_seconds: float = 0,
    end_seconds: float = -1,
    page: Any | None = None,
    width: int = 1280,
    *,
    source_bytes: bytes | None = None,
    source: MediaSource | None = None,
) -> list[ExtractedFrame]:
    """Download the video, extract N frames as JPEG bytes. Returns a list of
    {"timestamp": float, "image_b64": str} dicts in time order, where
    ``image_b64`` is a base64-encoded JPEG (1280px wide, ~720p).
    Supply ``source_bytes`` or a validated disk ``source`` to decode without fetching.
    """
    if not url:
        logger.warning("extract_frames(): no URL provided")
        return []
    if n_frames <= 0:
        logger.warning(f"extract_frames(): n_frames must be > 0, got {n_frames}")
        return []

    logger.info(
        f"extract_frames(): url={url!r} n={n_frames} "
        f"start={start_seconds}s end={end_seconds}s"
    )

    video_bytes = None if source is not None else (source_bytes if source_bytes is not None else fetch_media_bytes(url, page=page))
    if source is None and video_bytes is None:
        logger.warning(f"extract_frames(): could not fetch {url}")
        return []
    if (source.size if source is not None else len(video_bytes)) < 64:
        logger.warning("extract_frames(): file too small")
        return []

    # Use the URL's extension if it's a known video format, else default to .mp4
    ext = ".mp4"
    cleaned = url.split("?")[0].lower()
    for cand in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
        if cleaned.endswith(cand):
            ext = cand
            break

    with tempfile.TemporaryDirectory(prefix="webarena-pro-video-") as temp_dir:
        temp_path = Path(temp_dir)
        src_path = source.path if source is not None else temp_path / f"source{ext}"
        if source is None:
            src_path.write_bytes(video_bytes)

        # Determine the time window
        duration = probe_video_duration(src_path)
        if duration is None or duration <= 0:
            logger.warning("extract_frames(): could not probe video duration")
            return []
        s = max(0.0, float(start_seconds))
        e = duration if end_seconds < 0 else min(float(end_seconds), duration)
        if e <= s:
            logger.warning(f"extract_frames(): empty window [{s}, {e}]")
            return []

        # Compute N evenly-spaced timestamps inside (s, e)
        if n_frames == 1:
            timestamps = [s + (e - s) / 2]
        else:
            step = (e - s) / (n_frames + 1)
            timestamps = [s + step * (i + 1) for i in range(n_frames)]

        frames: list[ExtractedFrame] = []
        for index, timestamp in enumerate(timestamps):
            frame_path = temp_path / f"frame-{index}.jpg"
            ok = extract_video_frame(
                src_path,
                timestamp,
                frame_path,
                width=width,
            )
            if not ok:
                logger.warning("extract_frames(): ffmpeg failed at t=%s", timestamp)
                frames.append({"timestamp": timestamp, "image_b64": ""})
                continue
            frames.append(
                {
                    "timestamp": timestamp,
                    "image_b64": base64.b64encode(frame_path.read_bytes()).decode(
                        "utf-8"
                    ),
                }
            )

        return frames
