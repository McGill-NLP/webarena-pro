# WebArena-Pro Core ⚙️

> The framework-neutral runtime beneath every WebArena-Pro integration.

`webarena-pro-core` owns the website registry, Docker lifecycle, URL routing,
task configs, reset contracts, evaluator primitives, sync/async autologin and
UI evidence collectors, and the `webarena-pro` CLI. It can operate the benchmark
environments without importing BrowserGym or AgentLab.

The benchmark contains **400 tasks**: **100 dev tasks** and **300 test tasks**.
The website `*.raw.json` files contain only Test tasks. Dev tasks live only
in `config/splits/dev.json`. Each task stores its setup, intent, and evaluation
DAG together, with the DAG under `eval`.
`load_task_configs()` loads Test by default; use `load_task_configs(split="dev")`
to load Dev directly, optionally filtering by primary website.
Every task uses tiered DAG evaluation.

| Capability | What Core provides |
|---|---|
| Environments | Registry and lifecycle for 20 Dockerized websites |
| Tasks | Framework-neutral loading for 400 tasks with tiered DAG evaluations |
| Routing | Shared nginx subdomains or direct host ports |
| State | Per-site reset contracts and worker-isolated namespaces |
| Evaluation | DAG, state, answer, file, URL, HTML, calendar, WebDAV, and LLM checks |
| Integrations | Shared runtime for BrowserGym/AgentLab, MCP, Harbor, and custom integrations |

Website implementations live in [`../websites/`](../websites/).

## Requirements

