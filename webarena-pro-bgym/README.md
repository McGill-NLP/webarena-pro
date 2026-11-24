# WebArena-Pro BrowserGym + AgentLab 🤖

> Run reproducible browser-agent studies against WebArena-Pro's local website
> environments.

`webarena-pro-bgym` adapts the framework-neutral WebArena-Pro runtime to
[BrowserGym](https://github.com/ServiceNow/BrowserGym) and
[AgentLab](https://github.com/ServiceNow/AgentLab). It turns core task configs
into browser environments, runs agents, isolates parallel workers, evaluates
outcomes, and records inspectable study artifacts.

The benchmark contains **400 tasks**: **100 dev tasks** and **300 test tasks**.
Every task uses tiered DAG evaluation.

| Capability | BrowserGym + AgentLab integration |
|---|---|
| Task source | `webarena-pro-core` task configs with embedded evaluation DAGs |
| Execution | Supervised worker subprocesses sharing a FIFO task queue |
| Agent interface | BrowserGym observations and actions through AgentLab |
| Evaluation | Tiered DAG evaluations |
| Results | Screenshots, logs, summaries, rewards, and DAG traces |
| Dashboards | Environment control and live study monitoring |

Website lifecycle, URLs, credentials, resets, and evaluator primitives live in
[`webarena-pro-core`](../webarena-pro-core/README.md); media processing lives in
[`webarena-pro-media`](../webarena-pro-media/README.md). For the package boundary
and task lifecycle, see the [architecture guide](doc/README.md).

## Requirements

| Requirement | Purpose |
|---|---|
| Python 3.12+ | Runs BrowserGym, AgentLab, and this integration |
| Docker | Hosts local website environments |
| [`uv`](https://docs.astral.sh/uv/) | Installs and runs the workspace |
| Model-provider credentials | Authenticates the agent model selected for a run |

The media stack uses system `ffmpeg` and `ffprobe` when available, then falls
back to binaries supplied through `webarena-pro-media[transcription]`.

## Install

From the monorepo root:

```bash
cd webarena-pro-bgym
uv sync --python 3.12 --locked
uv run python -m playwright install chromium
```

Verify the resolved media binaries:

```bash
uv run python -c "from webarena_pro_media.sync_api import ffmpeg_binary, ffprobe_binary; print(ffmpeg_binary()); print(ffprobe_binary())"
```

## 🚀 Quickstart

Set the [agent and evaluator credentials](../docs/source/getting-started.md#model-credentials)
first. From `webarena-pro-bgym/`, start a website, create its authenticated browser
state, and run a live evaluator check:

```bash
uv run webarena-pro env start nextcloud --login
uv run webarena-pro run --site nextcloud --dry-run
```

Then launch selected tasks:

```bash
uv run webarena-pro run --split dev --site nextcloud --task 172,173 --max-steps 50
```

> [!TIP]
> Normal `webarena-pro run` invocations prepare isolated worker containers
> during per-task reset. For existing remote state, use the explicit
> [remote configuration](#remote-environment-hosts); `--no-autostart` alone
> does not disable worker-container setup or resets.

## Run evaluations

For Gemini's OpenAI-compatible endpoint, a filtered choice with a missing
message or text becomes an empty assistant response. AgentLab's action parser
then uses its bounded retry loop to request a valid action, preserving the same
behavior as other empty responses. The log records the provider's finish reason.

`webarena-pro run` evaluates every task with its tiered DAG, and
`run dashboard` opens the study dashboard. Use `run -h` to see all evaluation
options. There is no additional whole-task rubric judge.

New runs default to **50 environment steps per task**. The leaderboard will
show results at **50 steps, 100 steps, and unlimited** separately. Use
`--max-steps 50`, `--max-steps 100`, or `--max-steps -1` (also accepted as
`--max-steps unlimited`). Unlimited disables the environment step limit; the
agent can still finish or exhaust its own model-turn/token budget. DAG evaluations run
automatically at **steps 50 and 100 and on the final state**, saving both
finite cutoff scores while an unlimited run continues. A 100-step run also
provides the 50-step score. Report both the original run limit and the scoring
cutoff for derived scores.
See [step budgets and reporting](../docs/source/running-agents.md#step-budget-and-reporting)
for exhaustion behavior and comparison guidance.

| Goal | Command |
|---|---|
| Show runner help | `uv run webarena-pro run -h` |
| Check live DAG evaluators for one site | `uv run webarena-pro run --site metabase --dry-run` |
| Run tasks in parallel | `uv run webarena-pro run --site mattermost --n-jobs 2 --task 101,102,103,104` |
| List default Test tasks without live setup | `uv run webarena-pro run --list` |
| Run the dev set | `uv run webarena-pro run --split dev --n-jobs 6 --agent-model gemini/gemini-3.5-flash` |
| Continue interrupted tasks | `uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir>` |
| Skip previously attempted tasks | `uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir> --incomplete-only` |
| Retry failed tasks from scratch | `uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir> --retry-from-start` |

`--list` only inspects task selection. `--dry-run` performs live site preflight,
fetches evaluator state, and executes DAG checks without an agent episode. It
can start missing sites and invoke configured judges; it is not an offline
preview or evidence of task completion. The CLI still requires the selected
agent model's credentials, and configured judges may need their own credentials.

Useful eval flags:

| Flag | Behavior |
|---|---|
| `--n-jobs N` | Uses `N` supervised, isolated worker subprocesses, including `N=1` |
| `--n-relaunch N` | Total local attempts per task, including the first; default `1` adds no retry |
| `--max-worker-restarts N` | Limits consecutive worker replacements without task progress per runtime slot; default `3`, `0` disables replacement |
| `--no-autostart` | During preflight, fails if a site is unreachable instead of starting it; does not disable worker-container resets |
| `--skip-preflight` | Skips preflight reachability/startup checks; does not disable task setup or resets |
| `--no-reset-per-task` | Reuses existing sites in one in-process worker; disables supervised recovery and checkpoint replay |

### Parallelism and reset behavior

Each CLI worker receives its own website containers, ports, URLs, and
`WP_EXP_HASH` namespace. This prevents concurrent tasks from resetting or
mutating the same environment.

Workers, including the default single worker, pull the next task from a shared FIFO queue instead
of receiving fixed task groups. A free worker can keep taking pending tasks
while another worker finishes a slow task. Scheduling does not prefer sites:
every task still resets all its required sites. Sites start on demand during
reset; reserving a worker's ports does not start its containers.

Workers also reserve a standby runtime slot when at least two tasks are queued.
While one task runs, the next task's containers are reset and started in that
slot; after handoff, the released slot is prepared for the following task. The
runner falls back to a synchronous reset if prewarming cannot reserve a slot or
prepare it successfully. Set `WP_PREWARM_CONTAINERS=0` to turn prewarming off.
Active workers have priority over standby slots. A worker holds at most two
task claims with prewarming, or one without it.

The coordinator owns the FIFO in memory. Workers communicate through inherited
pipes using JSON-line requests; each claim, start, completion, or failure is
appended and flushed to `queue.jsonl` before acknowledgement. No database or
queue server is required. A `started` acknowledgement marks entry into experiment
preparation, before result artifacts or episode execution begin.

If a reset, step, or close times out, its unsafe worker exits. The coordinator
stops its entire process group (including prewarm children), cleans up its
runtime, and starts a replacement worker to take the next pending task. A
failed or interrupted task stays terminal for this invocation, so a reliably
hanging task cannot repeatedly block the queue. Unstarted claims return to
the FIFO only after their old process group has stopped. Ordinary recoverable
task errors still use `--n-relaunch N` attempts before becoming `failed`.

`--max-worker-restarts N` bounds consecutive worker startup failures per
runtime slot. The counter resets after a worker starts a task, allowing the
queue to continue past multiple distinct bad tasks. `0` disables replacement.
Idle workers remain available for recovered work. Lookahead is granted only
when pending tasks outnumber live workers, leaving work for startup/idle
workers and suppressing prewarming near the tail. This reduces avoidable tail
imbalance without revoking existing prewarm jobs.

Resume a parallel parent study with:

```bash
uv run webarena-pro run --resume-study /path/to/parent-study
```

Resume restores the original split, task selection, config directory, agent
model, worker count, step limit, retry limit, worker restart limit, and prewarm
setting. Explicit `--n-jobs`, `--max-steps`, `--n-relaunch`, or
`--max-worker-restarts` options can override those limits. Completed tasks stay
completed. Pending tasks start normally; failed and interrupted tasks receive
one new queue attempt, continuing from a compatible checkpoint when available.
Changing `--max-steps` invalidates an existing checkpoint; use
`--retry-from-start` for attempted tasks when changing their step budget.
Use `--incomplete-only` to run only pending and previously claimed-but-unstarted
tasks. Use `--retry-from-start` to discard saved continuation state for failed
and interrupted tasks and explicitly allow new agent calls from step zero.
When combined, `--incomplete-only` still skips all previously failed/interrupted
queue tasks. A torn
last journal line is repaired after exclusive coordinator ownership is obtained;
malformed complete events are refused. Resume also refuses while a previous
worker or its process group is still live. A new run into an existing study
directory is refused before metadata is overwritten. The benchmark wrapper
automatically resumes an existing all-site study.

Worker logs and results remain under `workers/worker-*/`; replacements and
resumes use new worker directories. Prior attempts remain inspectable, while
aggregate results select the queue's current attempt. Both runtime slots are
cleaned up at worker exit. The
coordinator returns a nonzero status if any task failed, was interrupted, or
remains pending, so shell scripts using `set -e` stop on such runs. The queue
improves load balancing; container and memory savings depend on the workload
and have not been established by this scheduling change.

Per-task reset uses `WP_RESET_BACKEND=auto` by default:

- lightweight sites use their package-level state restore contract;
- heavier sites recreate the Docker container; and
- snapshot-backed resets that require Docker access must execute on the
  environment host.

Override the strategy with `WP_RESET_BACKEND=state`, `container`, or `none`.
Checkpoint continuation requires an actual per-task reset. `--no-reset-per-task`
keeps the legacy in-process mode for existing or remotely hosted sites and
cannot be combined with multiple workers or `--max-worker-restarts`.

> [!NOTE]
> Each task record contains setup, intent, and its evaluation DAG under `eval`.
> Tiered criteria and their LLM fallback checks are preserved.
> The additional whole-task rubric judge cannot be enabled.

The task DAG, including its LLM fallback, runs when the agent issues
`done()`, `send_msg_to_user(...)`, or `report_infeasible(...)`, or when its step
budget is exhausted. At the environment's `max_steps` limit, it runs after the
last allowed action without adding another action or step. It uses the
resulting browser state, full recorded trajectory, captured downloads, and
initial baseline snapshots. It also runs automatically after actions **50 and
100** in longer runs, including unlimited runs, saving the live cutoff scores
and DAG traces without ending the episode or adding checkpoint scores to the
final reward. A cutoff
that coincides with completion or the run limit is graded once. Other steps
collect evidence and enforce the allowed-site URL checks without running the
DAG. There is no automatic stop based on an intermediate score.

Task summaries retain `step_budget_scores` entries for the available `"50"`,
`"100"`, and `"unlimited"` budgets, including each `score`, full-credit `success`
flag, and `evaluated_at_step`. The unlimited entry is the graded final state
of an unlimited run; `max_steps: -1` identifies that run limit. Use these
recorded evaluations to derive SR at each budget.

Agents with their own model-turn or token budget can signal exhaustion by
returning `(None, AgentInfo(extra_info={"budget_exhausted": True}))`. The study
then grades the last recorded state before closing the environment. Budget
exhaustion remains a truncation, even if the final DAG score is one; an explicit
completion remains a termination. The final step records `dag_evaluated = true`,
`evaluation_trigger` (`agent_completion` or `budget_exhaustion`), the score,
results and trace, including a genuine zero score.

Ordinary steps, reset, exceptions, timeouts, interruptions, and a `None` action
without the budget signal do not trigger grading. Unevaluated steps retain a
zero reward and `task_info.dag_evaluated = false`.

## 📊 Dashboards and results

| Dashboard | Default URL | Shows |
|---|---|---|
| `uv run webarena-pro env dashboard` | `http://dashboard.localhost:8080` | Website containers and connect links |
| `uv run webarena-pro run dashboard` | `http://127.0.0.1:8765` | Studies, worker lanes, task states, rewards, logs, and DAG traces |

Point the run dashboard at a specific source when needed:

```bash
uv run webarena-pro run dashboard --study-dir ~/agentlab_results/<study-name>
uv run webarena-pro run dashboard --results-root ~/agentlab_results
```

AgentLab study directories contain artifacts such as:

- `experiment.log` for episode and environment logs;
- `summary_info.json` for the terminal state, reward, and evaluator output;
- `screenshot_step_<N>.png` for visual observations; and
- `dag_trace.html` for dependency-aware evaluator evidence.

### Agent model requests

Each supported BrowserGym agent records its provider calls in the experiment
directory beside the saved steps. A single browser decision can make several
model calls, and a model call can make several HTTP attempts.

| Artifact | Contents |
|---|---|
| `model_requests.jsonl` | One version 1 JSON object per observed HTTP attempt, in dispatch order. |
| `completions/<call_id>-<attempt>.request.json` | Provider request body after credential redaction, including the messages or native media parts actually sent. |
| `completions/<call_id>-<attempt>.response.json` | Redacted provider response body, including error responses. A transport failure can leave only the request. |
| `model_usage.json` in the experiment directory | Episode counts and sums, plus the same accounting under `steps`, keyed by trajectory step. |
| `model_usage.json` in the study directory | Totals across recorded episodes, including usage from failed attempts and fresh retries. |
| `model_request.schema.json` in the study directory | Portable JSON Schema for validating each journal row. |

**Request identity and outcome.** `episode_id` identifies a logical episode across
checkpoint continuations. `step_id` is the zero-based BrowserGym trajectory step.
Each model invocation gets a new `call_id`. HTTP retries keep that ID and
increment the one-based `attempt`. For GenericAgent, `call_reason` is `action`
for the initial call and `parser_retry` when its parser asks the model again.
`provider`, `model_requested`, `model_served` and `route` identify the adapter,
requested model, actual model and upstream route. `provider_request_id` comes
from the request ID header and `completion_id` from the provider body.
`status`, `http_status`, `error_type` and `finish_reason` describe the outcome
of the request. An in-flight attempt is marked `unresolved` before dispatch so
a stopped worker leaves its request and unknown usage visible. A successful response may still require an action parser retry.
`started_at` is UTC and `latency_ms` measures the HTTP attempt through receipt
of the response body. The built-in adapters request non-streamed completions,
so `time_to_first_token_ms` is null. `raw_request_path` and `raw_response_path`
are relative to the experiment directory.

**Usage.** Every count below belongs to `usage`. A reported zero is `0`.
An unavailable count is `null`.

| Field | Meaning |
|---|---|
| `input_tokens.regular` | Input processed without a cache hit, including cache writes. |
| `input_tokens.cached` | Input served from cache. |
| `input_tokens.total` | Total input. Equals regular plus cached when both are known. |
| `input_tokens.cache_write` | The separately metered portion of regular input written to cache, when reported. |
| `input_tokens.by_modality.<modality>` | The same `regular`, `cached` and `total` counters for one modality. The map contains only modalities the provider identifies. |
| `output_tokens` | Total output plus available `reasoning`, `text` and `tool_calls` counts. Unreported components stay null. |

For example, Gemini can report 750 text and 250 image tokens, with 300 text
and 100 image tokens served from cache. The text split is 450 regular and
300 cached. The image split is 150 regular and 100 cached. The request has
600 regular and 400 cached tokens. A provider that reports just the 400
cached tokens across all modalities leaves the per-modality split unknown.

**Totals and coverage.** `request_count` includes failed attempts. `failed_count`
counts failed attempts, `unresolved_count` counts attempts with an unknown
outcome and `retry_count` counts attempts after the first in a logical call. Each entry in `metrics` contains a `sum` of known values and
`reported_requests`, the number of attempts contributing to it. A sum is
partial when that count is smaller than `request_count`. A sum over no known
values is null. Latency sums measure cumulative request time. Archived fresh
retries contribute their own calls. Checkpoint continuations link to a shared
journal and completions directory under `model_traces/<episode_id>/` beside
the checkpoint. Run totals count each journal once. Historical studies and
custom agents without an instrumented provider may have no request artifacts.

The OpenAI-compatible, Anthropic Messages and native Gemini adapters capture
provider JSON before the agent extracts its text. HTTP headers are omitted.
Raw bodies can contain the task prompt, website content and media. Keep these
private run artifacts together when copying a study. The portable schema is
available as `webarena_pro_core.model_requests.ModelRequest.model_json_schema()`.

### Resume and relaunch

Continue a queued study through the supported CLI:

```bash
uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir>
```

The worker saves each completed agent decision before applying its action.
Continuation resets the sites, replays saved actions without asking the agent
again, restores the saved agent state, and continues at the first unsaved
decision. The original step budget still applies. This saves already-recorded
model work; it is not a browser-memory snapshot and replay can still take time.
Continuation currently supports the standard `GenericAgent` and literal
high-level browser actions. Custom agents, arbitrary Python actions, uploads,
media actions, and custom step verifiers require an explicit fresh retry when
their state cannot be safely replayed.

Replay refuses to continue if the saved task/model configuration is incompatible,
the task date has changed, reset is disabled, the recorded observations no longer
match, or a paid call was interrupted before its response was durably recorded.
It fails before making another agent call instead of silently starting over.
Use `--retry-from-start` when you intentionally want a new full attempt. Grading
and media operations may have separate costs; continuation does not guarantee
that every external operation can be recovered after an interruption.

Studies created before checkpoint support cannot recover their old agent state.
A legacy study without a queue journal requires `--retry-from-start` to migrate
unfinished tasks into a supervised queue under `<study>/_recovery/`, retaining
the original task definitions, agent configuration, and old artifacts. Add
`--incomplete-only` to skip old errored tasks. Future resumes of the original
study automatically use that recovery queue. Checkpoint files contain private
serialized agent state and should only be loaded from trusted local studies.

For controlled maintenance of an existing study, use the lower-level relaunch
script:

```bash
uv run scripts/relaunch_errored_experiments.py \
  --study-dir /mnt/data/<study_dir> \
  --jobs 4
```

Add `--limit 1 --jobs 1` for a smoke test before relaunching the full queue.
This maintenance script starts fresh attempts; use the supported CLI above for
checkpoint continuation and worker supervision.

## Per-model benchmark scripts

The model scripts call `uv run webarena-pro run` with a fixed agent model and
model-specific `AGENTLAB_EXP_ROOT`. They accept the runner's evaluation flags:

```bash
scripts/run_benchmark_gemini_3_1_pro.sh
scripts/run_benchmark_gemini_3_1_flash_lite.sh --split dev --site nextcloud --task 172,173
scripts/run_benchmark_qwen35_9b.sh --site metabase --max-steps 100
scripts/run_benchmark_qwen3_6_27b.sh
scripts/run_benchmark_qwen3_6_36b_moe.sh
scripts/run_benchmark_gemma4_26b_a4b.sh
scripts/run_benchmark_gemma4_31b.sh
```

With no target, a script runs all sites in one study at its results root;
`--site` selects a study subdirectory for that site. Task filters use separate
study directories. Repeating a command resumes an existing study and preserves
its saved settings unless explicit runtime overrides are supplied.

New runs default to four workers and 50 steps per task. Set `BENCHMARK_N_JOBS`
or `BENCHMARK_MAX_STEPS`, or pass `--n-jobs` or `--max-steps`, to override those
defaults. The scripts manage `--agent-model` and `--study-dir`, so explicit
overrides of those flags are rejected.

## Lower-level scripts

The CLI covers normal runs. These scripts remain available for debugging and
study maintenance:

| Script | Purpose |
|---|---|
| `scripts/relaunch_errored_experiments.py` | Requeues errored or incomplete experiments |
| `scripts/replay_verifier_on_drive.py` | Replays verifier logic over saved artifacts |

Use `uv run <script> -h` to inspect the lower-level options. Prefer the
`webarena-pro` CLI unless you are debugging or maintaining saved studies.

## Multimodal actions

BrowserGym exposes WebArena-Pro media helpers as agent actions:

- `listen()` delivers a bounded audio-only clip to
  models configured with `audio_support=True`;
- `watch()` supplies video overviews or actual video clips, with optional audio,
  to models configured with `video_support=True`;
- `transcribe()` converts page audio or video into text (remote or local Whisper);
- `extract_frames()` samples frames from video for vision-capable models; and
- results are injected into the next accessibility-tree observation.

Authenticated media fetching and ffmpeg resolution are implemented in the
shared media package. See the [media guide](../docs/source/media.md) for the
supported inputs, capability settings, limits, and behavior. To opt in from the
CLI, use `--agent-model gemini/gemini-3.5-flash-omni` for Gemini's native video
and audio inputs, or an `-audio` alias for audio only. Provider model IDs stay
unchanged and automatic background transcription is disabled. The former
`listen(..., n_frames=...)` argument is removed; use `watch()` for video.

## 🧪 Evaluation and trace analysis

Completed tasks use dependency-aware DAG evaluators. Each trace records node
dependencies, pass/fail/skip status, decision tier, evidence, and the final
score.

Inspect AgentLab traces with the WebArena-Pro XRay extension:

```bash
uv run webarena-pro-agentlab-xray
```

The **DAG Evaluator** tab follows the selected episode step. The browser-based
run dashboard links to the same saved trace artifacts.

## Programmatic usage

```python
from agentlab.agents.generic_agent import GenericAgentArgs
from agentlab.agents.generic_agent.agent_configs import FLAGS_GPT_4o
from agentlab.llm.llm_configs import CHAT_MODEL_ARGS_DICT

from webarena_pro_bgym.benchmark.benchmark import WebArenaProBenchmark
from webarena_pro_bgym.study import WebArenaProStudy

agent = GenericAgentArgs(
    chat_model_args=CHAT_MODEL_ARGS_DICT["openai/gpt-5-nano-2025-08-07"],
    flags=FLAGS_GPT_4o,
)

benchmark = WebArenaProBenchmark(sites=["nextcloud"])
study = WebArenaProStudy(
    agent_args=[agent],
    benchmark=benchmark,
    comment="local-run",
)
study.run(n_jobs=1, parallel_backend="sequential", n_relaunch=1)
```

Use the CLI for parallel runs so worker processes receive isolated runtime
configuration before they start.

## Remote environment hosts

Agents can run separately from the Docker host. On the environment server:

```bash
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_WEB_SERVER_BIND_HOST=0.0.0.0
export WP_URL_MODE=subdomain
uv run webarena-pro env start all
```

After installing this workspace on the agent machine, run a live evaluator
check from `webarena-pro-bgym/` against the same public URL:

```bash
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_URL_MODE=subdomain
uv run webarena-pro run --site jobportal --dry-run --no-autostart
```

For an agent episode using the existing remote state, select the single-process,
no-reset mode:

```bash
uv run webarena-pro run --site jobportal --no-reset-per-task --no-autostart --n-jobs 1
```

This mode reuses state between tasks and disables supervised recovery and
checkpoint replay. `--no-autostart` by itself only controls preflight; normal
supervised runs ensure Docker is available and reset isolated worker containers.

> [!IMPORTANT]
> URL-based resets work remotely. Docker-exec and container-recreate resets
> still require access to the environment host's Docker daemon or a dedicated
> remote reset service. Run on that host or configure remote Docker access when
> per-task container isolation is required.

## Project map

| Path | Responsibility |
|---|---|
| `src/webarena_pro_bgym/benchmark/` | BrowserGym benchmark, environment, and task adapters |
| `src/webarena_pro_bgym/study.py` | AgentLab experiment and study integration |
| `src/webarena_pro_bgym/parallel.py` | Worker-slot allocation and process isolation |
| `src/webarena_pro_bgym/dashboard.py` | Study and worker dashboard server |
| `src/webarena_pro_bgym/xray.py` | AgentLab XRay DAG extension |
| `scripts/` | Direct runners and study-maintenance utilities |
| `tests/` | Unit and integration tests |

Task definitions live in
[`../webarena-pro-core/src/webarena_pro_core/config/`](../webarena-pro-core/src/webarena_pro_core/config/),
not in this adapter package.

## Development

Run the complete test suite:

```bash
uv run pytest -q
```

To include the real Chromium crash and navigation regressions, install the
browser and enable them explicitly. CI runs these tests with a two-minute
per-test timeout so a stalled browser fails the job:

```bash
uv sync --locked --group dev
uv run python -m playwright install chromium
WEBARENA_PRO_TEST_BROWSER=1 uv run --locked pytest -q --timeout=120 --timeout-method=thread tests
```

Run the benchmark/task tests while iterating on environment behavior:

```bash
uv run pytest tests/test_task.py tests/test_benchmark.py -q
```

For reproducible comparisons, keep the task selection, model configuration,
website images, reset mode, and worker count fixed across runs.

## Dev and test sets

The Dev set contains **100 tasks**. The test set contains **300 tasks**.

Use `--split dev` or `--split test` to select a set. Omitting `--split` selects
the 300 Test tasks before applying any site or task filters.

```bash
uv run webarena-pro run --split dev
uv run webarena-pro run --split test --n-jobs 4
uv run webarena-pro run --split dev --list
uv run webarena-pro run --split test --site mattermost --list
```

`--site` and `--task` narrow the selected split. The split flag cannot be used with `--resume-study`, which preserves the original study’s tasks. Dev runs use `config/splits/dev.json` directly, including dry runs and parallel workers. Test runs use only the individual website `*.raw.json` configs. Each task contains its evaluation under `eval`. No tasks or evaluators are duplicated between them.


### Captured UI evaluation evidence

Core evaluators consume versioned UI facts instead of live browser pages.
Core's bundled `webarena_pro_core.ui_evidence` sync/async collectors preserve selector,
visibility, and text semantics; Core retains all grading predicates. BrowserGym
collects privately at evaluation time and persists the `ui_evidence`
result field. `EvalContext(page=...)` callers must migrate to `ui_evidence`.
See [browser evidence and replay](../docs/source/evaluators.md#browser-evidence-boundary)
for the schema, limits, failure semantics, and saved-evaluation migration.
