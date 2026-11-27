# WebArena-Pro for Harbor

Start with the [Harbor run walkthrough](../docs/source/running-harbor-agents.md)
for a complete single-task example from installation through results and cleanup.

Run existing Harbor MCP-capable agents against WebArena-Pro tasks. Harbor owns
the agent loop, scheduling, concurrency, and retries. Core supplies task data,
readiness, authentication, UI evidence capture, and DAG grading.
This package exports ordinary Harbor
task directories; no custom Harbor agent or environment class is required.

This integration builds on the agent-independent `webarena-pro-mcp` service.
Its session controller and HTTP endpoint live in MCP; this adapter owns task
export, deployment, collection hooks, and reward verification. Harbor supplies
the agents, model calls, prompts, scheduling, and retries. Start with **Docker on
Linux**, Python 3.12, `uv`, and a Docker Compose-capable Harbor version supporting
`verifier.collect` and sidecar artifacts. The reference Harbor revision used for
development is `981a4b246aef3c68b3d1b5aa27cecb703692b1f9`. Do not assume older
versions support sidecar evidence collection. Cloud providers and ARM emulation
require separate qualification.

## Install and build

From this directory in the repository:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-harbor build-runtime
```

`build-runtime` builds wheels for Core, media, MCP, and this package, then builds the
local `webarena-pro-harbor:local` image with Chromium, the pinned Playwright MCP
server, and FFmpeg. It does not push an image. Install Harbor in its own tool
environment, independently of the browser service's MCP SDK:

```bash
uv tool install --with ../webarena-pro-core 'harbor @ git+https://github.com/harbor-framework/harbor.git@981a4b246aef3c68b3d1b5aa27cecb703692b1f9'
```

For a shared deployment, build/tag/push the runtime through your normal image
release process and pass its immutable reference to `export --runtime-image`.
The runtime image must include the same Core/media/MCP/Harbor versions used to
export the tasks. `build-runtime --source-root /path/to/repository` selects the
source explicitly when running from an installed package.

## Export and run

Listing and exporting do not launch websites, reset deployments, or call a model.

```bash
uv run --locked webarena-pro-harbor list --split dev
uv run --locked webarena-pro-harbor export --split dev --task 349 \
  --output ./exported/dev --max-steps 50
```

Omit `--task` to export the split; `--site` filters by primary website. Output
directories must be new; exports never overwrite previous datasets. Task IDs,
intents, accounts, and DAGs come from Core unchanged. Runtime tool instructions
are appended to the original intent.

Set a private evaluator token before invoking Docker Compose through Harbor:

```bash
export WP_HARBOR_EVAL_TOKEN="$(openssl rand -hex 32)"
export WP_HARBOR_JUDGE_MODEL='qwen/qwen3.6-27b'
# Supply WP_HARBOR_JUDGE_API_KEY via your secret manager or shell environment.
```

The default judge uses OpenRouter. Set `WP_HARBOR_JUDGE_BASE_URL` for a different
OpenAI-compatible endpoint; Core's model/provider routing still applies.
Configure the Harbor agent's own model credentials separately, as usual.

For long judge generations behind an HTTP proxy, set `WP_HARBOR_JUDGE_STREAM=1`.
Core assembles the streamed response and scores only after it completes. This
changes the response transport, not the model, prompt, sampling, or retry budget.
Incomplete streams remain evaluation errors. The saved judge request records
the transport so audit replay uses the same mode. The default is non-streaming.

```bash
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/dev -a claude-code -m '<your-model>' \
  -e docker -n 1
