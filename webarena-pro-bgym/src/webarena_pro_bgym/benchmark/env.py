from contextvars import ContextVar
from dataclasses import dataclass
import inspect
from pathlib import Path
import logging
import time
from copy import deepcopy
from typing import Any

from browsergym.core.env import BrowserEnv
from browsergym.utils.obs import flatten_axtree_to_str

from agentlab.benchmarks.abstract_env import (
    AbstractEnv,
    AbstractEnvArgs,
)

from webarena_pro_bgym.benchmark.actions import is_completion_action
from webarena_pro_bgym.benchmark.browser_diagnostics import browser_operation
from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_media.sync_api import TranscriptionError, extract_audio, transcribe_audio
from webarena_pro_core.task import WebArenaProTaskConfig
from webarena_pro_bgym.utils import print_last_step_output, LastStepOutputType

logger = logging.getLogger(__name__)

REPORTING_STEP_BUDGETS = (50, 100)

_PENDING_TRANSCRIBE_RESULTS: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "webarena_pro_transcribe_results",
    default=(),
)
_PENDING_FRAMES_RESULTS: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "webarena_pro_frames_results",
    default=(),
)
_PENDING_LISTEN_RESULTS: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "webarena_pro_listen_results", default=(),
)
_PENDING_WATCH_RESULTS: ContextVar[tuple[dict[str, Any], ...]] = ContextVar(
    "webarena_pro_watch_results", default=(),
)
_WATCH_SETTINGS: ContextVar[tuple[bool, int]] = ContextVar(
    "webarena_pro_watch_settings", default=(False, 131_072),
)


def _check_pending_media_size(result: dict) -> None:
    """Bound combined action attachments before buying the next model call."""
    def size(clip):
        if clip.get("error"):
            return 0
        if "attachment_bytes" in clip:
            return clip["attachment_bytes"]
        data = clip.get("audio_b64", "")
        padding = len(data) - len(data.rstrip("="))
        return len(data) * 3 // 4 - padding
    pending = (*_PENDING_LISTEN_RESULTS.get(), *_PENDING_WATCH_RESULTS.get())
    if sum(size(clip) for clip in (*pending, result)) > 8 * 1024 * 1024:
        from webarena_pro_media.sync_api import MediaClipError
        raise MediaClipError("Combined media attachments exceed 8 MiB this step; request clips in separate steps or shorter intervals.")


def _drain_watch_results() -> list[dict[str, Any]]:
    results = list(_PENDING_WATCH_RESULTS.get())
    _PENDING_WATCH_RESULTS.set(())
    return results


def _drain_listen_results() -> list[dict[str, Any]]:
    results = list(_PENDING_LISTEN_RESULTS.get())
    _PENDING_LISTEN_RESULTS.set(())
    return results


def listen(
    url: str,
    start_seconds: float = 0,
    end_seconds: float = 30,
) -> str:
    """
    Listen to audio in the next observation. Read a URL from a [media audio] or [media video] node. Select an explicit 0.1--60 second interval; start must be nonnegative and end cannot be -1. Only WAV audio is attached, with source timing; a video URL extracts its audio track only. Use watch() for video. At most two audio clips per step and a 100 MiB source are allowed. Combined audio/video attachments are capped at 8 MiB per step. Requires audio_support. Errors are explicit; silence/music is not transcribed. Use transcribe() for a text transcript. The former n_frames argument was removed; migrate video requests to watch().

    Examples:
        listen("http://localhost:3000/audio/song.mp3", 30, 50)
    """
    from webarena_pro_bgym.benchmark.env import _PENDING_LISTEN_RESULTS, _check_pending_media_size
    from webarena_pro_media.sync_api import MediaClipError, extract_media_clip

    pending = _PENDING_LISTEN_RESULTS.get()
    try:
        if sum("audio_b64" in result for result in pending) >= 2:
            raise MediaClipError("At most two clips can be requested per step; listen again next step.")
        result = extract_media_clip(
            url, start_seconds, end_seconds, n_frames=0,
            page=page,  # noqa: F821 - supplied by BrowserGym's exec globals
        )
        _check_pending_media_size(result)
    except MediaClipError as error:
        result = {"url": url, "start": start_seconds, "end": end_seconds, "error": str(error)}
    _PENDING_LISTEN_RESULTS.set((*pending, result))
    return result.get("error", "Media clip attached to the next observation.")


