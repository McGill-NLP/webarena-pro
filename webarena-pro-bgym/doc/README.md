# WebArena-Pro Architecture

This document summarizes WebArena-Pro's package boundaries and the
BrowserGym/AgentLab execution path. See the
[package architecture](../../docs/source/benchmark.md#package-architecture)
for the companion MCP and Harbor integrations.

## Package Split

The BrowserGym execution path uses three of the repository's five Python packages:

- `webarena-pro-core` owns the environment runtime: website registry, URL
  construction, Docker container lifecycle, nginx reverse-proxy routing,
  task config loading, credentials, sync/async autologin and UI evidence,
  package-level reset, and reusable DAG evaluators/providers.
- `webarena-pro-bgym` adapts those tasks and websites into BrowserGym and
  AgentLab: benchmark loading, task setup/teardown, episode execution, evaluator
  integration, traces, dashboards, and supervised study runners.
- `webarena-pro-media` provides independent sync/async media capture, processing,
  and transcription. BrowserGym depends on it directly; Core does not.

The other packages, `webarena-pro-mcp` and `webarena-pro-harbor`, support
external agents and native Harbor trials. See the canonical
[package map](../../docs/source/benchmark.md#choose-an-integration) for all five
packages. `websites/` contains the applications that agents interact with.

Core operates independently of BrowserGym and AgentLab. Integrations reuse
Core's task and runtime contracts.

## URL And Proxy Model

The default URL mode is subdomain mode:

```text
http://<site>--<run-or-worker-hash>.<domain>:<proxy-port>
```

For example:

```text
http://mattermost--w3.localhost:8080
```

The subdomain is not a separate deployment by itself. In local/subdomain mode,
a shared nginx container is the public ingress. It listens on the configured
web server port, reads the request `Host` header, and proxies traffic to the
matching website container on the Docker network.

```text
Browser or RL worker
  -> http://jobportal--w2.example.com:8080
  -> nginx reverse proxy
  -> Docker network
  -> jobportal-w2 container
```

Website containers are labeled with site name, experiment hash, and upstream
port. The nginx manager discovers those labels and regenerates proxy routes
when containers are started, stopped, or reset.

Set `WP_URL_MODE=port` to bypass nginx and expose each website on a direct host
port such as `http://localhost:4601`. Subdomain mode is better when many worker
instances need to share one public endpoint.

## Reset Model

Per-task reset is enabled by default. BrowserGym calls reset during
`WebArenaProTask.setup()` before login, baseline collection, and navigation.

Reset backend selection is controlled by `WP_RESET_BACKEND`:

- `auto` uses fast state restore for lightweight sites and container recreate
  for heavier sites.
- `state` forces the package-level in-place restore path.
- `container` forces Docker stop/remove/recreate from the seed image.
- `none` skips per-task reset.

State restore can happen through a website reset endpoint such as `/api/reset`
or through a Docker-exec snapshot restore for sites that do not expose a URL
reset endpoint. Container recreate needs Docker access on the environment host.

For a fresh worker slot, a state-reset site may not have a worker-specific
container yet. BrowserGym bootstraps that case by recreating the container once,
then later tasks on the same slot use the faster state restore path.

## BrowserGym Task Flow

`WebArenaProBenchmark` loads raw task configs from `webarena-pro-core` and
turns them into BrowserGym environment arguments. Each task run follows this
shape:

1. Resolve selected website sites and URLs.
2. Reset every selected site.
3. Wait for websites to become ready.
4. Log into required sites with core auto-login helpers.
5. Fetch baseline snapshots for evaluators.
6. Navigate the browser to the task start URL.
7. Run the agent episode.
8. Evaluate state changes and rubric/DAG conditions.
9. Stop only container-reset sites during teardown.

This lets task definitions, credentials, and URLs stay centralized in `core`
while BrowserGym owns the episode mechanics.

## AgentLab Integration

`WebArenaProStudy` and `WebArenaProExpArgs` wrap AgentLab study execution:

- AgentLab creates agents from `AgentArgs`.
- BrowserGym creates the environment and runs reset/setup.
- AgentLab records traces, screenshots, logs, summaries, and relaunch metadata.
- WebArena-Pro evaluators compute task scores from browser state and provider
  snapshots.

Normal CLI execution uses supervised worker subprocesses and a shared FIFO
queue, including the default `--n-jobs 1`. Every worker receives isolated website
URLs, container names, ports, and a `WP_EXP_HASH` namespace. Workers prepare sites
on demand during task reset; optional prewarming prepares a standby slot.
The coordinator journals task transitions and replaces unsafe workers after
fatal operation failures.

Queued resume restores compatible saved agent decisions by resetting sites and
replaying supported actions before making new decisions. See
[resume and relaunch](../README.md#resume-and-relaunch) for restrictions and the
explicit fresh-retry option.

Programmatic `study.run(..., parallel_backend="sequential")` remains in-process.
The CLI also uses one in-process worker with `--no-reset-per-task`, which reuses
existing site state and disables supervised recovery/checkpoint replay.
`--no-autostart` only controls preflight startup; it does not turn off the
normal supervised reset path. See [remote execution](../README.md#remote-environment-hosts).

AgentLab in-process parallel backends remain blocked when reset is enabled
because concurrent tasks would mutate the same process environment and reset
state.

## HPC Deployment Model

For HPC/RL training, the clean model is to run websites on a separate
environment host and let the HPC workers access them by URL:

```text
Remote / worker processes
  -> website URLs over the network

Environment host
  -> Docker containers
  -> nginx reverse proxy
  -> reset endpoints or container lifecycle operations
```

URL-reset sites can be restored remotely through their public URL. Docker-exec
snapshot restore and container recreate still need Docker access on the
environment host unless a separate reset service exposes those operations over
HTTP.
