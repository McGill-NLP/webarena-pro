"""Synchronous audio and video API."""

from .audio import (
    TranscriptionError,
    audio_bytes_to_base64,
    extract_audio,
    install_audio_capture,
    transcribe_audio,
    transcribe_media,
)
from .binaries import ffmpeg_binary, ffprobe_binary
from .cache import clear_media_cache
from .clips import MediaClipError, extract_media_clip
from .fetch import MediaFetchError, fetch_media_bytes
from .video import extract_video_frames
from .watch import extract_watch_clip

__all__ = [
    "MediaClipError",
    "MediaFetchError",
    "extract_media_clip",
    "extract_watch_clip",
    "clear_media_cache",
    "TranscriptionError",
    "audio_bytes_to_base64",
    "extract_audio",
    "extract_video_frames",
    "fetch_media_bytes",
    "ffmpeg_binary",
    "ffprobe_binary",
    "install_audio_capture",
    "transcribe_audio",
    "transcribe_media",
]
