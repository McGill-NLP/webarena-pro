# Run an external agent through MCP

This walkthrough runs Dev task `349` (flight-search) with Claude Code connected
to the browser/media MCP service. You act as the orchestrator: start the website,
prepare a private session, launch the agent, finalize grading, and stop resources.
For automatic per-trial container isolation and scheduling, use the
[Harbor walkthrough](running-harbor-agents.md).

The MCP service supplies tools and private Core evaluation. It does not select
models, run an agent loop, reset externally owned websites, or manage retries.
The [MCP reference](mcp.md) and
[package guide](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-mcp/README.md)
describe its complete configuration and tool contract.

## 1. Install the service and client

Use Linux or macOS, Python 3.12, `uv`, Node.js 20+, npm, and Docker for the local
website. The website images target `linux/amd64`; use a supported Docker host
or validate your host's emulation separately. From a shell:

```bash
git clone https://github.com/McGill-NLP/webarena-pro.git
cd webarena-pro
export WEBARENA_REPO="$(pwd)"
cd "$WEBARENA_REPO/webarena-pro-mcp"
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-mcp install
```

On Linux, install Chromium system dependencies as needed:

```bash
uv run --locked python -m playwright install --with-deps chromium
```

Install Claude Code using its [official setup instructions](https://code.claude.com/docs/en/setup).
Use a separate client installation; the repository does not install an agent.
The command below pins the version used by the adapter's current Claude Code
examples, after `claude` has been installed:

```bash
claude install 2.1.318
claude --version
```

The example uses a client supporting Streamable HTTP MCP, text, and images.
It starts with media disabled; omni needs a separately qualified audio/video
client and model. CLI flags are documented in the
[Claude Code CLI reference](https://code.claude.com/docs/en/cli-reference).

## 2. Prepare a private run and fresh website

Continue in the same shell, from `webarena-pro-mcp/`. Load `ANTHROPIC_API_KEY`
for the agent and `OPENROUTER_API_KEY` for the judge from your secret manager or
private environment. Set the remaining values:

```bash
: "${ANTHROPIC_API_KEY:?Load the agent API key first}"
: "${OPENROUTER_API_KEY:?Load the OpenRouter judge API key first}"
umask 077
export WEBARENA_RUN="$(mktemp -d /tmp/webarena-mcp.XXXXXX)"
mkdir "$WEBARENA_RUN/private" "$WEBARENA_RUN/client"
export WP_EVAL_TOKEN="$(openssl rand -hex 32)"
export WEBARENAPRO_LLM_JUDGE_MODEL='qwen/qwen3.6-27b'
export OPENROUTER_BASE_URL='https://openrouter.ai/api/v1'
export WP_EXP_HASH="$(basename "$WEBARENA_RUN")"
export WP_URL_MODE=port
export WP_FLIGHT_SEARCH_HOST_PORT=3001
export WP_FLIGHT_SEARCH_URL='http://localhost:3001'
```

The short private run path also keeps the Unix control socket below platform
path-length limits. `WP_EXP_HASH` names a separate website container. Port 3001
must be free: if you select another port, change both flight-search variables
before running any commands. The examples use one local trial at a time.

Start only the required website:

```bash
uv run --locked webarena-pro env start flight-search --wait-timeout 180
uv run --locked webarena-pro env status flight-search
```

The new container starts from the image's seed state, and `env start` waits for
readiness. The service later performs login using the task's account. Keep the
same `WP_EVAL_TOKEN` in the website launcher and service environment. Task 349
needs the LLM judge even in browser-only mode; the Core variable names here are
different from Harbor's `WP_HARBOR_*` forwarding variables.

For a fresh retry using this website container, first stop the prior service,
run `uv run --locked webarena-pro env restart flight-search`, then create new
session/evidence paths. Restart recreates the trial website and discards mutable
state. Do not reset a live task or reuse an old browser session as a fresh trial.

## 3. Generate the private configuration and public prompt

From `webarena-pro-mcp/`, generate the session directly from Core's unchanged
Dev task. Only the original intent, site URLs, and tool instructions go into
the agent prompt; the evaluation DAG stays private.

```bash
uv run --locked python - <<'PY'
import json
import os
from pathlib import Path

from webarena_pro_core.task import load_task_configs
from webarena_pro_core.website_metadata import deployed_website_urls
from webarena_pro_mcp.session import normalize_config

run = Path(os.environ["WEBARENA_RUN"])
task = next(t for t in load_task_configs(split="dev") if t.task_id == "349")
urls = deployed_website_urls(task.sites)
config = {
    "schema_version": 1,
    "task": task.raw_task,
    "urls": urls,
    "max_steps": 50,
    "wall_seconds": 600,
    "setup_timeout": 1800,
    "tool_timeout": 60,
    "evaluation_timeout": 900,
    "media": {"enabled": False},
}
normalize_config(config)  # Validate without starting a browser or grading.
(run / "private/session.json").write_text(json.dumps(config, indent=2))
prompt = task.intent + "\n\nTask websites:\n"
prompt += "\n".join(f"- {site}: {url}" for site, url in urls.items())
prompt += (
    "\nUse only the WebArena-Pro MCP tools for website interactions. "
    "Start by observing the browser. You have 50 UI/media actions and 600 seconds. "
    "Snapshots, screenshots, find queries, tab listings, and submission are free. "
    "Finish with webarena_submit(answer), including after the last allowed action, then stop. "
    "A final chat message alone does not submit an answer.\n"
)
(run / "client/prompt.txt").write_text(prompt)
(run / "client/mcp.json").write_text(json.dumps({
    "mcpServers": {
        "webarena-pro": {"type": "http", "url": "http://127.0.0.1:8000/mcp"}
    }
}, indent=2))
print("Prepared task", task.task_id, "for", urls)
print("Private run directory:", run)
PY
```

Keep `private/session.json`, evidence, and the control socket away from the
agent. Do not pass the full task JSON or repository to its prompt. Each new
service instance requires a new evidence directory. If port 8000 is occupied,
change it in both `client/mcp.json` and the service command below.

## 4. Start the service and check readiness

Still in `webarena-pro-mcp/`, launch the service with the evaluator environment
from step 2:

```bash
uv run --locked webarena-pro-mcp serve \
  --config "$WEBARENA_RUN/private/session.json" \
  --directory "$WEBARENA_RUN/private/evidence" \
  --socket "$WEBARENA_RUN/control.sock" \
  --host 127.0.0.1 --port 8000 \
  >"$WEBARENA_RUN/private/service.log" 2>&1 &
WEBARENA_SERVICE_PID=$!
```

Wait for readiness before starting the agent. This bounded check uses the
health endpoint and consumes no browser actions:

```bash
uv run --locked python - <<'PY'
import time
from urllib.error import URLError
from urllib.request import urlopen

deadline = time.monotonic() + 1800
while time.monotonic() < deadline:
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=5) as response:
            if response.status == 200:
                print(response.read().decode())
                break
    except (URLError, TimeoutError):
        pass
    time.sleep(2)
else:
    raise SystemExit("Service not ready; inspect private/service.log")
PY
```

Success returns `{"ready":true}` after browser startup and authentication. On
failure, stop here and inspect `private/service.log`. The public HTTP endpoint
has no authentication; keep it loopback-only for this local example. Deployments
must restrict it to the owning client and keep browser/backend access private.

## 5. Run the external agent

In the same shell, launch the client from its separate directory. Choose an
Anthropic model available to your account (this is an example ID):

```bash
export WEBARENA_AGENT_MODEL='claude-sonnet-5-5'
(
  cd "$WEBARENA_RUN/client"
  env -i PATH="$PATH" HOME="$HOME" \
    ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    CLAUDE_CONFIG_DIR="$WEBARENA_RUN/client/claude-config" \
    DISABLE_AUTOUPDATER=1 \
    claude --bare -p --model "$WEBARENA_AGENT_MODEL" \
      --setting-sources '' --tools '' \
      --strict-mcp-config --mcp-config ./mcp.json \
      --allowedTools 'mcp__webarena-pro__*' \
      --max-turns 60 --output-format stream-json --verbose \
      < ./prompt.txt > ./agent.jsonl 2> ./agent.stderr.log
)
```

The client gets its own API key, the prompt, and one MCP endpoint. The clean
environment omits evaluator secrets; `--bare` skips automatic project context,
and built-in tools are disabled. Strict MCP configuration limits the loaded
servers to this file. These client settings support a local walkthrough; use
separate OS/container permissions for stronger isolation, as Harbor does.
The flags and HTTP configuration are covered by the official
[CLI reference](https://code.claude.com/docs/en/cli-reference) and
[MCP guide](https://code.claude.com/docs/en/mcp).

`--max-turns` limits model turns, not WebArena actions. The service independently
enforces its 50-action and 600-second budgets. Inspect `client/agent.jsonl` for
MCP calls and the final submission. If the client fails or does not stop after
budget exhaustion, stop that client before finalizing; keep the browser service
and website running. Never reconnect another agent to continue the same trial
as if its budget had reset.

## 6. Finalize, inspect, and clean up

After the client exits, the shell returns to `webarena-pro-mcp/`. Grade the live
website through the private Unix socket:

```bash
uv run --locked webarena-pro-mcp finalize \
  --socket "$WEBARENA_RUN/control.sock" --timeout 1200
uv run --locked python - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["WEBARENA_RUN"]) / "private/evidence/result.json"
result = json.loads(path.read_text())
print("status:", result["status"])
print("steps:", result["steps"])
print("rewards:", result.get("rewards"))
print("error:", result.get("error"))
PY
```

The finalizer is idempotent. Its wait timeout allows the service's 900-second
grading deadline plus evidence collection and diagnostics. A successful private
result has `status: "graded"`, `rewards.reward` (partial credit),
`rewards.success`, and available cutoff scores. Inspect the DAG and judge audits
as well: a judge configuration failure can produce a conservative failed node
with a recorded error. An absent result or `status: "error"` is an infrastructure
failure, not a measured zero.

Keep these files for analysis:

| Path under the run directory | Contents |
|---|---|
| `client/agent.jsonl` | Agent events and provider-reported usage |
| `private/evidence/result.json` | Terminal Core result and budget scores |
| `private/evidence/calls.jsonl`, `trajectory.jsonl` | Public tool calls and observations |
| `private/evidence/evaluation-state.json` | Grading state, elapsed time, and failures |
| `private/evidence/` | Configuration provenance, DAG results, judge audits, UI evidence, and downloads |

After collecting the result, stop the service and this trial's website from the
same shell (so the container naming variables still match):

```bash
kill -TERM "$WEBARENA_SERVICE_PID"
wait "$WEBARENA_SERVICE_PID" || true
uv run --locked webarena-pro env stop flight-search
```

Keep `$WEBARENA_RUN` until you have archived the evidence; it is under `/tmp`
and may be removed by the OS. Stopping the public service does not finalize a
trial automatically. Finalization must precede browser and website teardown.

## Media, concurrency, and troubleshooting

To enable standard media in a new private configuration, set
`"media": {"enabled": true, "profile": "standard", "transcription": "disabled"}`
for frame extraction and JPEG watch overview, or use `"transcription": "api"` and provide
`WEBARENA_PRO_ASR_API_KEY` to the service. Select `"profile": "omni"` and independently
enable `"audio": true` for WAV listening and/or `"video": true` for inline MP4
watching, only with a compatible client/model.
See the [media configuration reference](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-mcp/README.md#browser-and-media-tools)
for limits, dependencies, and local transcription. Do not assume this Claude
Code example supports omni attachments.

Each parallel trial needs independent website state, ports/URLs, browser
service, socket, evidence directory, and client. Retries also need fresh state.
An orchestrator must enforce these lifecycles; the removed standalone
`webarena-pro-mcp run` command is not part of this flow.

| Symptom | Check |
|---|---|
| Service fails before `/health` is ready | Inspect `private/service.log`; verify Node/Chromium installation, site URL, readiness, and login. |
| Address already in use | Allocate free website and MCP ports; update the corresponding URLs before starting. |
| Client cannot discover tools | Check `client/mcp.json`, service health, strict configuration, and `client/agent.stderr.log`. |
| Submission missing | Look for `webarena_submit` in the call log; final chat text is insufficient. |
| Judge or backend authentication fails | Check `OPENROUTER_API_KEY`, judge routing, and the shared `WP_EVAL_TOKEN` in the service/website environments. |
| Finalizer cannot connect | Keep the service alive and use the same private socket path; do not teardown early. |
| Retry starts from modified data | Reset the owned website and use a new browser/evidence directory. |

Checking configuration, CLI help, and local fixture tests does not validate a
live provider run. Record the actual agent version, model, budgets, endpoint
configuration, and validation limitations when reporting results.
