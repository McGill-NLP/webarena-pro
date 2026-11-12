# Run agents with Harbor

This walkthrough runs Dev task `349` (flight-search) with an existing Harbor
agent, then locates the Core grade and browser trace. Harbor provisions fresh
websites, connects the agent to MCP, and grades the live state before teardown.
For the adapter's full contract, see [Harbor integration](harbor.md) and the
[package reference](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md).

## 1. Install on a Linux Docker host

Use Python 3.12, `uv`, Git, and a working Docker daemon with Docker Compose.
Website images target `linux/amd64`; ARM emulation and cloud environments need
separate validation. Allow capacity for the browser, agent, and website
containers together. The agent's resource declaration does not include all
website sidecars.

In a shell on that host:

```bash
git clone https://github.com/McGill-NLP/webarena-pro.git
cd webarena-pro/webarena-pro-harbor
uv sync --python 3.12 --locked --group dev
uv tool install 'harbor @ git+https://github.com/harbor-framework/harbor.git@981a4b246aef3c68b3d1b5aa27cecb703692b1f9'
harbor --version
docker info
docker compose version
```

Install Harbor separately from the package environment: its MCP dependencies
are independent of the browser service's. The pinned revision supports the
sidecar artifact collection and `verifier.collect` hooks this adapter requires.
If `harbor` is absent from `PATH`, run `uv tool update-shell` and start a new
shell. Run all remaining commands from `webarena-pro-harbor/`.

Build the runtime from this checkout:

```bash
uv run --locked webarena-pro-harbor build-runtime
```

The resulting local image is `webarena-pro-harbor:local`, containing Core,
Media, MCP, the Harbor adapter, Chromium, and FFmpeg. Rebuild it after updating
these packages and export a new dataset from the same checkout.

## 2. Configure agent and evaluator credentials

Load these secrets into the shell that will run Harbor using your secret
manager or private environment. Do not write them into exported task files.

| Variable | Used by |
|---|---|
| `ANTHROPIC_API_KEY` | The Claude Code agent in this walkthrough |
| `WP_HARBOR_JUDGE_API_KEY` | Core's private OpenRouter judge |
| `WP_HARBOR_EVAL_TOKEN` | Private website evaluator endpoints |

After loading the two API keys, set the remaining configuration:

```bash
: "${ANTHROPIC_API_KEY:?Load the agent API key first}"
: "${WP_HARBOR_JUDGE_API_KEY:?Load the OpenRouter judge API key first}"
export WP_HARBOR_EVAL_TOKEN="$(openssl rand -hex 32)"
export WP_HARBOR_JUDGE_MODEL='qwen/qwen3.6-27b'
export WP_HARBOR_JUDGE_BASE_URL='https://openrouter.ai/api/v1'
```

The agent model and the judge are separate choices. The example task needs a
judge even when media is disabled. The adapter passes judge credentials to the
private browser/evaluator service, not to the agent. For a streaming judge
endpoint, `WP_HARBOR_JUDGE_STREAM=1` changes response transport without changing
the scoring policy; see the package reference for provider routing.

## 3. Export one task

Preview the selected task, then export it to a new directory:

```bash
uv run --locked webarena-pro-harbor list --split dev --task 349
uv run --locked webarena-pro-harbor export --split dev --task 349 \
  --output ./exported/dev349-browser --browser-only \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

The list contains task `349`, site `flight-search`, and its original intent.
The export reports `Exported 1 tasks` and writes a manifest and a native Harbor
task directory with `instruction.md`, `task.toml`, Compose services, and verifier
files. Exporting does not start websites or call a model. Existing output
directories are rejected; choose a new name for another export.

The browser and Nextcloud sidecars reuse their configured images across tasks.
Per-task episode configuration and Nextcloud startup/PHP settings are mounted
read-only from that task's `environment/` directory. Keep those files with the
task when copying an export, and run Harbor on the Docker daemon's host so the
relative bind paths are available. The agent receives none of these mounts.

`--browser-only` avoids transcription credentials for this first run. The
50-action budget includes observations, rejected public calls, and submission.
The 600-second episode timer starts with the first public tool call; the
900-second private grading timeout is separate. Harbor also imposes its own
agent deadline. A final chat response alone is not a submission: the agent must
call `webarena_submit(answer)` and reserve one action for it.

## 4. Run a Claude Code agent

This example uses the CLI version and model configuration documented by the
adapter. Select a model enabled for your Anthropic account; keep the full model
ID and agent version in the run record.

```bash
harbor run -p ./exported/dev349-browser \
  -a claude-code -m anthropic/claude-sonnet-5-5 \
  --ak version=2.1.318 --ak reasoning_effort=low \
  --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name claude-dev349
