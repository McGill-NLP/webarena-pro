# WebArena Pro MCP

Start with the [external MCP agent walkthrough](../docs/source/running-mcp-agents.md)
for website setup, a complete session configuration, a Claude Code client, and
private finalization.

`webarena-pro-mcp` exposes browser and media tools for external MCP clients.
It owns the browser session, tool restrictions, media connections, and private
Core evaluation bridge. Develop agents in Harbor or another application: model
selection, prompts, conversation history, model calls, scheduling, retries, and
agent checkpoints belong to that application.

Core supplies task data, async autologin, UI evidence collection, and grading.
The independent Media package supplies audio/video processing. There is no
BrowserGym dependency.

## Install

Use Linux or macOS, Python 3.12–3.13, Node.js 20+, npm, and `uv`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-mcp install
```

Installation uses the bundled lockfile for `@playwright/mcp@0.0.84` and Python
Playwright `1.64.1` Chromium. On Linux, install browser system dependencies with
`uv run --locked python -m playwright install --with-deps chromium`.
Media uses FFmpeg/FFprobe on PATH or the included `static-ffmpeg` binaries.

## Start a session for an external agent

The orchestrator starts and resets the task websites and supplies their URLs.
The service waits for readiness and performs login; it does not reset or remove
these externally owned websites. Each session gets a fresh browser and a new
private evidence directory. Run separate service instances for concurrent trials.

Create a private configuration from an unchanged Core task. For example, after
configuring and starting the selected task's websites:

```python
import json
from pathlib import Path

from webarena_pro_core.task import load_task_configs
from webarena_pro_core.website_metadata import deployed_website_urls

selected = next(task for task in load_task_configs(split="dev") if task.task_id == "349")
config = {
    "schema_version": 1,
    "task": selected.raw_task,
    "urls": deployed_website_urls(selected.sites),
    "max_steps": 50,
    "wall_seconds": 1800,
    "setup_timeout": 1800,
    "tool_timeout": 60,
    "evaluation_timeout": 300,
    "media": {"enabled": True, "profile": "standard", "transcription": "disabled"},
}
path = Path("session.json")
path.write_text(json.dumps(config))
path.chmod(0o600)
```

Keep the full configuration and evidence directory private: the task contains
its evaluation DAG. Give the agent the task intent and the MCP endpoint.

```bash
uv run --locked webarena-pro-mcp serve \
  --config ./session.json --directory ./evidence/task-349 \
  --socket /tmp/webarena-task-349.sock --port 8000
```

Connect an external MCP client to `http://127.0.0.1:8000/mcp` using Streamable
HTTP. The service exposes `/health` for readiness. The default bind address is
loopback; an orchestrator can use `--host 0.0.0.0` inside a private container
network. The HTTP service has no built-in authentication; network access must
be restricted to the owning trial's client. Keep the raw Chromium endpoint and
website backend network private.

The client discovers browser/media tools and ends the episode with
`webarena_submit(answer)`. A final chat message alone does not submit an answer.
Submission closes public actions and does not reveal a score.

After stopping the agent, the orchestrator invokes the private grading hook
while the browser and websites are still running:

```bash
uv run --locked webarena-pro-mcp finalize \
  --socket /tmp/webarena-task-349.sock --timeout 360
```

This uses a filesystem-protected Unix socket. The public MCP endpoint has no
evaluate, reset, finalize, or result-reading tool. Collect `result.json` and the
other private artifacts before stopping the service and tearing down websites.
A missing or erroneous grade is an infrastructure failure, not a measured zero.

The companion [Harbor adapter](../webarena-pro-harbor/README.md)
exports tasks, configures sidecars, launches Harbor's own agents, invokes private
finalization, and validates the saved result. Other orchestrators can use the
same HTTP endpoint and lifecycle contract.

## Runtime architecture

- `session.py`: one serialized session, public tool dispatch, submission,
  action/wall budgets, and private evaluation finalization. `open_session()`
  provides an async context manager for Python integrations.
- `server.py`: Streamable HTTP MCP, health endpoint, and private Unix control
  socket. `make_app()` lets an integration host the same service.
- `mcp_client.py`: internal stdio connections to Microsoft Playwright MCP and
  the selected WebArena media MCP server; validation happens at dispatch.
- `supervisor.py`: a private process owning async Playwright, login, navigation
  guards, downloads, and browser cleanup. Both MCP servers share its Chromium
  session through private CDP connections.
- `browser_identity.py`: private CDP target/document identity shared by media
  discovery and evaluation, independent of each client’s tab-list ordering.
- `observations.py`, `evaluation.py`: active-tab parsing and the Core grading
  bridge. Core's async collector reads the selected page; serialized facts go
  to a dedicated grading thread while browser listeners remain responsive.
- `media_server.py`, `media_policy.py`, `tool_policy.py`: page media processing,
  capability limits, tool schemas, origin and argument restrictions.