def watch(
    url: str,
    start_seconds: float = 0,
    end_seconds: float = -1,
    mode: str = "overview",
    include_audio: bool = False,
    fps: float = 1.0,
    max_frames: int = 120,
) -> str:
    """
    Watch video from a [media video] URL in the next observation. Requires video_support. mode="overview" gives bounded timestamped still images across the range (end_seconds=-1 means the end), without audio; sparse samples can miss events. mode="detail" attaches an actual MP4 clip, with optional synchronized audio; end_seconds=-1 selects the next 30 seconds. mode="full" explicitly requests the entire selected interval if it fits the budget. Original source timestamps are preserved. Use include_audio=True to hear the video (requires audio_support); videos without audio still work. fps controls video sampling (0.1--5); max_frames bounds overview images (1--120). Shorter ranges/lower fps or fewer overview frames reduce cost. One successful watch per step. Errors report budget, range, fetch and decode failures; no silent fallback or truncation. Inspect long videos with an overview followed by selected detail intervals. Sampled coverage does not establish that every moment was inspected.

    Examples:
        watch("http://localhost:8000/static/videos/abc.mp4")
        watch("http://localhost:8000/static/videos/abc.mp4", 10, 40, mode="detail", include_audio=True)
    """
    from webarena_pro_bgym.benchmark.env import _PENDING_WATCH_RESULTS, _WATCH_SETTINGS, _check_pending_media_size
    from webarena_pro_media.sync_api import MediaClipError, extract_watch_clip

    pending = _PENDING_WATCH_RESULTS.get()
    try:
        audio_support, token_budget = _WATCH_SETTINGS.get()
        if include_audio and not audio_support:
            raise MediaClipError("This model has no audio support; use include_audio=False.")
        if any(not result.get("error") for result in pending):
            raise MediaClipError("At most one video request per step; watch again next step.")
        result = extract_watch_clip(
            url, start_seconds, None if end_seconds == -1 else end_seconds,
            mode=mode, include_audio=include_audio, fps=fps,
            # Native Gemini accounts overview JPEGs conservatively at 4096
            # tokens each versus Core's 1024-token video-frame estimate.
            max_input_tokens=token_budget // 4 if mode == "overview" else token_budget,
            max_frames=max_frames,
            page=page,  # noqa: F821 - supplied by BrowserGym's exec globals
        )
        _check_pending_media_size(result)
    except MediaClipError as error:
        result = {"url": url, "start": start_seconds, "end": end_seconds,
                  "mode": mode, "error": str(error)}
    _PENDING_WATCH_RESULTS.set((*pending, result))
    return result.get("error", "Video evidence attached to the next observation.")


def _stash_transcribe_result(
    url: str,
    start: float,
    end: float,
    transcript: str,
    error: str | None = None,
) -> None:
    result = {
        "url": url,
        "start": start,
        "end": end,
        "transcript": transcript or "",
    }
    if error is not None:
        result["error"] = error
    _PENDING_TRANSCRIBE_RESULTS.set((*_PENDING_TRANSCRIBE_RESULTS.get(), result))


def _drain_transcribe_results() -> list[dict[str, Any]]:
    results = list(_PENDING_TRANSCRIBE_RESULTS.get())
    _PENDING_TRANSCRIBE_RESULTS.set(())
    return results


def _stash_frames_result(
    url: str,
    n_frames: int,
    start: float,
    end: float,
    frames: list[dict[str, Any]],
) -> None:
    result = {
        "url": url,
        "n_frames": n_frames,
        "start": start,
        "end": end,
        "frames": frames,
    }
    _PENDING_FRAMES_RESULTS.set((*_PENDING_FRAMES_RESULTS.get(), result))


def _drain_frames_results() -> list[dict[str, Any]]:
    results = list(_PENDING_FRAMES_RESULTS.get())
    _PENDING_FRAMES_RESULTS.set(())
    return results


def transcribe(url: str, start_seconds: float = 0, end_seconds: float = -1, use_api: bool = True) -> str:
    """
    Transcribe the audio of an audio/video file (mp3/wav/mp4/webm/ogg) into text. The AXTree exposes media URLs as synthetic nodes of the form "[media audio] src=<URL>" or "[media video] src=<URL>"; read the URL from there and pass it. Optionally specify a time range [start_seconds, end_seconds] to transcribe only a portion of the file (end_seconds=-1 means to the end). Overlapping ranges clamp to the available audio; empty/out-of-range selections return an error. After this action runs, the transcription or actionable error appears as a synthetic text node in the AXTree on the next observation; a successful empty transcript is marked no_speech.

    Set use_api=False to use an installed local Whisper model instead of the default OpenAI transcription service.

    Examples:
        transcribe("http://localhost:3000/audio/song.mp3")
        transcribe("http://localhost:3000/audio/song.mp3", 30, 60)
        transcribe("http://localhost:3000/audio/song.mp3", start_seconds=45)
    """
    from webarena_pro_bgym.benchmark.env import _stash_transcribe_result
    from webarena_pro_media.sync_api import TranscriptionError, transcribe_media

    try:
        transcript = transcribe_media(
            url,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            page=page,  # noqa: F821 - supplied by BrowserGym's exec globals
            use_api=use_api,
        )
    except TranscriptionError as error:
        _stash_transcribe_result(url, start_seconds, end_seconds, "", error=str(error))
        return f"Transcription failed: {error}"
    _stash_transcribe_result(url, start_seconds, end_seconds, transcript)
    return transcript


