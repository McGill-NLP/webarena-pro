# Getting started

This guide installs and runs the BrowserGym/AgentLab integration. For other
agent runners, start with [Harbor](harbor.md) or the [MCP runtime](mcp.md).
The [benchmark overview](benchmark.md#choose-an-integration) explains the
package boundaries.

## Requirements and installation

| Requirement | Purpose |
|---|---|
| Python 3.12+ | Runs Core and BrowserGym/AgentLab |
| Docker | Hosts the isolated website environments |
| [uv](https://docs.astral.sh/uv/) | Installs and runs the Python workspaces |
| Model-provider credentials | Authenticates the selected agent and LLM evaluator |

```bash
git clone https://github.com/McGill-NLP/webarena-pro.git
cd webarena-pro/webarena-pro-bgym
uv sync --python 3.12 --locked
uv run python -m playwright install chromium
```

Run the remaining commands from `webarena-pro-bgym/`. Omit `uv run` if
`webarena-pro` is already installed in your active environment.

## Model credentials

Set the API key for your chosen agent before launching a run. The default
agent, `gemini/gemini-3.5-flash`, uses `GEMINI_API_KEY`. Pass `--agent-model`
to choose another configured model and provide its corresponding credential.

The default LLM evaluator uses `OPENROUTER_API_KEY`, independently of the
agent model. See [judge configuration](evaluators.md#strategy-implementations)
for model and provider overrides.

Backend evaluation authentication is provisioned automatically for local
runs. If websites and agents run on separate hosts or under different users,
configure the shared token as described in
[backend evaluation authentication](evaluators.md#backend-evaluation-authentication).

## Check one environment

List registered environments, then start one site and create its authenticated
browser state:

```bash
uv run webarena-pro env list
uv run webarena-pro env start nextcloud --login
```

Preview the task selection without starting an agent or containers:

```bash
uv run webarena-pro run --split dev --site nextcloud --list
```

Then check setup and evaluators against the live environment:

```bash
uv run webarena-pro run --split dev --site nextcloud --dry-run
```

Start only the sites you need. Normal benchmark runs prepare isolated worker
environments during per-task reset. `--no-autostart` only affects preflight;
see [remote execution](running-agents.md#use-a-deployment-server-url) before
reusing existing sites, and [state reset behavior](reset.md) for reset controls.

## Run agents

Start with a small selection:

```bash
uv run webarena-pro run --split dev --site nextcloud --task 172,173 --max-steps 50
```

For a full Dev run, use two terminals from `webarena-pro-bgym/`:

```bash
# Terminal 1: follow workers, tasks, rewards, logs, and DAG traces.
uv run webarena-pro run dashboard

# Terminal 2: run the 100 Dev tasks with four isolated workers.
uv run webarena-pro run --split dev --n-jobs 4 --max-steps 50 --agent-model gemini/gemini-3.5-flash
```

Open the run dashboard at `http://127.0.0.1:8765`. To evaluate the 300 Test
tasks, change `--split dev` to `--split test`. Omitting `--split` selects Test.
Combine `--split`, `--site`, and `--task` to narrow a selection; filters intersect.

New runs default to 50 environment steps per task. See
[step budgets and reporting](running-agents.md#step-budget-and-reporting)
for 50, 100, and unlimited budgets, saved cutoff scores, and comparisons.

## Common commands

| Goal | Command |
|---|---|
| Start selected sites | `uv run webarena-pro env start nextcloud mattermost` |
| Start every site | `uv run webarena-pro env start all` |
| Inspect a site | `uv run webarena-pro env status nextcloud` |
| Open the environment dashboard | `uv run webarena-pro env dashboard` |
| Stop every site and the proxy | `uv run webarena-pro env stop all` |
| Preview the Dev set | `uv run webarena-pro run --split dev --list` |
| Preview the Test set | `uv run webarena-pro run --split test --list` |
| Resume a study | `uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir>` |
| Retry failed tasks from step zero | `uv run webarena-pro run --resume-study ~/agentlab_results/<study_dir> --retry-from-start` |

The environment dashboard manages website containers; the run dashboard
tracks agent studies. See [dashboards](cli.md#dashboards) for both interfaces
and [resume and recovery](running-agents.md#resume-and-recovery) before
restarting an interrupted study.

## Deployment URLs

Subdomain routing is the default, for example
`http://nextcloud--local.localhost:8080`. Use `WP_EXP_HASH` for another
namespace or `WP_URL_MODE=port` for direct host ports. See
[URL configuration](cli.md#url-configuration) and
[remote environment hosting](running-agents.md#use-a-deployment-server-url)
for separate deployment and agent machines.

## Troubleshooting

| Symptom | Check |
|---|---|
| Task selection is empty | Preview with `--list`; site and task filters intersect with the selected split. Tasks `172,173` require `--split dev`. |
| Browser binary is missing | Run `uv run python -m playwright install chromium` from `webarena-pro-bgym/`. |
| Agent or evaluator authentication fails | Check the separate [model credentials](#model-credentials) and [backend token](evaluators.md#backend-evaluation-authentication). |
| Website URLs cannot be reached | Check [URL configuration](cli.md#url-configuration), site status, and [Docker platform settings](cli.md#docker-platform). |
| Website state changes unexpectedly between tasks | Review [reset behavior](reset.md) and the explicit [remote-state configuration](running-agents.md#use-a-deployment-server-url). |
| A study was interrupted | Follow [resume and recovery](running-agents.md#resume-and-recovery) to preserve compatible saved work. |
