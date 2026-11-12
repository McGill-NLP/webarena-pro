"""Schemas shared by the media MCP server and its validating client."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from jsonschema import Draft202012Validator

from .tool_policy import PolicyError

MEDIA_TOOLS = frozenset({"media_transcribe", "media_extract_frames", "media_listen", "media_watch"})
MEDIA_PROFILES = ("standard", "omni")
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_CACHE_BYTES = 1024 * 1024 * 1024
MAX_FRAMES = 120
MAX_TRANSCRIBE_SECONDS = 3600
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class MediaSettings:
    enabled: bool = True
    profile: str = "standard"
    audio: bool = False
    video: bool = False
    transcription: str = "api"
    timeout: float = 180
    transcription_timeout: float = 900

    def __post_init__(self):
        if self.profile not in MEDIA_PROFILES:
            raise ValueError("media profile must be standard or omni")
        if self.profile == "omni" and not (self.audio or self.video):
            raise ValueError("The omni media profile requires audio or video input support")
        if self.profile == "standard" and (self.audio or self.video):
            raise ValueError("Audio/video input requires the explicit omni media profile")
        if self.transcription not in {"api", "local", "disabled"}:
            raise ValueError("transcription must be api, local or disabled")
        for name in ("timeout", "transcription_timeout"):
            value = getattr(self, name)
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError(f"media {name} must be finite and positive")
        if any(type(value) is not bool for value in (self.enabled, self.audio, self.video)):
            raise ValueError("media capabilities must be booleans")

    def as_dict(self):
        return asdict(self)

    def timeout_for(self, name):
        return self.transcription_timeout if name == "media_transcribe" else self.timeout

    @property
    def server_name(self):
        return "webarena-pro-omni" if self.profile == "omni" else "webarena-pro"

    def capabilities(self):
        return {
            "media": self.enabled,
            "media_profile": self.profile if self.enabled else None,
            "audio": self.enabled and self.audio,
            "native_video": self.enabled and self.video,
        }


def schemas(settings: MediaSettings):
    if not settings.enabled:
        return {}
    base = {
        "ref": {
            "type": "string",
            "pattern": "^m[0-9a-f]{24}$",
            "description": (
                "Copy the media ref from the current Page media observation, "
                "not its URL or a browser element ref."
            ),
        },
        "start_seconds": {"type": "number", "minimum": 0, "default": 0},
        "end_seconds": {"type": ["number", "null"], "minimum": 0.1, "default": None,
                        "description": "End on the source timeline; null selects the full source (30 seconds for listen/detail)."},
    }
    definitions = {
        "media_transcribe": (
            "Transcribe up to one hour of registered page audio/video in bounded chunks. "
            "Returns text and timing, or an explicit error. Uses the configured transcription backend.",
            {},
        ),
        "media_extract_frames": (
            "Extract timestamped JPEG images from registered page video. Samples can miss intervening events.",
            {"n_frames": {"type": "integer", "minimum": 1, "maximum": MAX_FRAMES, "default": 5}},
        ),
        "media_listen": (
            "Hear a 0.1–60 second interval of registered page audio/video. Returns real WAV audio, "
            "never a transcript or video frames. Missing audio is an error, not evidence of silence.",
            {},
        ),
        "media_watch": (
            "Inspect registered video. overview returns sampled timestamped images without audio; "
            "detail/full return MP4 with optional synchronized audio. Sampling is not continuous coverage.",
            {
                "mode": {
                    "type": "string",
                    "enum": ["overview", "detail", "full"] if settings.video else ["overview"],
                    "default": "overview",
                },
                "include_audio": {
                    "type": "boolean",
                    **({} if settings.audio else {"const": False}),
                    "default": False,
                },
                "fps": {"type": "number", "minimum": 0.1, "maximum": 5, "default": 1},
                "max_frames": {"type": "integer", "minimum": 1, "maximum": MAX_FRAMES, "default": MAX_FRAMES},
            },
        ),
    }
    result = {}
    for name, (description, extra) in definitions.items():
        if name == "media_listen" and not settings.audio:
            continue
        if name == "media_transcribe" and settings.transcription == "disabled":
            continue
        result[name] = {
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": {**base, **extra},
                "required": ["ref"],
                "additionalProperties": False,
            },
        }
    return result


def validate(name, arguments, settings):
    definition = schemas(settings).get(name)
    if definition is None or list(Draft202012Validator(definition["inputSchema"]).iter_errors(arguments)):
        raise PolicyError("Media tool or arguments are outside the configured capabilities")
    start = arguments.get("start_seconds", 0)
    end = arguments.get("end_seconds")
    if end is None and (name == "media_listen" or (name == "media_watch" and arguments.get("mode") == "detail")):
        end = start + 30
    if (
        not math.isfinite(start)
        or not math.isfinite(arguments.get("fps", 1))
        or (end is not None and (not math.isfinite(end) or end - start < 0.1 - 1e-9))
    ):
        raise PolicyError("Select a finite media interval of at least 0.1 seconds")
    if name == "media_listen" and end - start > 60:
        raise PolicyError("Select a 0.1–60 second interval for native WAV audio")
    if name == "media_transcribe" and end is not None and end - start > MAX_TRANSCRIBE_SECONDS:
        raise PolicyError("Transcription intervals cannot exceed one hour")
    if name == "media_watch" and arguments.get("mode", "overview") == "overview" and arguments.get("include_audio", False):
        raise PolicyError("Overview returns JPEG frames without audio; use media_listen for audio")
    return {**arguments, "start_seconds": start, "end_seconds": end}