```

Harbor installs the pinned agent, registers the task's Streamable HTTP MCP
server, and forwards the agent API key. The adapter supplies the original task
intent and browser instructions. The agent accesses the websites through the
browser service. Built-in web search is disabled in this example.

`-n 1` allows one concurrent trial; `-k 1` requests one attempt. Use a new job
name for a fresh run. Other supported configurations, including Codex with
OpenAI models, are in the package's
[agent examples](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#codex-and-claude-code-examples).

### Use Gemini CLI instead

Keep the exported task and `WP_HARBOR_*` evaluator settings from the preceding
steps. Load `GEMINI_API_KEY` for the agent instead of `ANTHROPIC_API_KEY`, then run:

```bash
: "${GEMINI_API_KEY:?Load the Gemini agent API key first}"
harbor run -p ./exported/dev349-browser \
  -a gemini-cli -m gemini/gemini-2.5-pro \
  --ak version=0.40.0 --ak disable_web_search=true \
  -e docker -n 1 -k 1 -o ./jobs --job-name gemini-dev349
```

This configuration example pins Gemini CLI `0.40.0`; it is not a qualified
benchmark result. Choose a model enabled for your Google API project. Harbor
passes the API key and registers the exported Streamable HTTP MCP service
automatically. `disable_web_search=true` excludes Gemini's built-in search and
web-fetch tools while preserving MCP access.

Do not add `--ak reasoning_effort` for Gemini 2.5: the supported Harbor wrapper
rejects that option for the 2.5 family. See its pinned
[Gemini CLI implementation](https://github.com/harbor-framework/harbor/blob/981a4b246aef3c68b3d1b5aa27cecb703692b1f9/src/harbor/agents/installed/gemini_cli.py)
for the validation and MCP settings. Inspect `./jobs/gemini-dev349/` using the
same steps below, replacing the Claude job directory with the Gemini directory.

## 5. Inspect the outcome

The job directory is `./jobs/claude-dev349/`. For each trial, inspect:

| Path relative to the trial directory | Contents |
|---|---|
| `result.json` | Harbor trial status, exceptions, and verifier rewards |
| `agent/` | Agent logs and available trajectory/provider records |
| `verifier/reward.json` | Core partial credit, success, and available cutoff scores |
| `artifacts/manifest.json` | Collected artifact sources and services |
| `artifacts/webarena-evidence/` | Private Core result, calls, trajectory, evaluation inputs, and diagnostics |

From `webarena-pro-harbor/`, list the trial outcomes without exposing the private
evidence to an agent:

```bash
uv run --locked python - <<'PY'
import json
from pathlib import Path

for path in sorted(Path("jobs/claude-dev349").glob("*/result.json")):
    result = json.loads(path.read_text())
    print(path.parent.name)
    print("exception:", result.get("exception_info"))
    print("rewards:", (result.get("verifier_result") or {}).get("rewards"))
PY
```

A completed trial has verifier rewards: `reward` is partial credit and `success`
is `1` only for full credit. A low score can be a valid agent outcome. Missing
or malformed terminal evidence fails verification; diagnose the trial exception
and `evaluation-state.json` instead of interpreting missing rewards as zero.
Judge audits also record per-node judge failures or fallback behavior.

Harbor invokes private finalization inside the browser sidecar while the sites
are still live, collects evidence, and tears down its trial resources. Let that
phase complete. If a run is interrupted, inspect its trial log and the specific
Docker Compose project before cleaning up leftover containers; preserve the
job artifacts. A retry needs a fresh trial with seed state. Harbor regrade
validates the saved result; it does not restore databases and rerun Core's DAG.

## 6. Add traces, media, or more tasks

For screenshots at startup and after each completed action, export a new dataset
with `--record-screenshots`:

```bash
uv run --locked webarena-pro-harbor export --split dev --task 349 \
  --output ./exported/dev349-visual --browser-only --record-screenshots \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

