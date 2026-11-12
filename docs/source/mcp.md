# Browser and media MCP runtime

For a complete session with a concrete client, follow
[Run an external agent through MCP](running-mcp-agents.md).

`webarena-pro-mcp` supplies an agent-independent browser/media service. Agents
run in Harbor or another application, which owns model calls, prompts, memory,
scheduling, retries, and agent checkpoints. The service supplies controlled
browser tools, page-media tools, and a private Core evaluation bridge.

The orchestrator starts and resets the task websites, then supplies a private
session configuration containing the unchanged Core task and website URLs.
Each service instance owns one browser session and a new evidence directory.
It waits for site readiness and logs in, while website teardown stays with the
orchestrator.

```bash
cd webarena-pro-mcp
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-mcp install
uv run --locked webarena-pro-mcp serve \
  --config ./session.json --directory ./evidence/task-349 \
  --socket /tmp/webarena-task-349.sock --port 8000
```

The external agent connects to `http://127.0.0.1:8000/mcp` through Streamable
HTTP MCP and submits its answer with `webarena_submit(answer)`. The service
binds to loopback by default; container deployments can bind to their private
network. Access must be restricted to the owning client because the service
does not implement HTTP authentication.

After stopping the agent, the orchestrator runs the private finalizer before
tearing down the browser and websites:

```bash
uv run --locked webarena-pro-mcp finalize \
  --socket /tmp/webarena-task-349.sock --timeout 360
```

The finalizer uses a private Unix socket. Evaluation details, scores, credentials,
raw CDP, and backend/reset controls are outside the public MCP interface.

## Runtime ownership

The HTTP service delegates to a serialized session controller. It connects to
pinned Microsoft Playwright MCP and the selected WebArena media MCP server over
stdio. Both servers share the Chromium session owned by a private supervisor.
The supervisor manages async Playwright, Core autologin, navigation guards,
download listeners, and browser cleanup.

Private capture uses a fresh CDP observer with `no_defaults=True` to resolve
the exact selected target, document loader and URL, even when the owning
client's page inventory is stale. It disconnects after capture without closing
Chromium or changing browser settings. A closed or changed target remains an
explicit error; another tab with the same URL is never substituted.

Core's async UI-evidence collector reads that verified tab. Captured facts are
bound to the evaluation step and URL, then passed to Core's evaluator on a
dedicated thread. Browser routing and downloads remain responsive during
blocking backend/judge calls. Saved evaluation inputs and results stay private.

Python integrations can use `webarena_pro_mcp.session.open_session()` and
`webarena_pro_mcp.server.make_app()`. The
[Harbor integration](harbor.md) uses
this runtime for its browser sidecar while retaining task export, Compose setup,
agent execution, collection, and verification.

## Tools and budgets

Browser tools expose observed UI interactions, screenshots, snapshots, and tabs.
Canvas interactions use `browser_mouse_click_xy`, `browser_mouse_drag_xy`,
`browser_mouse_move_xy`, `browser_mouse_down`, and `browser_mouse_up`, with
nonnegative viewport CSS coordinates read from a `scale: "css"` screenshot.
Element actions still require observed references. Control/Meta grouping,
ungrouping, cut, copy, and paste are permitted editing shortcuts.
Clipboard API permissions are granted only to configured task origins. Their
exact HTTP origins are treated as secure contexts, enabling canvas copy/paste
on container hostnames as well as localhost; other origins receive no exception.
The pinned full Chromium build runs in new headless mode to support these
scoped origin exceptions. The normal runtime installer includes this browser.
Arbitrary JavaScript, shell/filesystem, direct HTTP, storage controls, and
page-provided WebMCP tools are unavailable. Origin, redirect, popup, and private
endpoint checks remain active for the browser session.

The `standard` media profile exposes transcription, frame extraction, and JPEG
watch overview. Explicit `omni` configuration independently enables WAV listening
with `audio: true` and MP4 watching with `video: true`. Declare the content types
the client supports. Model/provider selection belongs to
the external agent. Browser-only sessions disable media. Transcription uses its
own credentials or explicitly selected local processing.

Browser mutations and media processing count as actions. Snapshots, screenshots,
find queries, tab listings, rejected validation/policy calls, and final submission
do not. Explicit stale-reference rejections are free; uncertain partial actions
still count. A browser mutation returns both a snapshot and screenshot.
Observations and submission remain available after the last allowed action,
within the wall deadline. Internal capture and grading do not count.

Every tool accepts optional `webarena_rationale`, a brief stated explanation
recorded as `agent_info.think` for the shared judge and removed before browser
or media dispatch. Missing rationale stays absent. Per-call URLs come from
validated active-tab state; a retained URL is labeled if capture is unavailable.
The service enforces action limits, wall time, and per-tool deadlines; the agent
owns token/cost/model-turn limits. Concurrent requests and reconnections share
one counter. Core records applicable 50/100 cutoffs and terminal grades.
Uncertain execution or unavailable grading is an infrastructure failure.

The former standalone `run` command, built-in agents, study queue, and agent
checkpoint/replay implementation are removed. Existing study artifacts remain
historical records; run new trials through an external orchestrator.

See the [package guide](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-mcp/README.md)
for configuration, installation, media limits, artifacts, and validation.