- `artifacts.py`, `runtime.py`, `process_guard.py`: private records, pinned
  runtime installation, and cleanup of owned MCP subprocesses.

The runtime does not implement an agent or decide which tool to call. External
agents own provider-specific requests and media encoding for their model API.

During browser setup, the supervisor waits up to 30 seconds for Chromium to
publish a valid `DevToolsActivePort` file. Playwright's browser connection can
be ready before this file exists. An unavailable endpoint produces an explicit
startup timeout and follows the normal session cleanup path.

Media discovery and evaluation verify the selected Chromium target, document
loader and URL before and after capture. Navigation races trigger at most three
recaptures within the existing operation timeout; an unavailable or persistently
changing target remains an explicit error. A fixed private runtime probe reads
CDP metadata only. Code execution tools remain unavailable to agents.

Private evaluation opens a fresh CDP observer for each capture, so stale page
bookkeeping in the browser-owning client cannot hide a still-live target. The
observer attaches with `no_defaults=True`, preserves the existing browser
settings, and disconnects after capture without closing Chromium. It requires
the exact target, loader and URL; matching URLs or tab indices are never used
as substitutes. Login, navigation guards and download listeners remain owned
by the supervisor's original client.

Automatic media inventory treats verified blank tabs and Chromium network-error
pages as having no media, so a download or blocked redirect does not by itself
abort the episode. Browser errors carry a recovery hint; the agent can navigate
back or to a configured task website. Allowed-origin non-HTML and 404 documents
can also have an empty inventory. JSON response navigation remains blocked by
the existing response guard. External URLs, private endpoints and arbitrary
internal schemes remain prohibited. Inventory policy failures retain a sanitized
stage and URL category, without including URL credentials or query strings.

## Browser and media tools

Browser tools include snapshots, screenshots, navigation, form input, clicks,
tabs, dialogs, and bounded waits. Element targets must be observed references.
Canvas editors such as Penpot can also use `browser_mouse_click_xy`,
`browser_mouse_drag_xy`, `browser_mouse_move_xy`, `browser_mouse_down`, and
`browser_mouse_up`. Coordinates are nonnegative CSS pixels relative to the
viewport; use a screenshot with `scale: "css"` to locate drawing positions.
Coordinate clicks accept one to three clicks and at most 1000 ms between mouse
down and up. Control/Meta grouping, ungrouping, cut, copy, and paste shortcuts
are available alongside selection and undo/redo.
The browser grants Clipboard API read/write permissions only to the configured
task origins. Those exact HTTP origins are treated as secure contexts so canvas
copy/paste also works at container hostnames such as `http://penpot:9001`.
Sessions use the pinned full Chromium build in new headless mode, which honors
these scoped origin exceptions; `webarena-pro-mcp install` already installs it.
Unconfigured origins receive neither exception; normal URL guards remain active.
Arbitrary JavaScript, direct HTTP clients, shell/filesystem tools, browser
storage controls, and page-provided WebMCP tools are not exposed. The last tab
cannot be closed because the live browser is needed for grading.

Browser requests are restricted to the configured task origins. Normal website
API traffic remains possible; private evaluator/reset paths and direct API
navigation are blocked. Redirect chains and popups are checked. Downloads are
captured privately across tabs. Generic HTTP sessions do not stage uploads;
local integration code must explicitly configure permitted upload paths.
Application document names may contain a literal percent encoded as `%25`, such
as ERPNext Quality Goal names. Raw malformed escapes and invalid UTF-8 are
rejected; bounded nested decoding still checks encoded traversal/separators
against private endpoints and API navigation restrictions.
Percent followed by two hex digits remains subject to nested decoding: for
example, an identifier containing encoded literal `%FF` (`%25FF`) is rejected
because its nested interpretation is invalid UTF-8. Such ambiguous names are
not exempted from the URL policy.

| Profile | Media tools |
|---|---|
| `standard` (default) | `media_transcribe`, `media_extract_frames`, JPEG-only `media_watch` overview |
| `omni` | Standard tools plus `media_listen` when `audio: true`, and MP4 watch modes when `video: true` |

Set `media.enabled` to `false` for browser-only sessions. Select `profile: "omni"`
and independently declare `audio: true` for WAV input and/or `video: true` for
inline MP4 input. The caller declares compatible client capabilities; the MCP
package does not select or inspect an agent model. Overview always returns
sampled JPEGs without audio. Native video can include synchronized audio only
when both capabilities are enabled. The external agent must support the
selected content types.

Media tools accept references discovered on the current page. Fetches validate
origins and redirects before sending browser cookies. HTTP and blob sources
stream into private, hashed local files passed directly to the Media helpers; decoding cannot fetch secondary network URLs. Media
fetches are separate from the download evidence used for grading.