Run it with `-p ./exported/dev349-visual` and a new job name. Captures appear in
the private evidence's `screenshots/` and `screenshots.jsonl`. They consume
wall time but no extra actions and are not added to the model's input. Missing
captures are labeled; the option cannot reconstruct older runs.

Choose media when exporting:

| Mode | Export options and requirements |
|---|---|
| Browser only | `--browser-only`; no transcription service |
| Standard | Omit `--browser-only`; set `WP_HARBOR_ASR_API_KEY` and optionally `WP_HARBOR_ASR_BASE_URL` for transcription, or use `--transcription-backend disabled` for frames only |
| Native audio | `--native-audio`; the agent/model must handle MCP WAV audio; JPEG overview remains available |
| Native video | `--native-video`; the agent/model must handle inline MP4; add `--native-audio` for synchronized audio |

Do not assume a text/image agent supports omni. See the
[media contract](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#browser-and-media-contract).

For a full Dev split, omit `--task` and use another new output directory:

```bash
uv run --locked webarena-pro-harbor export --split dev \
  --output ./exported/dev-browser --browser-only \
  --max-steps 50 --wall-seconds 600 --evaluation-timeout 900
```

Use `-p ./exported/dev-browser` and a new job name in the run command. Dev has
100 tasks; `--split test` selects 300. Increase `-n` only within the host's
combined website capacity. `--max-steps` accepts `50`, `100`, or `-1` for an
unlimited action budget; wall time still applies. Pin website images with
`--image-map` and the runtime with `--runtime-image` when reporting reproducible
comparisons; see
[image pinning](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#images-and-reproducibility).

Before a batch, check Docker network capacity on the deployment host using the
same Docker context and concurrency as Harbor. Every trial requires two networks;
the websites network remains internal. Guard the launch with `&&`:

```bash
uv run --locked webarena-pro-harbor preflight-networks --concurrency 6 && \
  harbor run -p ./exported/dev-browser -a claude-code -m '<your-model>' \
    -e docker -n 6 --job-name dev-network-checked
```

The probe temporarily allocates twelve networks, then removes only its own
network IDs. Failure stops the shell before Harbor starts trials. Success is
point-in-time capacity, not a reservation against other studies. Reduce
concurrency or arrange non-overlapping Docker address pools if it fails; inspect
Docker subnets and host/VPN routes before changing pools, and never globally
prune a shared host. See the
[network preflight details](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-harbor/README.md#check-docker-network-capacity-before-a-study)
for deadlines, cleanup, and remote-context limitations.

## Troubleshooting

| Symptom | Check |
|---|---|
| Harbor rejects collection fields or misses sidecar evidence | Use the pinned Harbor revision from step 1. |
| Image build/pull or website startup fails | Check Docker/Compose, image architecture, disk/RAM, and the trial logs; rebuild runtime and re-export together. |
| Docker reports no available non-overlapping IPv4 address pool | Run `preflight-networks --concurrency N` on the same Docker context before starting the queue; reduce concurrency or arrange safe host address pools. |
| Agent has no browser tools | The agent must support task-declared Streamable HTTP MCP and text/image results. Check its MCP startup log. |
| Answer is absent from evaluation | Inspect `calls.jsonl` for `webarena_submit`; final chat text is not submitted. |
| Judge timeout or missing grade | Check the private judge variables, endpoint access, `evaluation-state.json`, and judge audits. Adjust grading timeout in a new export if needed. |
| Export directory or job name already exists | Choose a new path/name and preserve the previous experiment. |

Installation, task export, and CLI checks do not demonstrate a successful live
trial. A live validation requires the Linux Docker host, published website
images, model credentials, and inspection of both Harbor status and Core grades.