```

Use any compatible existing agent name or custom agent import path. The agent
must support task-declared **Streamable HTTP MCP**, text and image observations,
and explicit tool-based submission. A shell-only agent that ignores MCP does
not become a browser agent automatically. Tool names are registered under the
`webarena-pro` MCP server; the agent must finish with `webarena_submit(answer)`.
Its final chat message alone is not a submitted answer.

Increase `-n` only after checking the websites' resource needs: the agent's
`task.toml` resource declaration does not budget the combined website sidecars.
Each trial creates fresh website containers, anonymous image volumes, and a new
browser. Retries start from seed state, not a resumed browser session. Do not
reuse live trial containers to run additional tasks.

## Recorded coding-agent launch scripts

The [`scripts/`](scripts/) directory contains one standalone Bash launcher per
configuration used in the November 10–11, 2026 studies:

| Script | Harbor agent and version | Agent model | Agent credential |
|---|---|---|---|
| [`run_gemini.sh`](scripts/run_gemini.sh) | OpenCode `1.19.5` | `gemini/gemini-3.1-pro-preview` | `GOOGLE_GENERATIVE_AI_API_KEY` (falls back to `GEMINI_API_KEY`) |
| [`run_kimi.sh`](scripts/run_kimi.sh) | OpenCode `1.19.5` | `openrouter/moonshotai/kimi-k3.1-pro` | `OPENROUTER_API_KEY` |
| [`run_codex.sh`](scripts/run_codex.sh) | Codex `0.166.0` | `openrouter/openai/gpt-6.1-sol` | `OPENROUTER_API_KEY` |
| [`run_claude_code.sh`](scripts/run_claude_code.sh) | Claude Code `2.1.318` | `openrouter/anthropic/claude-opus-5.5` | `OPENROUTER_API_KEY` |

These launchers preserve the recorded models, CLI pins, high reasoning effort,
and disabled built-in web search. Gemini and Kimi use **OpenCode**, rather than
their native CLIs. Their inline model registrations preserve the recorded
context/output limits, reasoning settings, and media permissions. The Claude
launcher uses the Kimi-parity study's 32,768-token output cap and media
restrictions. Gemini, Kimi, and Claude disallow `media_watch` and `media_listen`;
Codex retains the standard media profile, including JPEG `media_watch` overview.

Install the pinned Harbor revision and build/export with this package as above.
Load the selected agent credential and `WP_HARBOR_JUDGE_API_KEY` privately, then
configure the evaluator independently of the agent:

```bash
export WP_HARBOR_EVAL_TOKEN="$(openssl rand -hex 32)"
export WP_HARBOR_JUDGE_MODEL='qwen/qwen3.6-27b'
export WP_HARBOR_JUDGE_BASE_URL='https://openrouter.ai/api/v1'
export WP_HARBOR_JUDGE_STREAM=1
# For exports with transcription enabled, also load WP_HARBOR_ASR_API_KEY.
export WP_HARBOR_ASR_BASE_URL='https://openrouter.ai/api/v1'
export WP_HARBOR_ASR_MODEL='openai/whisper-1'
```

Each script takes an existing exported dataset and a fresh job name. From this
directory, run the desired configuration, for example:

```bash
./scripts/run_gemini.sh ./exported/test-media gemini31-test
./scripts/run_kimi.sh ./exported/test-media kimi31-test
./scripts/run_codex.sh ./exported/test-media codex-sol-test
./scripts/run_claude_code.sh ./exported/test-media claude-opus55-test
```

Each invocation runs every task in the supplied dataset. Paths are relative to
the caller's working directory. Defaults are one concurrent Docker trial, one
attempt per task, zero automatic retries, and results under `./jobs/<job-name>`.
Set `N_CONCURRENT`, `JOBS_DIR`, or `HARBOR_BIN` to override those launcher
settings; additional arguments are forwarded to `harbor run`. `--help` prints
usage without credentials or a Harbor installation. Before increasing
concurrency, use the network preflight below with the same value:

```bash
uv run --locked webarena-pro-harbor preflight-networks --concurrency 6 && \
  N_CONCURRENT=6 ./scripts/run_kimi.sh ./exported/test-media kimi31-test-six
```

Task selection, screenshots, action/time budgets, media tools, and images remain
properties of the supplied export. The recorded studies used 50 actions and a
900-second evaluation timeout; Gemini, Kimi, and the Claude parity run used
1,800-second episodes, while the original Codex run used 600 seconds. Export
with the intended settings before launching. These portable commands use public
provider endpoints instead of the original host's private audit proxies, and
do not include study-specific billing collectors, runtime patches, or recovery
orchestration. Reproducing historical results also requires the original
exports and runtime/image revisions.

## Codex and Claude Code examples

Run these commands from `webarena-pro-harbor/` after installing Harbor and
building the runtime image above. Export one Dev task for an initial run:

```bash
uv run --locked webarena-pro-harbor export --split dev --task 349 \
  --output ./exported/agent-smoke --browser-only \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

All examples use the same task, 50-action budget, and 600-second agent budget.
`--browser-only` needs no transcription credentials. To use transcription and
frame extraction, export to a new directory without that flag and configure
`WP_HARBOR_ASR_API_KEY` as described below.

Set credentials in the shell that launches Harbor, or load them from your secret
manager. Agent credentials and the private Core judge have separate settings:

| Purpose | Host environment variables |
|---|---|
| Codex agent on OpenAI | `OPENAI_API_KEY` |
| Claude Code agent on Anthropic | `ANTHROPIC_API_KEY` |
| Gemini CLI agent on Google | `GEMINI_API_KEY` |
| Core judge, for any agent | `WP_HARBOR_JUDGE_API_KEY`, `WP_HARBOR_JUDGE_MODEL`, optional `WP_HARBOR_JUDGE_BASE_URL` |
| Private website evaluator access | `WP_HARBOR_EVAL_TOKEN` |

For example, keep the same OpenRouter judge for every agent/model comparison:

```bash
export WP_HARBOR_EVAL_TOKEN="$(openssl rand -hex 32)"
export WP_HARBOR_JUDGE_MODEL='qwen/qwen3.6-27b'
export WP_HARBOR_JUDGE_BASE_URL='https://openrouter.ai/api/v1'
export WP_HARBOR_JUDGE_STREAM=1
# Load WP_HARBOR_JUDGE_API_KEY and the selected agent's API key privately.
```

Harbor forwards the selected agent's credentials to its container and registers
the task's Streamable HTTP MCP service automatically. Changing `-m` selects the
**agent model**; it does not select the Core judge.

### Codex with OpenAI models

With `OPENAI_API_KEY` set, use `-a codex` and an `openai/` model name:

```bash
# GPT-5.6 Sol, low reasoning effort.
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/agent-smoke -a codex -m openai/gpt-5.6-sol \
  --ak version=0.166.0 --ak reasoning_effort=low --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name codex-gpt56-sol-dev349

# GPT-5, using the same agent version and task budgets.
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/agent-smoke -a codex -m openai/gpt-5 \
  --ak version=0.166.0 --ak reasoning_effort=low --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name codex-gpt5-dev349
```