def extract_frames(
    url: str,
    n_frames: int = 5,
    start_seconds: float = 0,
    end_seconds: float = -1,
) -> str:
    """
    Extract N evenly-spaced frames from a video file (mp4/webm/mov/etc.). The AXTree exposes media URLs as synthetic nodes "[media video] src=<URL>"; read the URL from there. Optionally specify a time range [start_seconds, end_seconds] (end_seconds=-1 means the end). Extracted frames appear as image attachments in the next observation.

    Examples:
        extract_frames("http://localhost:8000/static/videos/abc.mp4", 5)
        extract_frames("http://localhost:8000/static/videos/abc.mp4", 3, 10, 40)
        extract_frames("http://localhost:8000/static/videos/abc.mp4", 8, start_seconds=30)
    """
    from webarena_pro_bgym.benchmark.env import _stash_frames_result
    from webarena_pro_media.sync_api import extract_video_frames

    frames = extract_video_frames(
        url,
        n_frames=n_frames,
        start_seconds=start_seconds,
        end_seconds=end_seconds,
        page=page,  # noqa: F821 - supplied by BrowserGym's exec globals
    )
    _stash_frames_result(url, n_frames, start_seconds, end_seconds, frames)
    return ""


# ---------------------------------------------------------------------------
# Suppress Playwright "TargetClosedError" noise from the asyncio logger.
#
# When a task ends, BrowserEnv closes the browser/context. Any Playwright
# ``Channel.send`` coroutines still in-flight surface later as
# "Task exception was never retrieved: TargetClosedError(...)" via the asyncio
# default unhandled-exception path. These are harmless cleanup artifacts and
# clog the log. Drop them once, at import time of this module.
# ---------------------------------------------------------------------------

class _DropTargetClosedFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover
        exc_info = record.exc_info
        if exc_info and exc_info[0] is not None:
            if exc_info[0].__name__ == "TargetClosedError":
                return False
        msg = record.getMessage() if record.args else str(record.msg)
        if "TargetClosedError" in msg:
            return False
        return True


_asyncio_logger = logging.getLogger("asyncio")
if not any(isinstance(f, _DropTargetClosedFilter) for f in _asyncio_logger.filters):
    _asyncio_logger.addFilter(_DropTargetClosedFilter())


# Silence browsergym's empty-iframe warning. Nextcloud's Calendar / Talk /
# Office apps all embed iframes with no ``name`` attribute; browsergym warns
# each time it tries to mark/unmark them. The warning is harmless (the empty
# iframe just doesn't get BID annotations) but fires on every observation
# step, drowning out real log output.

class _DropEmptyFrameFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover
        msg = record.getMessage()
        if "Skipping frame '' for marking" in msg or "Skipping frame '' for unmarking" in msg:
            return False
        return True


_obs_logger = logging.getLogger("browsergym.core.observation")
if not any(isinstance(f, _DropEmptyFrameFilter) for f in _obs_logger.filters):
    _obs_logger.addFilter(_DropEmptyFrameFilter())


_BROWSER_ENV_ACCEPTS_USE_RAW_PAGE_OUTPUT = (
    "use_raw_page_output" in inspect.signature(BrowserEnv.__init__).parameters
)


