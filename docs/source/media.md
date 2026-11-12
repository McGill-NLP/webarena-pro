# Playwright Media Tools

Use the BrowserGym media actions to transcribe speech, sample video frames, or
send audio/video directly to a capable agent. The
[`webarena_pro_media.sync_api` helpers](#python-helpers) provide the reusable
processing layer for other integrations; their browser-facing functions accept
sync or async Playwright pages through the corresponding API module.

Choose `transcribe()` for speech as text, `extract_frames()` for still images,
`listen()` for sound, and `watch()` for a video overview or native video clip.
Direct listening preserves music and vocal qualities that a transcript omits;
video detail preserves motion that sampled frames can miss.

## Installation

Use Python 3.12 and `uv`. For standalone helpers, install the media package:

```bash
cd webarena-pro-media
uv venv --python 3.12
uv pip install ".[transcription]"
.venv/bin/playwright install chromium
# Optional local Whisper support
uv pip install ".[transcription,local]"
```

The paths above refer to `webarena-pro-media/`. Run Python examples with
`.venv/bin/python` in that directory. Core is not needed for media processing.

For BrowserGym agents, follow the [workspace installation](getting-started.md#requirements-and-installation),
which includes `webarena-pro-media[transcription,local]` and Chromium. Run the
CLI examples below from `webarena-pro-bgym/` with `uv run`. The
[getting-started guide](getting-started.md) covers credentials and website setup.

System `ffmpeg` and `ffprobe` binaries take precedence. When they are absent,
the `static-ffmpeg` package supplies platform binaries.

Set credentials in the process running the agent:

| Operation | Prerequisite |
| --- | --- |
| Remote `transcribe()` or background transcription | `OPENAI_API_KEY`; optionally `OPENAI_BASE_URL` for a proxy supporting the transcription endpoint and `whisper-1` |
| Local `transcribe(..., use_api=False)` | `webarena-pro-media[local]` and local Whisper weights; defaults to `base`, overridden by `WEBARENA_PRO_WHISPER_MODEL` |
| Direct Gemini audio/video | `GEMINI_API_KEY` and a supported model configuration; see [model configuration](#model-configuration) |
| Frame extraction or clip processing | Accessible media source and working `ffmpeg`/`ffprobe`; model credentials are needed separately to run an agent |

Local Whisper may download weights on first use. Remote transcription failures
do **not** automatically fall back to local Whisper. Direct `listen()` and
`watch()` requests send evidence to the evaluated model without using the
transcription service.

## BrowserGym action reference

These are agent action calls, executed by BrowserGym with its current page.
They are distinct from media functions that you import into your own Python code.
The benchmark's default `WebArenaProActionSetArgs` configuration includes the
`custom` action subset and registers media actions according to the negotiated
model capabilities:

| Action and defaults | Required capability | Evidence in the next observation |
| --- | --- | --- |
| `transcribe(url, start_seconds=0, end_seconds=-1, use_api=True)` | Always registered; requires the selected transcription backend | Text in an AXTree `[TRANSCRIBE_RESULT ...]` node; errors have `status=error`, empty speech has `status=no_speech` |
| `extract_frames(url, n_frames=5, start_seconds=0, end_seconds=-1)` | `vision_support=True` | Timestamped JPEGs in `obs["extracted_frames"]`, attached as images by the prompt builder, with an AXTree `[FRAMES_RESULT ...]` marker |
| `listen(url, start_seconds=0, end_seconds=30)` | `audio_support=True` with a supported adapter | WAV audio and timing in `obs["media_clips"]`, attached as audio, with an AXTree `[LISTEN_RESULT ...]` marker |
| `watch(url, start_seconds=0, end_seconds=-1, mode="overview", include_audio=False, fps=1.0, max_frames=120)` | `video_support=True`; overview images also need `vision_support=True`, and `include_audio=True` needs `audio_support=True` | Sampled JPEGs or an MP4 in `obs["video_clips"]`, attached in the matching representation, with an AXTree `[WATCH_RESULT ...]` marker |

`transcribe()` and `extract_frames()` use `end_seconds=-1` for the end of the
source. For `watch()`, it means the source end in `overview`/`full`, or the next
30 seconds in `detail`. `listen()` requires a finite end and defaults to the
first 30 seconds. See [limits, caching, and errors](#limits-caching-and-errors)
for the different range and size limits.

Audio/video capabilities add `listen()`/`watch()` to this existing action set;
there is no separate action-space selection. A video-capable model without
image support must request `mode="detail"` or `mode="full"`: its prompt reports
that overview images were omitted. Image-only models can use `extract_frames()`
without enabling native video.

### From a media URL to evidence

After opening a page containing an `<audio>` or `<video>` element, inspect the
AXTree for a synthetic source node. For example:

```text
[media video] src=https://example.test/media/demo.mp4
```

The URL here is illustrative; copy the actual `src` from your observation.
With an omni agent configured as shown below, request an overview as one action:

```python
watch("https://example.test/media/demo.mp4")
```

Read the next observation's `[WATCH_RESULT ... mode=overview status=attached]`
marker and the timestamped overview images. The corresponding
`obs["video_clips"]` entry reports `representation="sampled_frames"`, the source
range, and `audio_included=False`. Choose a relevant interval from those source
timestamps, then submit a new action in the next step:

```python
watch("https://example.test/media/demo.mp4", 10, 30, mode="detail", include_audio=True)
```

Inspect the next result's actual range, `representation="video"`, sampling,
and `audio_included` metadata along with the attached clip. A video without an
audio track can still succeed with `audio_included=False`. If `status=error`,
read the diagnostic before adjusting the request; an attachment marker alone
does not prove that the provider accepted or interpreted the media.

For other evidence, submit one of these alternative actions using the same
discovered URL (an audio source can also be passed to the first two):

```python
transcribe("https://example.test/media/demo.mp4", 10, 30)
```

Read the text in `[TRANSCRIBE_RESULT ...]`. For sound rather than text:

```python
listen("https://example.test/media/demo.mp4", 10, 30)
```

Read `[LISTEN_RESULT ...]` and listen to the attached WAV. For an image-capable
model without native video support:

```python
extract_frames("https://example.test/media/demo.mp4", 5, 10, 30)
```

Inspect `[FRAMES_RESULT ...]` and the attached images with source timestamps.
Requested media is attached only to the current observation, rather than
repeated throughout later prompt history. These examples are separate actions
with an intervening observation, not a Python script to run directly.

## Python helpers

The following examples use an existing synchronous Playwright `page` and a
`media_url` obtained by your integration. Media helpers return data directly to
your code; BrowserGym result markers and agent attachments belong to the adapter.

Adapters with their own fetch policy can pass `source_bytes` to
`extract_media_clip` / `extract_video_frames`, or a local `MediaSource` as
`source` to `extract_watch_clip`. These optional arguments bypass downloading;
the adapter must validate and bound the source first. Decoding uses local
file/pipe protocols only. Async integrations use these inputs to process fetched media without passing
browser objects to workers. The [MCP service](mcp.md) uses this path for its
separate WebArena Pro media server, alongside regular Playwright MCP.

### Async integrations

Use the async module with an async Playwright page:

```python
from webarena_pro_media.async_api import extract_audio, extract_media_clip, clear_media_cache

audio = await extract_audio(page, duration=5)
clip = await extract_media_clip(media_url, 0, 5, page=page, n_frames=0)
await clear_media_cache(page)  # on episode reset
```

Browser calls stay on their event loop. Blocking HTTP, decoding and transcription
run in workers with plain data. Cancellation waits for an active worker to finish
and clean up, and cache cleanup waits for in-flight processing. Both APIs use the
same processing and validation logic. BrowserGym uses the sync API; async
integrations can import the async API directly.

### Audio capture and transcription

Capture the active `<audio>` or `<video>` element through the browser's
`MediaRecorder` API:

```python
from webarena_pro_media.sync_api import extract_audio, transcribe_audio

audio_bytes = extract_audio(page, duration=5.0)
text = transcribe_audio(audio_bytes)  # OpenAI transcription API
text_local = transcribe_audio(audio_bytes, use_api=False)
```

`extract_audio` supports both Playwright APIs and browsers that
support `HTMLMediaElement.captureStream()` and `MediaRecorder`. Protected,
cross-origin, or DRM media may prevent browser capture.

To transcribe an existing audio or video URL, including a selected time range:

```python
from webarena_pro_media.sync_api import transcribe_media

text = transcribe_media(
    media_url,
    page=page,
    start_seconds=30,
    end_seconds=60,
)
```

The URL downloader first tries a direct HTTP request. If that fails, an
optional Playwright page supplies its authenticated browser context.

Remote transcription is the default and uses `whisper-1`. Select `use_api=False`
in the Python helpers or the BrowserGym action to use local Whisper; see
[installation](#installation) for dependencies and credentials.

All inputs, including full video files, are decoded with ffmpeg to 16 kHz mono
PCM audio before transcription. Audio is split into contiguous chunks of at
most 10 minutes (each WAV upload below 20 MiB, leaving headroom below the
reported 25 MiB proxy limit; other providers may impose different limits).
Chunks are submitted in chronological order and their
text is joined with newlines; the return value remains plain text without added
timestamps. The final chunk is balanced with the others so a very short tail
is not uploaded separately. This bounds each upload, not the download or local
temporary storage required to decode the source.

Ranges refer to decoded audio time. Negative starts clamp to zero, `end_seconds=-1`
means the end, and ends past the duration clamp to the last audio sample. A range
starting outside the audio, ending before its start, containing nonfinite values,
or selecting less than 0.1 seconds raises `TranscriptionError` before any API call.
Missing, undecodable, or empty audio also raises an error.

Successful transcription still returns a string; an empty string means the
backend returned no speech. Failures raise `TranscriptionError`, including
HTTP 400/413, authentication, transport, and local-model failures. API diagnostics
include status/error codes and setup/retry advice without copying credentials or
provider response bodies. A chunk failure identifies its source time range and
fails the complete call instead of returning an apparently complete partial
transcript. BrowserGym exposes these errors in the next AXTree observation with
`status=error`, while a successful empty response has `status=no_speech`.

### Video frames

Extract evenly spaced JPEG frames as base64 strings:

```python
from webarena_pro_media.sync_api import extract_video_frames

frames = extract_video_frames(
    media_url,
    page=page,
    n_frames=5,
    start_seconds=10,
    end_seconds=40,
)

for frame in frames:
    print(frame["timestamp"], frame["image_b64"][:40])
```

`ffprobe` determines the video duration and `ffmpeg` extracts each frame.

## Direct evidence for omni models

`listen(url, start_seconds=0, end_seconds=30)` delivers **audio only** as
timestamped WAV data. A video URL extracts its audio track, with no images.
Use `transcribe()` when a text transcript is needed.

`watch(url, start_seconds=0, end_seconds=-1, mode="overview",
include_audio=False, fps=1.0, max_frames=120)` handles video separately:

| Mode | Delivered evidence | Default interval |
| --- | --- | --- |
| `overview` | Bounded timestamped JPEG samples, no audio | Whole source |
| `detail` | Actual MP4 clip, optionally including synchronized audio | Next 30 seconds |
| `full` | Explicit whole-interval MP4 request, if it fits the allowance | Whole source |

`overview` is explicitly a sampled-image representation, not native video.
It samples at most 120 images, approximately one per 30 seconds, further bounded
by the model's media allowance. Intervening events and speech are not supplied.
For an hour-long source, request an overview and then inspect selected intervals:

```python
watch("https://example.test/media/long-video.mp4")
watch("https://example.test/media/long-video.mp4", 1200, 1320, mode="detail", include_audio=True)
```

Replace this illustrative URL with the observed source and submit these calls
in separate steps, inspecting the overview before choosing a detail interval.

Native clips preserve playback speed and original source timestamps. Their
encoded time zero corresponds to the requested source start. Sampling can miss
brief events: neither a whole-source overview nor a sparsely sampled MP4 proves
that every moment was inspected. Videos without audio are supported, and the
observation explicitly reports whether audio was actually included.

### Model configuration

For direct audio and video with Gemini, use an explicit omni alias:

```bash
uv run webarena-pro run --split dev --site acidwave --task 422,398 \
  --agent-model gemini/gemini-3.5-flash-omni
uv run webarena-pro run --split dev --site yt-lite --task 386,361 \
  --agent-model gemini/gemini-3.5-flash-omni
```

Every registered Gemini preset has `-audio` and `-omni` aliases. `-audio`
enables `audio_support` on the existing Chat Completions adapter; `-omni`
enables both `audio_support` and `video_support` and uses Gemini's native
`generateContent` API. Provider model IDs are unchanged. Record the response's
`modelVersion`: a provider may route an older model ID to a newer model.

Native Gemini requests use documented `inlineData` audio/image/video parts
and `videoMetadata.fps`, with text action responses. See
[Gemini video inputs](https://ai.google.dev/gemini-api/docs/generate-content/video-understanding).
The evaluated agent interprets the media directly; no auxiliary model summarizes
it. Unsupported content and provider errors are explicit, with no automatic
transcript or image fallback.
An explicit provider `MALFORMED_RESPONSE` with no text is retried once, with
both attempts' usage retained. Safety blocks and other empty responses fail
explicitly; ambiguous network failures are not automatically replayed.

Programmatically set `audio_support=True, video_support=True` on
`GeminiModelArgs`. Video support is independent of image support and requires
a verified adapter. Other adapters currently reject `video_support=True`.
Keep `extract_frames()` for explicit video sampling by image-capable models.

Audio-only support remains available with `GeminiModelArgs`,
`OpenRouterModelArgs`, `VLLMEndpointModelArgs(backend="vllm")`, and
`OpenAIAudioModelArgs`. Their deployed endpoints/models must accept the
documented `input_audio` WAV payload. Capabilities are declarations, not
inferred from model names or tested by paid startup calls.

A `WebArenaProStudy` negotiates capabilities and disables automatic background
audio capture/transcription for audio/video-enabled agents. A manually constructed
agent must call `configure_media(agent_args)` after `set_benchmark(...)`, before
constructing the agent or its action set:

```python
from copy import deepcopy

from agentlab.agents.generic_agent import GenericAgentArgs
from agentlab.agents.generic_agent.agent_configs import FLAGS_GPT_4o

from webarena_pro_bgym.agent import configure_media
from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark
from webarena_pro_bgym.llm_configs import WEBARENA_PRO_CHAT_MODEL_ARGS_DICT

benchmark = WebArenaProBenchmark(split="dev", sites=["yt-lite"])
agent_args = GenericAgentArgs(
    chat_model_args=deepcopy(
        WEBARENA_PRO_CHAT_MODEL_ARGS_DICT["gemini/gemini-3.5-flash-omni"]
    ),
    flags=deepcopy(FLAGS_GPT_4o),
)
agent_args.set_benchmark(benchmark, demo_mode=False)
configure_media(agent_args)

# Manual runners also disable the separate background transcription path.
for env_args in benchmark.env_args_list:
    env_args.enable_audio = False
    env_args.audio_transcribe = False

action_set = agent_args.flags.action.action_set.make_action_set()
```

`set_benchmark()` supplies `WebArenaProActionSetArgs`; `configure_media()` only
updates action sets of that type. It validates audio/video adapter support,
copies model image support, and sets the per-agent video allowance from its
input context. A model alias selects capabilities and an adapter, not another
action space. When using `WebArenaProStudy`, it performs these configuration
steps for you; see [programmatic BrowserGym usage](running-agents.md#programmatic-browsergym-usage).

The explicit `transcribe()` action remains available even when automatic
background capture is disabled. For a text/image-only agent, background capture
is enabled by default and uses the remote transcriber. Set
`env_args.enable_audio=False` on its `WebArenaProEnvArgs` to disable it, including
when using only on-demand local `transcribe(..., use_api=False)`.

### Limits, caching, and errors

- `listen()` selects 0.1–60 seconds, with a nonnegative start. `-1` is not an
  unlimited audio end. Default: 0–30 seconds. It supplies PCM16 WAV at 24 kHz,
  stereo; source size is capped at 100 MiB, attachments at 8 MiB, and successful
  audio requests at two per step. Ends beyond EOF clamp to decoded audio.
- `watch()` allows one successful request per step. Native video sampling
  accepts 0.1–5 FPS; dimensions are bounded to 768 pixels and attachments to
  8 MiB. The source download limit is separate (512 MiB). Detail intervals may
  exceed 60 seconds when the model allowance permits. Native intervals must
  span at least one sampled frame (`1 / fps` seconds). Encoded duration and
  frame count disclose frame-boundary rounding separately from the source range.
- Video planning estimates 1,024 tokens per frame plus 64 per audio second and
  metadata. Each agent reserves at least half its configured input context for
  other content, with a maximum 131,072-token media allowance. These are
  conservative estimates, not provider token accounting. The native adapter
  also checks combined request size (20 MiB), text/image/media estimates, and
  output reserve before making a generation request. Overview JPEG planning
  reserves 4,096 tokens per image; `max_frames` can further reduce sampling.
  All pending audio/video attachments together are capped at 8 MiB per step.
- Over-budget requests fail with smaller-range/lower-FPS suggestions.
  Requested ends beyond EOF clamp with explicit metadata; other limits never
  silently shorten the requested interval. Overview audio requests fail
  explicitly; use detail/full when sound is required.
- Sources stream to disk and are cached per browser context and authentication
  state. HTTP validators are rechecked; sources without validators are fetched
  and content-hashed again. Source versions and transformed variants are bounded
  and cleared on reset/close. Browser-only fallback is capped at 32 MiB and may
  buffer in Playwright before its size check; it is not a hard allocation bound.
  This implementation reuses local sources/clips, not provider-upload handles.
- `media_clips` and `[LISTEN_RESULT ...]` contain audio results;
  `video_clips` and `[WATCH_RESULT ...]` contain video results. Observations
  record requested/actual ranges, representation, sampling, audio inclusion,
  and errors. Payloads are attached once and not replayed in later prompts.
- Missing binaries, authentication/download failures, invalid media/ranges,
  processing timeouts, missing tracks, and size limits are explicit errors.
  A failed audio request does not establish silence.
- Native Gemini metadata records requested/served model IDs and provider token
  usage. Monetary cost is unavailable unless independently priced; unknown cost
  is not reported as zero dollars.

### Troubleshooting

| Symptom | What to check |
| --- | --- |
| `listen()` or `watch()` is absent from action descriptions | Use a supported model configuration with the required capability; manual runners must call `set_benchmark()` then `configure_media()` before constructing the action set. Keep the `custom` subset enabled. |
| Overview or extracted images are omitted | Enable model image support, or use native `watch(..., mode="detail")` with a video-capable adapter. Video capability alone does not enable image attachments. |
| Transcription authentication or endpoint error | Check `OPENAI_API_KEY` / `OPENAI_BASE_URL` and transcription endpoint support. Gemini model credentials do not configure the separate speech-to-text service. For local transcription, install `webarena-pro-media[local]` and explicitly pass `use_api=False`. |
| Unexpected background speech-to-text requests | Disable `WebArenaProEnvArgs.enable_audio`; `use_api=False` only changes that explicit transcription call. Studies automatically disable background capture for audio/video agents. |
| No source node or media download failure | Load the player so an `<audio>`/`<video>` source exists, copy its observed URL, and check access in the current authenticated browser context. Protected media may prevent capture/download. |
| Missing binary, decode failure, or failed frame extraction | Check the selected `ffmpeg`/`ffprobe` binaries and that the source contains the required track. `extract_frames()` may report failed extraction or omit individual images; inspect its marker and the images actually delivered. |
| Invalid range or over-budget request | Check the action-specific end convention, source duration, and limits above. Request a smaller interval, lower native FPS, or fewer overview frames; spread requests across steps. |
| `[TRANSCRIBE_RESULT ... status=no_speech]` | The backend returned no text. It does not establish that the source is silent; use direct audio when non-speech sound matters. |

### Migration and validation

The agent-visible `listen(..., n_frames=...)` argument is intentionally removed;
old calls fail validation/execution and must migrate to `watch(..., mode="detail")`
or `extract_frames()`. Existing `extract_media_clip(..., n_frames=...)`
remains available for programmatic compatibility. Checkpoint identities include
the new capability fields. Media actions, including `watch()`, are not replayed
during recovery, preventing repeated external work.

`extract_watch_clip()` and `clear_media_cache()` are framework-neutral.
Media package tests exercise real FFmpeg output, silent videos, source timestamps,
long-source sampling, caching, and limits. BrowserGym tests exercise generated
actions, per-agent capabilities, observation injection, native request JSON,
and one-time delivery. Fixture/mock tests are not live benchmark scores.

## Framework boundary

The reusable code lives in `webarena-pro-media`:

- browser audio capture;
- direct and authenticated media downloading;
- OpenAI or local Whisper transcription;
- audio slicing through ffmpeg;
- bounded raw audio/video clips with timing and format metadata;
- video probing and frame extraction;
- ffmpeg/ffprobe discovery.

The BrowserGym package retains only its integration layer:

- the agent-visible `listen()`, `watch()`, `transcribe()` and `extract_frames()` custom actions;
- pending action-result storage;
- capability negotiation, synthetic AXTree nodes and media attachments in the next observation.

This separation lets other Playwright environments call the Media APIs
without depending on Core, BrowserGym, or AgentLab. `sync_api` supports
synchronous Playwright, while `async_api` keeps async browser calls on their
owning event loop and offloads blocking processing. The MCP media servers use
the async API with sources already validated by their origin, redirect, and
size policies.