`--ak version` pins the Codex CLI installed inside the agent container. The
`0.166.0` pin was used for this adapter's Codex qualification runs. Replace `-m`
with another model available to your API project and use a reasoning effort
supported by that model. Model IDs are listed in the official
[OpenAI model catalog](https://developers.openai.com/api/docs/models).

### Claude Code with Anthropic models

With `ANTHROPIC_API_KEY` set, use `-a claude-code` and an `anthropic/` model name:

```bash
# Claude Sonnet 5.5.
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/agent-smoke -a claude-code -m anthropic/claude-sonnet-5-5 \
  --ak version=2.1.318 --ak reasoning_effort=low --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name claude-sonnet55-dev349

# Claude Opus 5.5, using the same agent version and task budgets.
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/agent-smoke -a claude-code -m anthropic/claude-opus-5-5 \
  --ak version=2.1.318 --ak reasoning_effort=low --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name claude-opus55-dev349
```

The Claude Code examples pin CLI version `2.1.318`; these are configuration
examples, not reported benchmark results. Use a model enabled for your Anthropic
account; see the official [Claude model IDs](https://platform.claude.com/docs/en/models/overview)
and [Claude Code model configuration](https://code.claude.com/docs/en/model-config).

### Gemini CLI with Google models

With `GEMINI_API_KEY` set, use `-a gemini-cli` and a `gemini/` model name:

```bash
: "${GEMINI_API_KEY:?Load the Gemini agent API key first}"
harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/agent-smoke -a gemini-cli -m gemini/gemini-2.5-pro \
  --ak version=0.40.0 --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name gemini25-pro-dev349
```

This pins Gemini CLI `0.40.0` and uses the same export and private judge settings
as the other examples. Use a model available to your Google API project. It is
a configuration example, not a qualified benchmark result. Harbor forwards
`GEMINI_API_KEY` to the agent and registers the task's Streamable HTTP MCP server
in Gemini CLI's settings; no manual MCP setup is required.

Omit `--ak reasoning_effort` for Gemini 2.5: the pinned Harbor wrapper rejects
that option for this model family before starting the agent. This is a wrapper
restriction, not a claim that the underlying model cannot reason. The wrapper
accepts supported reasoning-effort values for Gemini 3 models. Its
[Gemini CLI implementation](https://github.com/harbor-framework/harbor/blob/981a4b246aef3c68b3d1b5aa27cecb703692b1f9/src/harbor/agents/installed/gemini_cli.py)
defines model validation, credential forwarding, MCP registration, and exclusion
of `google_web_search` and `web_fetch` when `disable_web_search=true`.

For these agents, `--ak disable_web_search=true` disables their built-in web tools;
the benchmark browser remains accessible through MCP. Use a new `--job-name`
when repeating a command. Results are written under `./jobs/<job-name>/`.
`-n` controls concurrent trials, while `-k` controls attempts per task; neither
changes WebArena-Pro's action budget. Keep the exported tasks, judge settings,
agent versions, and budgets fixed when comparing models.

To run a full split, omit `--task` when exporting (100 Dev or 300 Test tasks):

```bash
uv run --locked webarena-pro-harbor export --split test \
  --output ./exported/test-browser --browser-only \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

Then use `-p ./exported/test-browser` in any command above, give it a new job
name, and choose concurrency with `-n` for your host's website capacity.
The pinned Harbor revision's [agent options and authentication guide](https://github.com/harbor-framework/harbor/blob/981a4b246aef3c68b3d1b5aa27cecb703692b1f9/docs-mintlify/agents/agent-auth-resolution.mdx)
documents provider/model parsing and credential forwarding.

### Check Docker network capacity before a study

Each running trial needs two separate bridge networks: `default` for the agent
and browser, and an `internal: true` `websites` network. Docker's default address
pools can run out on a shared host even when CPU and memory are available. Run
the network preflight **on the deployment host using Harbor's Docker context**,
with the same concurrency as `harbor run -n`, before launching the queue:

```bash
uv run --locked webarena-pro-harbor preflight-networks --concurrency 6 && \
  harbor run --plugin webarena_pro_core.atif_usage:HarborRequestUsage -p ./exported/test-browser -a claude-code -m '<your-model>' \
    -e docker -n 6 --job-name test-network-checked
```

The check temporarily allocates all twelve networks together, then removes only
the exact network IDs it created. It starts no containers, changes no existing
networks, and makes no model calls. Allocation or cleanup failure returns a
nonzero status, so the `&&` guard prevents trials from being consumed. Allocation
has a 120-second deadline (`--timeout` overrides it), followed by at most 30
seconds for cleanup. Interrupted or timed-out requests may leave a probe whose
name/ID is reported for inspection; never delete unrelated networks.

This is a point-in-time check, **not a reservation**. Other studies can consume
capacity afterward; run it again before another batch or after changing
concurrency. The check uses the active Docker CLI context and cannot validate a
different remote host selected only in Harbor. It does not validate host RAM,
website readiness, image availability, or provider connectivity.

If allocation fails, reduce concurrency and rerun the check, or ask the host
administrator to provide enough non-overlapping Docker address pools. Check all
existing Docker subnets and host/VPN routes before choosing a private range; a
daemon-wide pool change requires planning around active studies. Avoid global
network pruning or restarting a shared daemon during experiments. Hard-coding
one subnet per exported task is unsafe when repeated attempts of that task can
run concurrently. This preflight leaves Compose's per-trial network allocation
and the internal websites isolation unchanged.

## Images and reproducibility

Core's current image registry uses mutable `latest` tags by default. For a
reproducible dataset, supply `--image-map images.json` with pinned references:

```json
{
  "acidwave": "webarenapro/acidwave@sha256:<actual-published-digest>"
}
```

Only override sites you need. The manifest records configured image references
and the complete episode configuration hash. Supply actual digests; the exporter
does not resolve tags or claim that a mutable tag is immutable. Website images
currently target `linux/amd64`; the runtime can be built for the host platform.
The browser service reuses the runtime image directly. Each task's
`environment/browser/episode.json` is bind-mounted read-only into that service;
it is not baked into a separate image. Nextcloud similarly reuses its configured
site image, with a read-only PHP JIT configuration and a startup wrapper that
prepares Core's seed-directory ownership before invoking the image's seeded
entrypoint (or the original Nextcloud entrypoint for older compatible images).
No browser or Nextcloud image build is required per task. Harbor still builds
the agent and separate verifier environments. Only required sites are started.

All bind sources are small files inside the individual task's `environment/`
directory; missing sources fail startup rather than creating empty host
directories. Copy the complete task directory to relocate it. Run Harbor on
the Docker daemon's host so Compose can mount those paths. Remote Docker
contexts and cloud providers need their own file-staging validation. Never
share writable browser or Nextcloud seed state across trials; these mounts
contain configuration only and are absent from the agent container.

## Browser and media contract

The agent container can reach the MCP service, but the websites are on a separate
internal Compose network. No host ports, shared Docker socket, database volume,
browser profile, CDP endpoint, or evaluator credentials are mounted into the agent
container. The browser service applies the existing MCP tool and URL restrictions
at dispatch time and serializes all calls, including concurrent requests and
requests from reconnected clients. Public MCP has no grading/reset/control tools.

The same browser is shared by the Playwright and media MCP implementations.
The supervisor uses native async Playwright and Core's autologin and UI evidence
APIs; the media server uses `webarena_pro_media.async_api`. The supervisor captures
UI facts asynchronously and passes serialized evidence to Core's private grading
thread, so browser routing and download capture remain active during grading.

- Browser UI tools provide navigation, snapshots, screenshots, form input,
  clicking, tab management, and the existing allowlisted actions.
  Closing the last tab is rejected so Chromium remains available for grading;
  the agent can navigate that tab or close a tab when another remains open.
- The standard media profile exposes `media_transcribe`, `media_extract_frames`,
  and JPEG-only `media_watch` overview by default. Set `WP_HARBOR_ASR_API_KEY` for transcription, optionally
  `WP_HARBOR_ASR_BASE_URL`; `--transcription-backend disabled` removes transcription.
- `--native-audio` independently enables WAV `media_listen`; `--native-video`
  enables inline MP4 `media_watch` detail/full modes. Either flag selects the
  omni profile. Pass both for synchronized audio/video. Declare only content
  types supported by the agent and model; support is not inferred from the
  Harbor agent's model. JPEG overview needs neither native flag.
- `--browser-only` disables the media tools.

Rebuild the runtime image and re-export tasks after updating the MCP service.
Existing exports are left untouched. The Harbor `serve` and `finalize` commands
delegate to the shared MCP runtime, preserving the existing sidecar entrypoints.

Uploads are not enabled in this initial integration. Arbitrary host paths and
agent-created sandbox files are not automatically shared with the browser.
Downloads are captured privately for grading. Page media access is not recorded
as a user download.

Browser mutations and media processing cost one action. Snapshots, screenshots,
find queries, tab listings, validation/policy rejections, and submission are
free. Explicit stale-reference rejections are free; possible partial actions
still count. Browser mutations return a text snapshot and screenshot together.
Internal observations and grader queries do not cost actions. `--max-steps` accepts 50,
100, or -1. A 50/100 checkpoint is recorded before allowing subsequent actions.
At the final action limit, grading runs in the private finalizer instead of
delaying the last tool response past the agent's MCP timeout.
After action exhaustion the service accepts observations and final submission
until the wall deadline, while rejecting further mutations/media processing.
Harbor's own timeout bounds an agent that does not stop. Episode wall time starts on the first tool
call, excluding agent installation. Agent token/cost limits remain Harbor/agent
settings, not browser-service settings.

## Website startup

Core configures authentication for each trial's internal website URLs. Pipedrive
uses that URL for NextAuth callbacks, and Penpot's HTTP deployment disables Secure
session cookies while retaining its seeded password-login settings. The Penpot
launch wrapper forwards those settings through the image's Supervisor process;
its health check allows three minutes for the bundled database and JVM to warm up.
Nextcloud login accepts Chromium's canonical URL without an explicit default
port, and YT-Lite waits for the authenticated redirect instead of idle video
traffic.

Peppermint waits for both its frontend and login API before the browser service
starts. The exported health probe requires HTTP 200 or 401 from the API's public
`/api/v1/auth/check` route, so a ready frontend cannot consume login retries while
the API is still starting. This override also works with existing pinned site
images. The frontend probe follows Next.js's `HOSTNAME` bind address; the API
probe uses loopback. Both bypass HTTP proxies. Probe requests are bounded to three seconds each; Compose retries every
five seconds after each probe, for at most 138 unsuccessful probes (within the
30-minute setup health budget, including probe time), then reports an unhealthy dependency with the failing component and HTTP status in its health
log. It does not extend the agent's action or wall-time budget.

A setup exception is an unscored infrastructure failure. Retry it as a fresh
trial after addressing the cause, preserving the original attempt and the task,
model, judge, image pins, and action/time budgets. Do not rerun a valid graded
trial merely because its score is low.

## Per-request token usage

The launchers write `<job>/model_requests.json` at job end. Harbor supplies the
input, cached and output counts from each trial's native `agent/trajectory.json`.
A step with `llm_call_count: 1` identifies one inference. Aggregated steps
appear in `coverage_gaps`. HTTP retries absent from the native trajectory have
no individual record. Inspect the native trajectory for the agent's completion.
See the [shared token fields and totals](../README.md#model-request-files).

To rebuild a report from an existing job, run
`uv run --locked webarena-pro-harbor export-usage jobs/my-job`.
When moving a job, include the hidden `.request-usage-<trial-uuid>.json` files.
They preserve the usage of failed trials whose directories Harbor replaces on retry.

## Verification and artifacts

To retain visual traces, add `--record-screenshots` when exporting a **new**
dataset and use a runtime image built with this option's implementation. The
browser service saves the initial view and a screenshot after each completed
action under private `screenshots/`, indexed by `screenshots.jsonl`. This is
independent of `--browser-only` and media tools. It does not add agent actions,
send extra images to the model, or invoke the evaluator. Capture is bounded to
five seconds and the remaining episode time, so it adds latency within the
existing wall-time budget. Errors are recorded as missing images and do not
change action results or grades. Agent-requested screenshots are reused.

The option defaults off to preserve existing experiment settings. It cannot
recover images for historical actions that were never captured. Existing runs,
their scores, and final grading screenshots remain unchanged.

```bash
uv run --locked webarena-pro-harbor export --split test --task 282 \
  --output ./exported/visual-trace --browser-only --record-screenshots \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

After the agent phase, Harbor stops the main service and invokes
`webarena-pro-harbor finalize` **inside the browser sidecar**. That command uses
a private Unix socket to grade the live websites before teardown. The public
HTTP endpoint cannot finalize or retrieve a score.

`export --evaluation-timeout SECONDS` sets the private Core grading deadline
(default 300). For a slower judge endpoint, use a larger value such as 900.
The exported Harbor collection deadline automatically includes this budget,
evidence queries, any in-flight action, and diagnostics. This does not extend
the agent's step or wall-time budget.

Harbor collects `/webarena-evidence` and `/webarena-service` from that sidecar.
The exported `supervise` entrypoint creates the latter private directory before
loading the episode configuration, captures service stdout/stderr, and saves
`status.json` with the actual exit code (and signal, when applicable). Health
checks append failures to `health.jsonl` and record the first successful
readiness check. An exit before readiness produces an explicit ungraded
`setup_error` in `/webarena-service/result.json`, without reward metrics or
fabricated Core/browser evidence. This does not require the stopped service's
`finalize` hook to succeed: the pinned Harbor runner copies sidecar files from
stopped containers before deleting the trial. The original setup exception and
trace locations remain in `stderr.log`; trace source lines/locals are omitted.

Diagnostics redact secret environment values, credential fields, URL userinfo,
and URL queries/fragments before writing or forwarding output. They remain on
the private sidecar filesystem and are never mounted into the agent container.
Rebuild the runtime image and regenerate exports to enable this entrypoint.
Existing low-level `serve` calls retain their previous behavior. Container or
network failures **before the entrypoint runs**, and forced termination that
prevents the wrapper from writing, still require Harbor/Docker host diagnostics;
this wrapper cannot report an exception from a process that never started.

A minimal separate verifier checks the completed Core result and writes `/logs/verifier/reward.json`:

- `reward`: Core partial-credit score.
- `success`: 1 only when the score is exactly 1.
- `score_at_50`, `score_at_100`, or `score_at_unlimited`: available budget scores.

Evidence includes the original configuration, baselines, calls, trajectory,
downloads, terminal and checkpoint DAG results, judge audits, and screenshots
captured for evaluations. Evaluation inputs are saved before Core grading;
`evaluation-state.json` records the deadline, elapsed time, and failure cause
even when grading times out. Missing, erroneous, or malformed terminal evidence
fails verification instead of producing an invented zero reward. Core judge
error/fallback semantics are preserved in the DAG results and audits.

The separate verifier validates a result calculated against the live websites.
Running Harbor regrade repeats that validation; it does **not** rerun the DAG
against a restored database. Full offline re-evaluation requires additional
backend snapshots and is not provided by this version.

## Validation

```bash
uv run --locked pytest -q tests
uv run --locked webarena-pro-mcp install
WP_HARBOR_BROWSER_TESTS=1 uv run --locked pytest -q tests/test_browser.py
uv build
```

Browser tests use local fixtures and the real Playwright/MCP/Core stack, including
both media profiles and external-site startup, without model credentials or
Docker. They need FFmpeg/FFprobe for their generated media fixture.
Native Harbor smoke validation additionally needs
Docker, the built runtime image, and the supported Harbor revision. Refer to the
PR validation record for the deployment paths actually exercised.
