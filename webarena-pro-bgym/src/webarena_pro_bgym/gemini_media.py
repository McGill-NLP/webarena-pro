"""Gemini native media requests for explicitly video-enabled agents.

The existing Gemini Chat Completions adapter remains unchanged. Video uses the
documented generateContent inlineData/videoMetadata contract, not an assumed
OpenAI-compatible video extension. No auxiliary model interprets the media.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
import time
from urllib.parse import quote
import wave

import httpx
from agentlab.llm.base_api import AbstractChatModel
from agentlab.llm.llm_utils import AIMessage
from agentlab.llm import tracking

logger = logging.getLogger(__name__)
GEMINI_NATIVE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_REQUEST_BYTES = 20 * 1024 * 1024


def _inline_part(block: dict, *, audio_support: bool) -> tuple[dict, int]:
    kind = block["type"]
    if kind == "text":
        text = block["text"]
        # Byte count is a conservative text-token allowance, not billing.
        return {"text": text}, len(text.encode("utf-8"))
    if kind == "image_url":
        url = block["image_url"]["url"]
        if not url.startswith("data:image/") or ";base64," not in url:
            raise ValueError("Gemini media requires inline image data, not remote image URLs.")
        header, data = url.split(",", 1)
        return {"inlineData": {"mimeType": header[5:].split(";")[0], "data": data}}, 4096
    if kind == "input_audio":
        if not audio_support:
            raise ValueError("Audio input requires audio_support=True.")
        audio = block["input_audio"]
        if audio["format"] != "wav":
            raise ValueError("Gemini media accepts WAV listen() attachments.")
        try:
            with wave.open(io.BytesIO(base64.b64decode(audio["data"], validate=True))) as wav:
                duration = wav.getnframes() / wav.getframerate()
        except (ValueError, wave.Error, EOFError) as error:
            raise ValueError("Invalid WAV audio attachment.") from error
        return {"inlineData": {"mimeType": "audio/wav", "data": audio["data"]}}, math.ceil(duration * 64)
    if kind == "input_video":
        video = block["input_video"]
        if video["audio_included"] and not audio_support:
            raise ValueError("Video audio requires audio_support=True; rewatch without audio.")
        if video["mime_type"] != "video/mp4":
            raise ValueError("watch() must supply an MP4 attachment.")
        return {
            "inlineData": {"mimeType": "video/mp4", "data": video["data"]},
            "videoMetadata": {"fps": video["fps"]},
        }, int(video["estimated_tokens"])
    raise ValueError(f"Unsupported Gemini media content block: {kind}")


class GeminiMediaChatModel(AbstractChatModel):
    request_provider = "gemini"

    def __init__(self, model_name, temperature=1.0, max_tokens=4096,
                 max_input_tokens=None, reasoning_effort=None, audio_support=False):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens or 4096
        self.max_input_tokens = max_input_tokens or 131_072
        self.reasoning_effort = reasoning_effort
        self.audio_support = audio_support
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY is required for the Gemini native media adapter.")
        self.native_client = httpx.Client(
            base_url=GEMINI_NATIVE_URL, headers={"x-goog-api-key": key},
            timeout=httpx.Timeout(180, connect=15),
        )
        self.last_response_metadata = {}
        self.retries = 0
        self.success = False
        self.error_types = []

    def __call__(self, messages, n_samples=1, temperature=None):
        if n_samples != 1:
            raise ValueError("The Gemini native media adapter supports one sample per request.")
        contents, instructions = [], []
        estimated_tokens = 0
        for message in messages:
            role = message["role"]
            content = message.get("content", "")
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            parts = []
            for block in blocks:
                part, estimate = _inline_part(block, audio_support=self.audio_support)
                parts.append(part)
                estimated_tokens += estimate
            if role in {"system", "developer"}:
                if any("text" not in part for part in parts):
                    raise ValueError("Gemini system instructions must be text.")
                instructions.extend(parts)
            elif role in {"user", "assistant"}:
                contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
            else:
                raise ValueError(f"Unsupported Gemini media message role: {role}")
        if estimated_tokens + self.max_tokens > self.max_input_tokens:
            raise ValueError(
                f"Estimated request plus output reserve ({estimated_tokens + self.max_tokens} tokens) "
                f"exceeds the {self.max_input_tokens} context allowance; shorten video intervals, "
                "lower fps, or reduce browser history."
            )
        body = {"contents": contents, "generationConfig": {
            "temperature": self.temperature if temperature is None else temperature,
            "maxOutputTokens": self.max_tokens,
        }}
        if instructions:
            body["systemInstruction"] = {"parts": instructions}
        if self.reasoning_effort is not None:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": self.reasoning_effort.upper()}
        encoded = json.dumps(body, separators=(",", ":")).encode()
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ValueError("Gemini media request exceeds 20 MiB; request fewer or shorter media clips.")
        self.retries, self.success, self.error_types = 0, False, []
        self.last_response_metadata = {}
        responses = []
        malformed_retries = 0
        for attempt in range(4):
            self.retries += 1
            # Never place the key in the URL, logs, or saved request metadata.
            response = self.native_client.post(
                f"models/{quote(self.model_name, safe='')}:generateContent",
                content=encoded, headers={"Content-Type": "application/json"},
            )
            if response.status_code == 429 or response.status_code >= 500:
                self.error_types.append(f"HTTP {response.status_code}")
                if attempt < 3:
                    time.sleep(min(2 ** (attempt + 1), 30))
                    continue
            response.raise_for_status()
            payload = response.json()
            usage = payload.get("usageMetadata", {})
            response_metadata = {
                "requested_model": self.model_name,
                "served_model": payload.get("modelVersion"),
                "http_status": response.status_code,
                "usage": usage,
                "estimated_input_tokens": estimated_tokens,
                "cost_available": False,
            }
            responses.append(response_metadata)
            self.last_response_metadata = {**response_metadata, "attempts": responses}
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0)
            tracker = getattr(tracking.TRACKER, "instance", None)
            if isinstance(tracker, tracking.LLMTracker):
                # Pricing is provider/model-specific; missing pricing is not $0.
                tracker(input_tokens, output_tokens, float("nan"))
            logger.info("Gemini media response requested=%s served=%s input_tokens=%s output_tokens=%s",
                        self.model_name, payload.get("modelVersion"), input_tokens, output_tokens)
            candidates = payload.get("candidates") or []
            text = "".join(part.get("text", "") for part in
                           (candidates[0].get("content", {}).get("parts", []) if candidates else [])
                           if not part.get("thought"))
            if not text:
                reason = candidates[0].get("finishReason", "empty") if candidates else "blocked or empty"
                response_metadata["finish_reason"] = reason
                # An explicit malformed-response finish is a known outcome,
                # not an ambiguous transport failure. Retry once and account
                # for both responses; safety blocks and other finishes fail.
                if reason == "MALFORMED_RESPONSE" and malformed_retries == 0 and attempt < 3:
                    malformed_retries += 1
                    self.error_types.append(reason)
                    logger.warning("Gemini returned MALFORMED_RESPONSE; retrying once with the same request.")
                    continue
                raise RuntimeError(f"Gemini returned no text action ({reason}).")
            self.success = True
            return AIMessage(text)
        raise RuntimeError("Gemini native media request failed after retries.")

    def get_stats(self):
        return {"n_retry_llm": self.retries, "native_cost_unavailable": 1}
