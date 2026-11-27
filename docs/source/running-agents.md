# Running BrowserGym agents

This guide covers BrowserGym/AgentLab studies through `webarena-pro-bgym`.
Start with [Getting started](getting-started.md) for installation and a first
run. Core supplies website setup and grading; the adapter owns agent execution,
worker isolation, recovery, and study artifacts.

External agents can connect to the [browser/media MCP service](mcp.md) in
`webarena-pro-mcp`. Harbor or another application supplies the agent loop and
scheduling; the service enforces tool/action limits and delegates grading to Core.

## Prepare a Website

Use Python 3.12 and `uv`. From the monorepo root, install Core and start a site
for an interactive check:

```bash
cd webarena-pro-core
uv sync --python 3.12 --locked
uv run webarena-pro env start nextcloud
```

The commands use the selected package's environment through `uv run`; no
shell activation is required. Normal BrowserGym runs prepare their own isolated
sites during per-task reset, so starting every website in advance is unnecessary.

Subdomain URLs are used by default, for example
`http://nextcloud--local.localhost:8080`. Use `WP_URL_MODE=port` if you need
direct localhost ports.

## Use A Deployment Server URL

You can run the website containers and core proxy on one machine, then run
AgentLab locally against that server. On the deployment server, bind the proxy
publicly and use a wildcard DNS name for the server IP:

```bash
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_WEB_SERVER_BIND_HOST=0.0.0.0
export WP_URL_MODE=subdomain
uv run webarena-pro env start all
```

This produces URLs like
`http://jobportal--local.213.0.113.10.sslip.io` and
`http://nextcloud--local.213.0.113.10.sslip.io`. Open the proxy port in the
server firewall. If you use a non-default port, include it in
`WP_WEB_SERVER_URL`, for example `http://213.0.113.10.sslip.io:8080`.

On the agent machine, install the BrowserGym workspace as described below.
From `webarena-pro-bgym/`, use the same public URL for a live evaluator check:

```bash
export WP_WEB_SERVER_URL=http://213.0.113.10.sslip.io
export WP_URL_MODE=subdomain
uv run webarena-pro run --site jobportal --dry-run --no-autostart
```

`--dry-run` runs live DAG checks without an agent episode. It can contact
backend services and configured judges, and the CLI still checks the selected
agent model's credentials. Use `--list` to inspect task selection without live
setup or evaluator calls.

To run an agent against existing remote state without local worker-container
setup, use the single-process mode explicitly:

```bash
uv run webarena-pro run --site jobportal --no-reset-per-task --no-autostart --n-jobs 1
```

This reuses site state across tasks and disables supervised worker recovery and
checkpoint replay. `--no-autostart` affects preflight startup only; by itself,
it does not prevent normal supervised runs from ensuring Docker is running and
resetting worker containers. For isolated per-task resets, run on the environment
host or provide access to its Docker daemon. URL-based state resets can run
remotely, while Docker-exec restore and container recreation require Docker access.

## BrowserGym And AgentLab