| Requirement | Purpose |
|---|---|
| Python 3.12+ | Runs the package and CLI |
| Docker | Hosts website and nginx containers |
| [`uv`](https://docs.astral.sh/uv/) | Installs the package and optional feature sets |

Core installs Playwright and the evaluator libraries by default. Live browser
work also needs a browser binary (`python -m playwright install chromium`).
Additional optional dependencies are grouped by capability:

| Extra | Adds |
|---|---|
| `verifier` | Jinja, NumPy, Pillow, YAML, and verifier support |

## Install

From this package directory, create and activate a Python 3.12 environment:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install .
```

Keep this environment active for the `python` and `webarena-pro` commands
below. In a new terminal, return to `webarena-pro-core/` and activate it again.
Install the browser binary and additional packages as needed:

```bash
# Browser binary for autologin and UI evidence collection
python -m playwright install chromium

# Independent Media capture/frame extraction helpers
uv pip install ../webarena-pro-media

# Add local Whisper transcription support
uv pip install "../webarena-pro-media[local]"

# Additional verifier dependencies
uv pip install ".[verifier]"
```

Media is installed separately; see its [package guide](../webarena-pro-media/README.md)
for standalone installation and transcription options.

## 🚀 Quickstart

```bash
# Discover the environment registry.
webarena-pro env list

# Start one site and inspect its URL and container state.
webarena-pro env start nextcloud
webarena-pro env status nextcloud

# Open the environment dashboard.
webarena-pro env dashboard
```

The dashboard is available at `http://dashboard.localhost:8080` by default and
provides start, restart, stop, and connect controls for every registered site.
It connects to Docker when the server starts; importing its configuration
helpers does not require a running Docker daemon.

Common lifecycle commands:

| Goal | Command |
|---|---|
| Pull the published image for a site | `webarena-pro env pull nextcloud` |
| Start selected sites | `webarena-pro env start nextcloud mattermost` |
| Start every site | `webarena-pro env start all` |
| Create authenticated state | `webarena-pro env start nextcloud --login` |
| Recreate one site from its image | `webarena-pro env restart nextcloud` |
| Stop selected sites | `webarena-pro env stop nextcloud mattermost` |
| Stop every site and nginx | `webarena-pro env stop all` |
| Show command help | `webarena-pro env start -h` |

Pulling an image updates the local image tag without changing an existing
container. `env restart` removes and recreates the container, discarding its
mutable state; it is different from a literal `docker restart`. See
[updating website images](../docs/source/reset.md#updating-website-images) for
the upgrade sequence and published release evidence.

> [!TIP]
> Start only the environments needed for your task. This reduces image pulls,
> startup time, memory use, and reset work.

## 🌐 Supported websites

The package currently registers these website IDs:

| Website | Docker image | Direct-mode env var | Direct-mode default |
|---|---|---|---:|
| `acidwave` | `webarenapro/acidwave:latest` | `WP_ACIDWAVE_HOST_PORT` | `9401` |
| `erp-next` | `webarenapro/erp-next:latest` | `WP_ERP_NEXT_HOST_PORT` | `9201` |
| `firefly` | `webarenapro/firefly:latest` | `WP_FIREFLY_HOST_PORT` | `4801` |
| `flight-search` | `webarenapro/flight-search:latest` | `WP_FLIGHT_SEARCH_HOST_PORT` | `3001` |
| `immich` | `webarenapro/immich:latest` | `WP_IMMICH_HOST_PORT` | `5001` |
| `jobportal` | `webarenapro/jobportal:latest` | `WP_JOBPORTAL_HOST_PORT` | `4601` |
| `mattermost` | `webarenapro/mattermost:latest` | `WP_MATTERMOST_HOST_PORT` | `5101` |
| `metabase` | `webarenapro/metabase:latest` | `WP_METABASE_HOST_PORT` | `6101` |
| `minerva-lite` | `webarenapro/minerva-lite:latest` | `WP_MINERVA_LITE_HOST_PORT` | `7001` |
| `mydrive` | `webarenapro/mydrive:latest` | `WP_MYDRIVE_HOST_PORT` | `6001` |
| `nextcloud` | `webarenapro/nextcloud:latest` | `WP_NEXTCLOUD_HOST_PORT` | `3101` |
| `notion` | `webarenapro/notion:latest` | `WP_NOTION_HOST_PORT` | `7301` |
| `password-manager` | `webarenapro/password-manager:latest` | `WP_PASSWORD_MANAGER_HOST_PORT` | `3201` |
| `penpot` | `webarenapro/penpot:latest` | `WP_PENPOT_HOST_PORT` | `9001` |
| `peppermint` | `webarenapro/peppermint:latest` | `WP_PEPPERMINT_HOST_PORT` | `9301` |
| `pipedrive` | `webarenapro/pipedrive:latest` | `WP_PIPEDRIVE_HOST_PORT` | `9101` |
| `thunderbird` | `webarenapro/thunderbird:latest` | `WP_THUNDERBIRD_HOST_PORT` | `5201` |
| `travelmap` | `webarenapro/travelmap:latest` | `WP_TRAVELMAP_HOST_PORT` | `4701` |
| `x-lite` | `webarenapro/x-lite:latest` | `WP_X_LITE_HOST_PORT` | `7101` |
| `yt-lite` | `webarenapro/yt-lite:latest` | `WP_YT_LITE_HOST_PORT` | `7201` |

Peppermint also publishes an API port in direct-port mode:
`WP_PEPPERMINT_API_HOST_PORT`, default `5003`.

## URL modes

Subdomain mode is the default. Websites are exposed through the shared nginx
reverse proxy:

```bash
WP_URL_MODE=subdomain webarena-pro env start nextcloud
```

With the default local settings, this produces URLs like:

```text
http://nextcloud--local.localhost:8080
http://mattermost--local.localhost:8080
```

Use `WP_EXP_HASH` to create a separate namespace for another run:

```bash
WP_EXP_HASH=run42 webarena-pro env start nextcloud
# http://nextcloud--run42.localhost:8080
```

To expose environments from a remote deployment server, bind nginx publicly and
use a wildcard DNS name that resolves to the server:

```bash
# On the deployment server:
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_WEB_SERVER_BIND_HOST=0.0.0.0
export WP_URL_MODE=subdomain
webarena-pro env start all
```

This publishes URLs such as:

```text
http://nextcloud--local.213.0.113.10.sslip.io
http://jobportal--local.213.0.113.10.sslip.io
```

On a separate agent machine, set the same URL settings before running tasks so
task URLs point at the deployment server instead of localhost:

```bash
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_URL_MODE=subdomain
```

If the proxy is not on port 80, include the port in `WP_WEB_SERVER_URL`, for
example `http://213.0.113.10.sslip.io:8080`.

For old direct-host-port behavior:

```bash
WP_URL_MODE=port webarena-pro env start nextcloud
```

Override a direct-mode port with the site-specific env var:

```bash
WP_URL_MODE=port WP_NEXTCLOUD_HOST_PORT=3999 webarena-pro env start nextcloud
```

If your browser or OS does not resolve `*.localhost`, use a wildcard loopback
domain such as `127.0.0.1.sslip.io`, or point your own wildcard DNS at
localhost.

## Auto-login

Core bundles [autologin helpers](docs/autologin.md) with sync and async APIs.
Playwright is installed with Core and loaded only when browser work is requested.
Install the Chromium binary before using these flags.

Use `webarena-pro env start <site> --login` for selected sites or
`webarena-pro env start all --auto-login` for all supported default logins.
See the [CLI reference](../docs/source/cli.md#environment-commands) for browser,
authentication-state directory, and retry options.

Mattermost login waits for the landing page's "View in Browser" control to render,
including when plugins and Calls are enabled, before opening the login form.

Peppermint login waits for a successful authentication response and the redirect
away from the login page before verification, allowing the client to store its
token. Failed authentication responses enter the normal login retry flow.

From Python:

```python
from webarena_pro_core.autologin.sync_api import save_storage_state, ui_login

# page is any synchronous Playwright Page.
ui_login("x-lite", page, username="techvalueinvestor")

save_storage_state(
    "jobportal",
    ".auth/jobportal_alice.json",
    username="alice_seeker",
)
```

## Task configs

Raw task files live in
[`src/webarena_pro_core/config/*.raw.json`](src/webarena_pro_core/config/).
Each file is a JSON array of task objects.

Load task configs without importing BrowserGym:

```python
from webarena_pro_core.task import WebArenaProTaskConfig, load_task_configs

configs = load_task_configs(["nextcloud", "mattermost"])

demo = WebArenaProTaskConfig.from_raw_task(
    raw_task={
        "task_id": "demo",
        "intent": "Open Nextcloud",
        "sites": ["nextcloud"],
    },
    container_name="webarena-pro-demo-0",
)
```

See the [task configuration guide](src/webarena_pro_core/config/README.md) for
the task schema.

## State reset

The reset API is shared by BrowserGym and any other integration that
needs to return a website to a known seed state.

```python
from webarena_pro_core.state_reset import reset_site, restore_site_state

reset_site("nextcloud")
restore_site_state("travelmap")
```

The reset backend is selected automatically by default. Some websites use a
fast in-place reset endpoint or packaged restore script; others are reset by
recreating the container.

Useful reset variables:

| Variable | Purpose |
|---|---|
| `WP_RESET_BACKEND` | Select `auto`, `container`, `state`, or `none`. |
| `WP_RESET_CONTAINER_PER_TASK` | Enable per-task reset in BrowserGym (default); `0`, `false`, or `no` disables it. The selected backend still comes from `WP_RESET_BACKEND`. |
| `WP_<SITE>_RESET_TOKEN` | Site-specific reset token for reset endpoints. |
| `WP_RESET_TOKEN` | Shared fallback reset token. |

See the [reset documentation](../docs/source/reset.md) for the per-site reset
matrix and backend details.

## Playwright media tools

Media helpers live in the independent [media package](../webarena-pro-media/README.md),
with `sync_api` and `async_api` modules. The following example uses a synchronous page.

```python
from webarena_pro_media.sync_api import (
    extract_audio,
    extract_video_frames,
    transcribe_audio,
    transcribe_media,
)

audio = extract_audio(page, duration=5)
transcript = transcribe_audio(audio)

# Protected URLs can reuse the page's authenticated browser context.
transcript = transcribe_media(media_url, page=page, start_seconds=30, end_seconds=60)
frames = extract_video_frames(media_url, page=page, n_frames=5)
```

See the [media tools documentation](../docs/source/media.md) for supported
inputs and installation details.

## Evaluators

Core includes reusable evaluator primitives under `webarena_pro_core.eval`,
including DAG evaluation, exact/substring/fuzzy answer matching, URL matching,
downloaded-file checks, HTML checks, calendar/WebDAV checks, and LLM judging.

Every active benchmark task uses a tiered DAG evaluator. See the
[DAG evaluator documentation](../docs/source/evaluators.md) for how DAG
evaluation is represented and executed.

## Runner delegation

Core does not execute benchmark studies. When `webarena-pro-bgym` is installed
or present as a sibling checkout, `webarena-pro run ...` delegates to its
BrowserGym/AgentLab runner:

```bash
webarena-pro run -h
```

See the [BrowserGym + AgentLab guide](../webarena-pro-bgym/README.md) for study,
parallelism, dashboard, and relaunch commands.

## Docker platform

On ARM Macs, WebArena-Pro retries missing website images with `linux/amd64`
when Docker reports no native ARM image manifest.

Force a platform:

```bash
WP_DOCKER_PLATFORM=linux/amd64 webarena-pro env start jobportal
```

Disable automatic fallback:

```bash
WP_DOCKER_FALLBACK_PLATFORM= webarena-pro env start jobportal
```

## Development

Run core tests from the package directory:

```bash
uv run pytest -q tests
```

Or from the monorepo root:

```bash
cd webarena-pro-core
uv run pytest -q tests
```

## Package migration

Autologin and UI evidence collection are bundled in Core. Replace imports from
`webarena_pro_autologin` with `webarena_pro_core.autologin`, and imports from
`webarena_pro_ui_evidence` with `webarena_pro_core.ui_evidence`; both retain
`sync_api` and `async_api` modules. Remove the standalone helper dependencies
and depend on `webarena-pro-core` directly (plus `verifier` where needed).
Playwright and evaluator libraries are included by default; remove the former
`browser` and `eval` extra selections. The older `webarena_pro_core.auto_login`
path is not restored.

Core and Media have no package dependency on each other. Install Media directly
when needed and use
`webarena_pro_media.sync_api` / `.async_api`. Standalone Media selects API
transcription dependencies with `[transcription]`; local Whisper uses `[local]`.
URL helpers and
`WEBSITE_LOGIN_PATHS` remain in `webarena_pro_core.website_metadata`.

Task loading and backend/saved-evidence evaluation do not initialize Playwright.
Browser collection is isolated from the data-only evaluators within Core, while
both paths ship with their required dependencies.


### Captured UI evaluation evidence

Core evaluators consume versioned UI facts instead of live browser pages.
The bundled `webarena_pro_core.ui_evidence` sync/async collectors preserve selector,
visibility, and text semantics; Core retains all grading predicates. BrowserGym
collects privately at evaluation time and persists the `ui_evidence`
result field. `EvalContext(page=...)` callers must migrate to `ui_evidence`.
See [browser evidence and replay](../docs/source/evaluators.md#browser-evidence-boundary)
for the schema, limits, failure semantics, and saved-evaluation migration.
