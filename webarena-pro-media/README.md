# WebArena-Pro media

Browser audio/video capture, authenticated fetching, bounded audio clips,
video evidence, and optional transcription. This package is independent of
WebArena-Pro Core and its benchmark adapters.

```bash
pip install webarena-pro-media
pip install 'webarena-pro-media[transcription]'  # API transcription
pip install 'webarena-pro-media[local]'          # optional local Whisper
```

Use `webarena_pro_media.sync_api` with synchronous Playwright pages and
`webarena_pro_media.async_api` with asynchronous pages:

```python
from webarena_pro_media.sync_api import extract_audio, extract_media_clip

audio = extract_audio(sync_page, duration=5)
clip = extract_media_clip(url, 0, 5, page=sync_page, n_frames=0)
```

```python
from webarena_pro_media.async_api import extract_audio, extract_media_clip

audio = await extract_audio(async_page, duration=5)
clip = await extract_media_clip(url, 0, 5, page=async_page, n_frames=0)
```

Both APIs provide `install_audio_capture`, `extract_audio`, `fetch_media_bytes`,
`extract_media_clip`, `extract_video_frames`, `extract_watch_clip`,
`transcribe_audio`, `transcribe_media`, and `clear_media_cache`, with matching
arguments, results, and errors. `audio_bytes_to_base64` is a shared pure helper.
Explicit source bytes or a `MediaSource` bypass downloading for adapters that
validate media before processing it. `transcribe_audio` defaults to API
transcription; select `use_api=False` for local Whisper.

Async browser operations run on the caller's event loop. Blocking HTTP,
FFmpeg and transcription work runs in workers using plain data; browser objects
never cross threads. Cancellation waits for an already-started worker's bounded
operation to finish before releasing its files or cache lock. It does not stop
an HTTP request, decoder or transcription call immediately. Watch operations
serialize cache use per browser context; call `await clear_media_cache(page)`
on reset. Sync and async caches are separate.

From this checkout: `uv sync --group dev`, then `uv run pytest -q tests`.
Browser tests need `uv run python -m playwright install chromium`; media
regression fixtures require system FFmpeg/FFprobe.

Trusted integrations can pass a validated `MediaSource` as `source=` to sync or
async `extract_media_clip` and `extract_video_frames`, as with `extract_watch_clip`.
These calls decode the local file directly without fetching the URL or copying
the entire source into memory. The integration owns source download limits and
lifetime; clip/attachment bounds and decoder network restrictions still apply.