Remote transcription uses `WEBARENA_PRO_ASR_API_KEY` and optional
`WEBARENA_PRO_ASR_BASE_URL`. Set `media.transcription` to `local` with
`webarena-pro-media[local]` installed, or `disabled` to remove the transcription
tool. This tool's OpenAI client is retained; no agent provider client remains.

Sources are limited to 512 MiB; retained source/derived-file storage is pruned
at eight sources or 1 GiB, including derived variants for the current source.
This bound excludes private audit records and persisted returned attachments.
Failed or canceled downloads remove partial files.
Attachments remain limited to 8 MiB. `media_extract_frames` and `media_watch`
overview can survey the whole source in one call, with up to 120 requested
frames. Overview also applies a 131,072-token planning allowance and samples
at most one frame per 30 seconds; sampling can miss intervening events.

When either tool returns frames through the public MCP endpoint, read the
metadata (including timestamps) from the first `content` block as JSON.
The JPEGs follow as image blocks. These replies omit `structuredContent`
so clients that prefer that field receive the images together with the metadata.

Omit `end_seconds` (or pass `null`) for the full source in transcription,
frame extraction, overview, or full watch mode. Native WAV listening and detail
watch default to 30 seconds from the selected start. Listening is limited to
60 seconds per attachment. Transcription accepts up to one hour per call and
internally processes contiguous WAV chunks of at most 60 seconds, preserving
per-chunk audit records and returning a complete transcript only after every
chunk succeeds. Native MP4 modes use the media token and attachment limits
rather than an arbitrary 60-second source interval limit.

Transcription has a 900-second overall timeout, configurable with
`media.transcription_timeout`. Other media calls, source downloads, and individual
transcription API requests use `media.timeout` (180 seconds by default). Every
call is also bounded by the remaining session wall time; expensive processing
may require a shorter interval or a larger configured timeout. Harbor exports
include the transcription timeout in the collection budget. Live streams,
playlists, MediaSource, arbitrary media URLs, and cross-origin blobs are unsupported.

## Budgets, evidence, and migration

Browser mutations and media processing each cost one action. Snapshots,
screenshots, find queries, tab listings, and `webarena_submit` are free.
Validation/policy failures and the pinned browser's explicit stale-reference
rejection do not consume actions; other errors after dispatch conservatively
count because an action may have partially executed. Each browser mutation
returns a text snapshot and a screenshot in the same response. An unavailable
screenshot is labeled and can be retried with a free screenshot call.

After the last action, observations and final submission remain available until
the wall deadline. All calls share the wall budget and serialization lock,
including rejected calls; reconnecting does not reset either budget. `max_steps`
accepts a positive integer or `-1`; wall time starts on the first public call.
Token/cost/model-turn limits remain the external agent's responsibility. This
replaces the v1.0.0-rc.1 policy of charging every tool call; record the runtime
version when comparing scores.

Every public tool accepts optional `webarena_rationale` (a string of at most
10,000 characters). For example, add
`"webarena_rationale": "Save the completed form"` to a click's arguments.
The service validates and removes this metadata before browser/media dispatch,
then records it as `agent_info.think` for the shared Tier-2 judge. Omission
means no stated rationale is available; the service never invents one.
Trajectory URLs come from validated browser tab state, including on screenshot,
media and submit entries. If that capture fails, the previous validated URL is
retained and labeled `url_source: "retained"`. Each entry includes a sequential
`call`, its action-budget `step`, and whether the call was `counted`.

Core records 50/100 cutoffs when applicable. Intermediate grades finish before
subsequent actions; terminal grading uses the private finalizer, outside the
last public tool response. A final answer submitted at a previously graded cutoff triggers a fresh terminal
grade with that answer at the same action count. Free observations alone do not
rerun a completed cutoff. Finalization is idempotent. Unknown in-flight tool
outcomes fail the session; the orchestrator owns retry policy and fresh trials.

Private artifacts include `provenance.json`, `initial.json`,
`mcp_servers.json`, `calls.jsonl`, `trajectory.jsonl`, baselines, downloads,
media attachments and transcription audits, evaluation inputs, UI evidence,
DAG results, screenshots, `evaluation-state.json`, `diagnostics.json`, and
`result.json`. Agent prompts, provider requests, token usage, and agent
checkpoints are recorded by the external runner.

The former `webarena-pro-mcp run` / `list` commands, built-in Chat Completions
and Gemini agents, worker queue, and agent checkpoint/replay implementation
have been removed. Existing standalone studies are historical artifacts and
cannot be resumed by this service. Use Core to select tasks and Harbor or
another runner to execute agents. Rebuild runtime images when upgrading.

## Validation

```bash
WP_MCP_BROWSER_TESTS=1 uv run --locked pytest -q tests
uv build
```

Tests use scripted MCP clients, real Chromium, both media profiles, HTTP and
stdio transports, and a local transcription endpoint. They cover tool guards,
private evidence, budgets, isolated sessions, cleanup, typed media, and Core
grading without agent implementations or paid model calls.
