"""Helpers for locating ffmpeg/ffprobe binaries."""

from __future__ import annotations

from functools import lru_cache
import logging
import shutil

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _static_ffmpeg_paths() -> tuple[str, str] | None:
    try:
        from static_ffmpeg import run
    except ImportError:
        return None

    try:
        ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
        return ffmpeg, ffprobe
    except Exception as e:
        logger.warning("static-ffmpeg could not provide ffmpeg/ffprobe: %s", e)
        return None


def ffmpeg_binary() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    static_paths = _static_ffmpeg_paths()
    if static_paths:
        return static_paths[0]
    return "ffmpeg"


def ffprobe_binary() -> str:
    path = shutil.which("ffprobe")
    if path:
        return path
    static_paths = _static_ffmpeg_paths()
    if static_paths:
        return static_paths[1]
    return "ffprobe"