class WebArenaProBrowserEnv(BrowserEnv):
    """
    Customized BrowserEnv for WebArenaPro.

    Adds audio-modality support: when ``enable_audio=True``, each observation
    captures a short audio segment from the active page and runs Whisper.
    Additionally, this environment always:

    - injects ``[media audio]``/``[media video]`` synthetic AXTree nodes
      exposing the ``src`` of any ``<audio>``/``<video>`` element on the page
      (so agents can discover URLs to pass to ``transcribe()``);
    - injects ``[TRANSCRIBE_RESULT ...]`` synthetic AXTree nodes carrying the
      output of any ``transcribe()`` call from the previous step.
    """

    last_step_output: LastStepOutputType = None
    last_action: str | None = None
    _budget_exhausted: bool = False
    _budget_checkpoint: bool = False

    # Audio capture knobs (set via WebArenaProEnvArgs)
    enable_audio: bool = True
    audio_duration: float = 5.0
    audio_transcribe: bool = True

    @browser_operation("observation")
    def _get_obs(self):
        self._prepare_navigation()
        obs = super()._get_obs()

        # Optional inline audio capture (raw bytes + Whisper transcript).
        replay_obs = getattr(self, "_checkpoint_replay_obs", None)
        if replay_obs is not None:
            # Rebuilding a browser must not buy the same background transcript.
            for key in ("audio_segment", "audio_transcript"):
                if key in replay_obs:
                    obs[key] = replay_obs[key]
        elif self.enable_audio:
            try:
                audio_bytes = extract_audio(self.page, duration=self.audio_duration)
                obs["audio_segment"] = audio_bytes
                if self.audio_transcribe and audio_bytes:
                    before_call = getattr(self, "_checkpoint_external_call", None)
                    if before_call is not None:
                        before_call()
                    obs["audio_transcript"] = transcribe_audio(audio_bytes)
                else:
                    obs["audio_transcript"] = ""
            except TranscriptionError as error:
                obs["audio_transcript"] = f"Transcription failed: {error}"
                _stash_transcribe_result(
                    "captured page audio", 0, self.audio_duration, "", error=str(error)
                )
            except Exception as e:
                logger.warning(f"Audio capture failed: {e}")
                obs["audio_segment"] = None
                obs["audio_transcript"] = ""

        # <audio>/<video> elements are invisible and excluded from the
        # accessibility tree by default. Inject synthetic text nodes that
        # expose their ``src`` URLs so the agent can discover them.
        try:
            self._inject_media_sources_into_axtree(obs)
        except Exception as e:
            logger.warning(f"Failed to inject media sources into AXTree: {e}")

        # Output of any ``transcribe()`` call from the previous step.
        try:
            self._inject_transcribe_results_into_axtree(obs)
        except Exception as e:
            logger.warning(f"Failed to inject transcribe results into AXTree: {e}")

        # Output of any ``extract_frames()`` call from the previous step.
        try:
            self._inject_frames_results_into_axtree(obs)
        except Exception as e:
            logger.warning(f"Failed to inject frame results into AXTree: {e}")

        self._inject_listen_results_into_axtree(obs)
        self._inject_watch_results_into_axtree(obs)
        guard = getattr(getattr(self, "task", None), "navigation_guard", None)
        if guard is not None:
            guard.remember_pages(getattr(self.context, "pages", ()))
        return obs

    def _prepare_navigation(self):
        guard = getattr(getattr(self, "task", None), "navigation_guard", None)
        if guard is None or not hasattr(self.context, "pages"):
            return
        guard.contain(self.context)
        pages = self.context.pages
        if self.page not in pages and pages:
            self.page = pages[-1]
        self.page_history = {
            page: value for page, value in self.page_history.items() if page in pages
        }
        warnings = guard.drain_warnings()
        if getattr(self.page, "url", "") == "chrome-error://chromewebdata/":
            warnings.append("Navigation failed. Use go_back() or navigate to an available task website.")
        if warnings:
            self.last_action_error = "\n".join(filter(None, [getattr(self, "last_action_error", ""), *warnings]))

    def _inject_listen_results_into_axtree(self, obs: dict):
        results = _drain_listen_results()
        # Keep the attachment even when a page has no accessibility tree.
        obs["media_clips"] = results
        nodes = (obs.get("axtree_object") or {}).get("nodes") or []
        if not nodes or not results:
            return
        root = next((node for node in nodes if not node.get("parentId")), nodes[0])
        next_id = max((int(n["nodeId"]) for n in nodes if str(n.get("nodeId", "")).isdigit()), default=0) + 1
        child_ids = []
        for index, result in enumerate(results):
            status = "error" if result.get("error") else "attached"
            details = result.get("error") or (
                f"WAV {result['sample_rate']} Hz, {result['channels']} channels; "
                "audio only."
            )
            node_id = str(next_id + index)
            nodes.append({
                "nodeId": node_id, "parentId": root["nodeId"],
                "role": {"type": "role", "value": "text"},
                "name": {"type": "computedString", "value": (
                    f"[LISTEN_RESULT url={result['url']} range={result['start']}-{result['end']} "
                    f"status={status}]: {details}"
                )},
                "ignored": False, "properties": [], "childIds": [],
            })
            child_ids.append(node_id)
        root["childIds"] = child_ids + list(root.get("childIds") or [])

    def _inject_watch_results_into_axtree(self, obs: dict):
        results = _drain_watch_results()
        obs["video_clips"] = results
        nodes = (obs.get("axtree_object") or {}).get("nodes") or []
        if not nodes or not results:
            return
        root = next((node for node in nodes if not node.get("parentId")), nodes[0])
        next_id = max((int(n["nodeId"]) for n in nodes
                       if str(n.get("nodeId", "")).isdigit()), default=0) + 1
        child_ids = []
        for index, result in enumerate(results):
            status = "error" if result.get("error") else "attached"
            details = result.get("error") or (
                f"{result['representation']}; audio_included={result['audio_included']}; "
                f"sampling={result.get('fps', 'overview')} fps. "
                "Sampled evidence does not establish continuous coverage."
            )
            node_id = str(next_id + index)
            nodes.append({
                "nodeId": node_id, "parentId": root["nodeId"],
                "role": {"type": "role", "value": "text"},
                "name": {"type": "computedString", "value": (
                    f"[WATCH_RESULT url={result['url']} range={result['start']}-{result['end']} "
                    f"mode={result['mode']} status={status}]: {details}"
                )},
                "ignored": False, "properties": [], "childIds": [],
            })
            child_ids.append(node_id)
        root["childIds"] = child_ids + list(root.get("childIds") or [])

    def _inject_media_sources_into_axtree(self, obs: dict):
        """Add synthetic AXTree nodes listing the ``src`` URLs of all
        ``<audio>``/``<video>`` elements on the page.

        Each URL is anchored to the closest ancestor with a ``bid`` (so the
        synthetic node ends up near the corresponding UI element in the
        flattened AXTree). Falls back to a global player widget if no
        specific ancestor is found, and finally to the AXTree root."""
        axtree = obs.get("axtree_object")
        if not axtree or "nodes" not in axtree:
            return

        try:
            media_sources = self.page.evaluate(
                """
                () => {
                    const srcs = [];

                    const findGlobalPlayerBid = () => {
                        const selectors = [
                            '[class*="now-playing" i]', '[class*="now_playing" i]',
                            '[class*="playback" i]', '[aria-label*="now playing" i]',
                            '[role="region"][aria-label*="play" i]',
                            'button[aria-label*="pause" i]',
                            'button[aria-label*="play/pause" i]',
                            '[class*="player-bar" i]', '[class*="playerbar" i]',
                            '[class*="player-controls" i]',
                            'input[type="range"][aria-label*="seek" i]',
                            'input[type="range"][aria-label*="progress" i]',
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (!el) continue;
                            let cur = el;
                            while (cur) {
                                const bid = cur.getAttribute && cur.getAttribute('bid');
                                if (bid) return bid;
                                cur = cur.parentElement;
                            }
                        }
                        return null;
                    };

                    const isSpecificAncestor = (el) => {
                        if (!el) return false;
                        const tag = el.tagName;
                        if (['BODY', 'HTML', 'MAIN'].includes(tag)) return false;
                        const cls = (el.className || '').toString().toLowerCase();
                        const rootLike = ['h-screen', 'min-h-screen', 'app-root', 'app-container'];
                        if (rootLike.some(p => cls.includes(p))) return false;
                        return true;
                    };

                    document.querySelectorAll('audio, video').forEach(el => {
                        const src = el.src || el.currentSrc || '';
                        if (!src) return;

                        let anchor = null;
                        let cur = el.parentElement;
                        while (cur) {
                            const bid = cur.getAttribute && cur.getAttribute('bid');
                            if (bid && isSpecificAncestor(cur)) { anchor = bid; break; }
                            cur = cur.parentElement;
                        }
                        if (!anchor) anchor = findGlobalPlayerBid();
                        if (!anchor) {
                            let cur2 = el.parentElement;
                            while (cur2) {
                                const bid = cur2.getAttribute && cur2.getAttribute('bid');
                                if (bid) { anchor = bid; break; }
                                cur2 = cur2.parentElement;
                            }
                        }
                        srcs.push({tag: el.tagName.toLowerCase(), src: src, anchor_bid: anchor});
                    });
                    return srcs;
                }
                """
            )
        except Exception:
            return

        if not media_sources:
            return

        nodes = axtree["nodes"]
        bid_to_node_id = {}
        for n in nodes:
            for prop in n.get("properties", []) or []:
                if prop.get("name") == "browsergym_id":
                    bid_to_node_id[prop.get("value", {}).get("value")] = n.get("nodeId")
                    break
        node_by_id = {n.get("nodeId"): n for n in nodes}

        root = None
        for n in nodes:
            parent = n.get("parentId")
            if parent is None or (isinstance(parent, dict) and parent.get("value") is None):
                root = n
                break
        if root is None:
            root = nodes[0]

        existing_ids = {str(n.get("nodeId", "")) for n in nodes}
        next_id = max(
            (int(nid) for nid in existing_ids if nid.isdigit()),
            default=0,
        ) + 1

        for media in media_sources:
            anchor_bid = media.get("anchor_bid")
            anchor_node_id = bid_to_node_id.get(anchor_bid) if anchor_bid else None
            anchor = node_by_id.get(anchor_node_id) if anchor_node_id else root

            syn_id = str(next_id)
            next_id += 1
            nodes.append({
                "nodeId": syn_id,
                "parentId": anchor.get("nodeId"),
                "role": {"type": "role", "value": "text"},
                "name": {
                    "type": "computedString",
                    "value": f"[media {media['tag']}] src={media['src']}",
                },
                "ignored": False,
                "properties": [],
                "childIds": [],
            })
            anchor["childIds"] = list(anchor.get("childIds") or []) + [syn_id]

    def _inject_transcribe_results_into_axtree(self, obs: dict):
        """Drain any pending ``transcribe()`` results and inject them as
        synthetic text nodes at the top of the AXTree so agents can read
        the tool output in their next observation."""
        results = _drain_transcribe_results()
        if not results:
            return
        axtree = obs.get("axtree_object")
        if not axtree or "nodes" not in axtree:
            return

        nodes = axtree["nodes"]
        existing_ids = {str(n.get("nodeId", "")) for n in nodes}
        next_id = max(
            (int(nid) for nid in existing_ids if nid.isdigit()),
            default=0,
        ) + 1

        root = None
        for n in nodes:
            parent = n.get("parentId")
            if parent is None or (isinstance(parent, dict) and parent.get("value") is None):
                root = n
                break
        if root is None:
            root = nodes[0]

        new_child_ids = []
        for r in results:
            prefix = (
                f"[TRANSCRIBE_RESULT url={r['url']} "
                f"range={r['start']}-{r['end']}"
            )
            if r.get("error"):
                label = f"{prefix} status=error]: {r['error']}"
            elif r["transcript"]:
                label = f"{prefix}]: {r['transcript']}"
            else:
                label = f"{prefix} status=no_speech]: No speech was returned by the transcriber."
            syn_id = str(next_id)
            next_id += 1
            nodes.append({
                "nodeId": syn_id,
                "parentId": root.get("nodeId"),
                "role": {"type": "role", "value": "text"},
                "name": {"type": "computedString", "value": label},
                "ignored": False,
                "properties": [],
                "childIds": [],
            })
            new_child_ids.append(syn_id)

        existing = list(root.get("childIds") or [])
        root["childIds"] = new_child_ids + existing

    def _inject_frames_results_into_axtree(self, obs: dict):
        """Drain any pending ``extract_frames()`` results and inject them as
        synthetic text nodes at the top of the AXTree so agents can read
        the tool output in their next observation."""
        results = _drain_frames_results()
        if not results:
            return
        axtree = obs.get("axtree_object")
        if not axtree or "nodes" not in axtree:
            return

        nodes = axtree["nodes"]
        existing_ids = {str(n.get("nodeId", "")) for n in nodes}
        next_id = max(
            (int(nid) for nid in existing_ids if nid.isdigit()),
            default=0,
        ) + 1

        root = None
        for n in nodes:
            parent = n.get("parentId")
            if parent is None or (isinstance(parent, dict) and parent.get("value") is None):
                root = n
                break
        if root is None:
            root = nodes[0]

        # Stash the raw frame bytes on obs so the prompt builder can render
        # them as image content blocks for VLM agents. Text-only agents will
        # only see the [FRAMES_RESULT ...] marker below.
        obs_frames = obs.setdefault("extracted_frames", [])

        new_child_ids = []
        for r in results:
            frames = r.get("frames") or []
            if frames:
                timestamps = ", ".join(f"t={f['timestamp']:.1f}s" for f in frames)
                label = (
                    f"[FRAMES_RESULT url={r['url']} n={r['n_frames']} "
                    f"range={r['start']}-{r['end']}]: {len(frames)} frames "
                    f"attached as images ({timestamps})."
                )
                for f in frames:
                    if f.get("image_b64"):
                        obs_frames.append({
                            "url": r["url"],
                            "timestamp": f["timestamp"],
                            "image_b64": f["image_b64"],
                        })
            else:
                label = (
                    f"[FRAMES_RESULT url={r['url']} n={r['n_frames']} "
                    f"range={r['start']}-{r['end']}]: (frame extraction failed)"
                )
            syn_id = str(next_id)
            next_id += 1
            nodes.append({
                "nodeId": syn_id,
                "parentId": root.get("nodeId"),
                "role": {"type": "role", "value": "text"},
                "name": {"type": "computedString", "value": label},
                "ignored": False,
                "properties": [],
                "childIds": [],
            })
            new_child_ids.append(syn_id)

        existing = list(root.get("childIds") or [])
        root["childIds"] = new_child_ids + existing

    def post_step(
        self, info: dict[str, Any], validate: bool = True
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        # Keep BrowserEnv's page settling and validation hooks, but collect the
        # resulting observation first. The study's pending StepInfo has no obs
        # until step() returns, so it cannot supply current evidence to a judge.
        if getattr(self, "_checkpoint_replaying", False):
            validate = False
        info["action_exec_stop"] = time.time()
        info["wait_for_page_loading_start"] = time.time()
        time.sleep(self.pre_observation_delay)
        self.context.cookies()  # flush pending Playwright callbacks
        monitor = getattr(self, "_browser_crash_monitor", None)
        if monitor is not None:
            monitor.check("observation")
        self._prepare_navigation()
        self._wait_dom_loaded()
        info["wait_for_page_loading_stop"] = time.time()

        if validate:
            self._active_page_check()
            self._wait_for_user_message()

        info["get_observation_start"] = time.time()
        obs = self._get_obs()
        info["get_observation_stop"] = time.time()

        if not hasattr(self, "episode_info") or self.episode_info is None:
            self.episode_info = []
        judge_obs = deepcopy(obs)
        # Agent preprocessing happens only after step() returns. Supply the
        # judge's text representation here without changing the agent's obs.
        if "axtree_txt" not in judge_obs and judge_obs.get("axtree_object"):
            judge_obs["axtree_txt"] = flatten_axtree_to_str(judge_obs["axtree_object"])
        self.last_step_output = {
            "obs": judge_obs,
            "reward": 0.0,
            "terminated": False,
            "truncated": False,
            "info": info,
            "episode_info": self.episode_info,
        }

        info["validation_start"] = time.time()
        if validate:
            reward, done, user_message, task_info = self._task_validate()
            if task_info.get("evaluation_trigger") == "budget_checkpoint":
                # Keep the cutoff score in task_info, not the accumulated
                # episode reward. A successful checkpoint must not end a run.
                reward = 0.0
        else:
            reward, done, user_message, task_info = 0.0, False, None, {}
        info["task_info"] = task_info
        info["validation_stop"] = time.time()

        if user_message:
            self.chat.add_message(role="user", msg=user_message)
            obs["chat_messages"] = tuple(deepcopy(self.chat.messages))
            judge_obs["chat_messages"] = obs["chat_messages"]

        terminated = done or (
            self.terminate_on_infeasible and self.infeasible_message_received
        )
        truncated = False
        self.last_step_output.update(
            reward=reward, terminated=terminated, truncated=truncated
        )
        logger.info(
            "post_step: step=%d reward=%s terminated=%s truncated=%s",
            len(self.episode_info),
            reward,
            terminated,
            truncated,
        )
        print_last_step_output(self.last_step_output, func_name="post_step")
        return obs, reward, terminated, truncated, info

    def register_episode_info(self, episode_info):
        if hasattr(self, "episode_info"):
            # warn that the episode_info is being overwritten
            logger.warning(
                "The episode_info is being overwritten. This may not be intended."
            )
        self.episode_info = episode_info

    def _task_validate(self, *, budget_exhausted: bool | None = None):
        prev_active_page = self.page
        prev_page_history = self.page_history.copy()
        # call validate
        print_last_step_output(self.last_step_output, func_name="_task_validate")

        reward, done, user_message, info = self.task.validate(
            self.page,
            self.chat.messages,
            last_step_output=self.last_step_output,
            last_action=self.last_action,
            budget_exhausted=(
                self._budget_exhausted if budget_exhausted is None else budget_exhausted
            ),
            budget_checkpoint=self._budget_checkpoint,
            termination_reason=(
                "agent_infeasible"
                if self.terminate_on_infeasible and self.infeasible_message_received
                else None
            ),
        )

        # safety fix, in case validate() did mess up the active page and/or page history
        if prev_active_page != self.page or prev_page_history != self.page_history:
            logger.debug(
                "The active page and / or page history has changed during task.validate(). A recovery fix will be applied."
            )
            self.page = prev_active_page
            self.page_history = prev_page_history

        return reward, done, user_message, info


@dataclass
class WebArenaProEnvArgs(AbstractEnvArgs):
    task_config: WebArenaProTaskConfig
    task_name: str
    task_seed: int = 0
    max_steps: int = 50  # -1 disables the environment step limit.
    action_space: str = "bid+coord"
    enable_audio: bool = True
    audio_duration: float = 5.0
    audio_transcribe: bool = True

    def make_env(
        self,
        exp_dir: Path,
        action_mapping=None,
        use_raw_page_output: bool = False,
    ) -> "WebArenaProEnv":
        env = WebArenaProEnv(
            self,
            action_mapping=action_mapping,
            use_raw_page_output=use_raw_page_output,
        )
        env.browser_diagnostics_dir = exp_dir
        return env
    

class WebArenaProEnv(AbstractEnv, WebArenaProBrowserEnv):
    def __init__(self, env_args: WebArenaProEnvArgs, **kwargs):
        self.env_args = env_args
        if (
            not _BROWSER_ENV_ACCEPTS_USE_RAW_PAGE_OUTPUT
            and "use_raw_page_output" in kwargs
        ):
            kwargs = dict(kwargs)
            kwargs.pop("use_raw_page_output", None)
        WebArenaProBrowserEnv.__init__(
            self,
            task_entrypoint=WebArenaProTask,
            task_kwargs={"config": env_args.task_config},
            **kwargs,
        )

        # Wire through audio-modality settings
        self.enable_audio = env_args.enable_audio
        self.audio_duration = env_args.audio_duration
        self.audio_transcribe = env_args.audio_transcribe

        self.steps_taken = 0

    @browser_operation("reset")
    def reset(self, seed=None):
        _drain_listen_results()
        _drain_watch_results()
        from webarena_pro_media.sync_api import clear_media_cache
        if getattr(self, "page", None) is not None:
            clear_media_cache(self.page)
        _drain_frames_results()
        _drain_transcribe_results()
        self.steps_taken = 0
        self._budget_exhausted = False
        self._budget_checkpoint = False
        self.last_action = None
        self.last_step_output = None
        return WebArenaProBrowserEnv.reset(self, seed)

    @browser_operation("step")
    def step(self, action):
        assert isinstance(action, str), (
            "Action must be a string of Python code to execute in the browser environment."
        )
        # Grade the live state after actions 50 and 100 as well as the final
        # allowed action. Each cutoff gets one evaluation, even at the limit.
        self._budget_exhausted = (
            self.env_args.max_steps != -1
            and self.steps_taken + 1 >= self.env_args.max_steps
        )
        self._budget_checkpoint = (
            self.steps_taken + 1 in REPORTING_STEP_BUDGETS
            and not self._budget_exhausted
        )
        try:
            obs, reward, terminated, truncated, info = WebArenaProBrowserEnv.step(
                self, action
            )
        finally:
            self._budget_exhausted = False
            self._budget_checkpoint = False
        self.steps_taken += 1
        if is_completion_action(action):
            terminated = True
        if (not terminated and self.env_args.max_steps != -1
                and self.steps_taken >= self.env_args.max_steps):
            truncated = True
        self.last_step_output.update(terminated=terminated, truncated=truncated)
        return obs, reward, terminated, truncated, info

    @browser_operation("budget_evaluation")
    def evaluate_budget_exhaustion(self):
        """Grade an agent-owned budget limit without taking another action.

        Use the last recorded observation and live backend before cleanup. The
        caller keeps its observation/action history and updates the final step
        with the returned reward, terminal flags and environment info.
        """
        output = self.last_step_output
        if output is None:
            raise RuntimeError("Cannot grade a budget limit before an observation exists")
        info = output["info"]
        if not output["terminated"] and not output["truncated"]:
            task_info = info.get("task_info") or {}
            if task_info.get("evaluation_trigger") == "budget_checkpoint":
                # The agent can hit its own limit immediately after a cutoff.
                # Reuse that exact state rather than buying a second judge call.
                reward, done, user_message = task_info["score"], False, None
                task_info = dict(task_info, evaluation_trigger="budget_exhaustion")
            else:
                info["validation_start"] = time.time()
                reward, done, user_message, task_info = self._task_validate(budget_exhausted=True)
                info["validation_stop"] = time.time()
            info["task_info"] = task_info
            if user_message:
                self.chat.add_message(role="user", msg=user_message)
            output.update(reward=reward, terminated=done, truncated=not done)
        return output["reward"], output["terminated"], output["truncated"], info

    def close(self):
        from webarena_pro_media.sync_api import clear_media_cache
        if getattr(self, "page", None) is not None:
            clear_media_cache(self.page)
        try:
            WebArenaProBrowserEnv.close(self)
        finally:
            _drain_listen_results()
            _drain_watch_results()
            _drain_frames_results()
            _drain_transcribe_results()