Complete the [workspace installation](getting-started.md#requirements-and-installation)
and [model credentials](getting-started.md#model-credentials), then run these
commands from `webarena-pro-bgym/`:

```bash
uv run webarena-pro run -h
uv run webarena-pro run --site metabase --dry-run
uv run webarena-pro run --split dev --site nextcloud --task 172,173 --max-steps 50
uv run webarena-pro run --site mattermost --n-jobs 2 --task 101,102,103,104
uv run webarena-pro run --split test --n-jobs 6 --max-steps 50 --agent-model gemini/gemini-3.5-flash
```

`webarena-pro run` forwards to `webarena-pro-bgym` when that package is
installed or available as a sibling checkout. Use `--n-jobs N` for isolated
subprocess workers, each with its own website containers and per-task reset.
Every task uses tiered DAG evaluation. Select the 100 dev tasks with
`--split dev`, or the 300 test tasks with `--split test` (the default). Add
`--list` to preview the selection. Dev loads from `config/splits/dev.json`;
the website configs contain only Test tasks. Each task record contains its
setup, intent, and evaluation DAG under `eval`.

`--list` only prints matching task IDs. `--dry-run` checks selected tasks against
live sites and evaluates their DAGs; preflight may start missing environments
unless `--no-autostart` is set. It is not a task-selection preview and does not
establish that an agent completed a task. The selected agent's API credentials
are checked even for this live evaluator mode, and configured judge calls may
also require credentials.

`--n-relaunch N` sets the total number of local attempts per task in the current
invocation, including the first attempt; its default `1` means no additional
attempt. Fatal worker failures follow the separate worker-replacement path.

On platforms with `SIGALRM`, the main worker thread enforces wall-clock limits
for setup/reset, each model or environment operation, and environment close.
`WEBARENA_PRO_RESET_TIMEOUT_SECONDS` and `WEBARENA_PRO_STEP_TIMEOUT_SECONDS`
default to 600 seconds; `WEBARENA_PRO_CLOSE_TIMEOUT_SECONDS` defaults to 120.
Non-positive values disable the corresponding limit. An expired operation
aborts through HTTP-client retries, saves the timeout and available episode
results, and marks the worker for replacement. A timed-out model call remains
ambiguous for checkpoint replay because the provider may have completed it.
The internal `WebArenaProStepTimeoutError` derives from `BaseException` so
ordinary transport and provider exception handlers cannot swallow the deadline;
the experiment runner handles it explicitly, including during close.

Navigation outside a task's selected website origins is blocked and reported
in the next observation. Unauthorized popups are closed and interrupted tabs
are restored when possible. A failed local navigation remains recoverable:
the agent can go back or navigate to an available task URL. These navigation
errors do not by themselves end the episode or erase completed checkpoints.

Resume an interrupted study:

```bash
uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir> --incomplete-only
```

Open the run dashboard:

```bash
uv run webarena-pro run dashboard
```

Then open `http://127.0.0.1:8765`.

To view and manage website containers instead, use the website viewer:

```bash
uv run webarena-pro env dashboard
```

Then open `http://dashboard.localhost:8080`.

From the BrowserGym workspace, use `uv run` to select its installed dependencies:

```bash
uv run webarena-pro run --split dev --site nextcloud --task 172,173
uv run webarena-pro run --all
uv run webarena-pro run --site mattermost --n-jobs 2
```

Per-task reset is enabled by default. To reuse the same site state across
tasks:

```bash
uv run webarena-pro run --site nextcloud --no-reset-per-task
```

## Resume and recovery

Normal CLI runs use a supervised FIFO queue, including runs with one worker.
A timed-out worker is replaced so pending tasks can continue; its failed task
is retried when the study is resumed. Each worker uses isolated website state.

Observation extraction can recover once per episode from a confirmed renderer
crash by replacing the active tab in the same browser context and opening its
last observed authorized URL. This does not replay the agent's action, rerun
login, or reset the websites. Server state, cookies, and local storage remain;
unsaved page edits and session storage may be lost. The next observation warns
the agent to inspect the current state before continuing. Recovery is disabled
during checkpoint replay. A repeated crash, disconnected browser, missing safe
URL, or failed tab restoration follows the existing environment-error and
worker-discard path. Closing the crashed tab has a two-second deadline. If it
cannot be closed and removed from the context, recovery aborts and discards the
worker rather than leaving a dead tab in later observations or tab actions.
`browser_recoveries.json` records restored, failed, and interrupted recovery
attempts next to the existing browser diagnostics.

Resume an interrupted study with:

```bash
uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir>
```

Resume restores compatible saved agent work: the runtime resets the sites,
replays recorded actions, and continues from the checkpoint. Use
`--incomplete-only` to skip previously attempted tasks. Checkpoint continuation
requires compatible task/model settings and replayable actions; it cannot
recover every custom agent, media operation, or interrupted model call.

To explicitly start fresh attempts with new model calls, use:

```bash
uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir> --retry-from-start
```

Older studies without queue checkpoints require this explicit retry to migrate
unfinished work into a recovery queue. See the
[BrowserGym recovery guide](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-bgym/README.md#resume-and-relaunch)
for checkpoint restrictions and legacy-study migration details.

## Step Budget And Reporting

New BrowserGym/AgentLab CLI runs default to **50 environment steps per task**.
Select `--max-steps 50`, `--max-steps 100`, or `--max-steps -1` for the
three reporting budgets. Unlimited (`-1`, also accepted as
`--max-steps unlimited`) disables the environment step limit. The agent can
still finish or reach its own model-turn/token budget; operation timeouts still apply. Custom positive
integer limits remain available. Programmatic runs use
`WebArenaProEnvArgs.max_steps`, with 50 as the default and -1 for unlimited;
set it on each entry in `benchmark.env_args_list` before constructing the
study to override it.

The leaderboard will report results separately at **50 steps, 100 steps, and
unlimited**. The **50- and 100-step scores can be derived from unlimited runs**
using the DAG evaluations recorded at those cutoffs. BrowserGym/AgentLab
automatically runs the task DAG after actions **50 and 100 and on the final
state** when the agent finishes or exhausts its budget, including current
backend checks and any configured LLM fallback. Each evaluation uses the live
state and trajectory available at that step. The run continues afterward,
even if a cutoff receives full credit, and checkpoint scores do not add to the
final episode reward. If a cutoff coincides with the final state, it is
evaluated once. A 100-step run also captures the 50-step score.

Separate agent runs at all three budgets are not required. If a task finishes
earlier, its graded final state supplies the remaining cutoffs within the
original run limit, including both finite cutoffs for unlimited runs.
Derived scores require the saved cutoff evaluations. Report both the original
run limit and the scoring cutoff for derived scores, and compare scores at
the same cutoff.

BrowserGym/AgentLab stores each cutoff's DAG results, trace, and judge evidence
in the step artifacts. Each task's `summary_info.json` also includes
`max_steps` (-1 for unlimited) and `step_budget_scores`, keyed by `"50"`,
`"100"`, and `"unlimited"` when available. The unlimited entry records the
graded final state of an unlimited run. Each entry contains `score`, `success`
(full credit), and `evaluated_at_step`. Use the `success` values to calculate
SR at each cutoff, with the reported task denominator. When a supported budget
cannot be evaluated, its entry has `status: "unavailable"`, null `score`,
`success`, and `evaluated_at_step`, and a reason. It also identifies the last
actual evaluation available before that cutoff. Report evaluation coverage
separately; an unavailable result is not a newly measured zero or a pass.
A run that fails after a checkpoint retains completed cutoff scores and marks
an unevaluated unlimited result unavailable. Older summaries may omit these
entries entirely.
Resuming a run preserves completed cutoff evaluations without rerunning their
judges during browser replay.

If an episode ends early while its state remains evaluable, the final DAG
grade supplies later cutoffs within the original run limit. Raw summaries
retain the most recent actual grade in `cum_reward`, with `score_provenance`
distinguishing a terminal grade from an earlier evaluation. They do not take
the maximum historical score or invent a final grade after browser failure.
CLI output marks a historical score without a terminal evaluation as `UNGRADED`.
Dashboard status, submission status, and study aggregates do not count that
score as episode success, even when the episode ended without an exception.
Errored attempts also remain unsuccessful in the aggregate study summary.
AgentInfo and nested message data are normalized before artifact persistence,
so saving an exception does not replace the original error with a serialization
failure. Literal special-token strings in page text are counted as ordinary
text without altering the text sent to the agent.

To run a chosen budget directly, use one of:

```bash
uv run webarena-pro run --split test --max-steps 50
uv run webarena-pro run --split test --max-steps 100
uv run webarena-pro run --split test --max-steps -1
```

Resuming a study preserves its saved budget unless `--max-steps` is supplied.
Do not infer the budget of historical results from today's default.

In BrowserGym, the final allowed action executes and its resulting state is
graded by the task DAG. If the episode has not otherwise terminated, it ends
with `truncated=True` and retains the DAG score, including partial or full
credit. Budget exhaustion alone therefore does not imply a zero score or a
failed task. A step counts one environment `step(action)` call, not individual
browser clicks or model API calls.

When reporting scores, include:

- The actual maximum steps per task, any per-task overrides, and other agent
  limits that can end an episode earlier. For scores derived from a longer run,
  also include the scoring cutoff, such as 50 or 100 steps from an unlimited run.
- The split and task selection, benchmark release or commit, and completed-task
  count/score denominator, with errors or skipped tasks identified.
- The runner and agent configuration, including agent and judge model
  identifiers, relevant generation settings, and enabled modalities/tools.
- The count of episodes that exhausted the budget, distinguishing those without
  full credit from those that received full credit.

Use the same scoring budget for direct comparisons. If budgets differ, label each
score with its budget and discuss the difference; do not present those scores
as results under equivalent conditions.

## Programmatic BrowserGym Usage

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

benchmark = WebArenaProBenchmark(split="test")
for env_args in benchmark.env_args_list:
    env_args.max_steps = 50  # Set the reporting budget explicitly.
study = WebArenaProStudy(agent_args=[agent], benchmark=benchmark, comment="local run")
study.run(n_jobs=1, parallel_backend="sequential", n_relaunch=1)
```

For parallel runs with per-task reset, prefer the CLI (`--n-jobs N`) so the
runner can spawn isolated worker subprocesses.

### Canvas actions

The default BrowserGym action set includes element-ID actions, coordinate
mouse/keyboard actions, and WebArena-Pro's media actions. Coordinate actions
use pixels in the current screenshot; BrowserGym maps screenshot scaling to
viewport coordinates. Scrolling changes the visible coordinates. For Penpot
pencil strokes, use `mouse_down(x, y)`, successive `mouse_move(x, y)` calls,
then `mouse_up(x, y)`. For a closed path, click each vertex and then the first
vertex again. These literal coordinate actions also participate in the
existing checkpoint replay path.

## Results Viewers

From `webarena-pro-bgym/`, inspect BrowserGym/AgentLab traces with the run
dashboard or the WebArena-Pro XRay extension:

```bash
uv run webarena-pro run dashboard
uv run webarena-pro-agentlab-xray
```

The WebArena-Pro XRay extension adds a **DAG Evaluator** tab for the selected
step's evaluation evidence.

For model request counts, episode totals, and raw completions, see the
[BrowserGym transcript guide](https://github.com/McGill-NLP/webarena-pro/blob/main/webarena-pro-bgym/README.md#agent-model-requests).
