# WebArena-Pro

WebArena-Pro is a self-hosted browser-agent benchmark with 400 tasks across
20 websites. Its shared Core runtime powers BrowserGym/AgentLab, Harbor, and
external MCP-connected agents, with isolated website state and tiered DAG
evaluation.

## Start here

| Goal | Guide |
|---|---|
| Run BrowserGym/AgentLab studies | [Getting started](getting-started.md), then [running agents](running-agents.md) |
| Run existing Harbor agents | [Harbor integration](harbor.md) |
| Connect another agent or orchestrator | [Browser and media MCP runtime](mcp.md) |
| Understand the benchmark and package boundaries | [Benchmark overview](benchmark.md) |
| Configure websites, URLs, and resets | [CLI](cli.md) and [resets](reset.md) |
| Understand scores and media tools | [Evaluators](evaluators.md) and [media](media.md) |

## Running agents

```{toctree}
:maxdepth: 2

getting-started
benchmark
running-agents
mcp
running-mcp-agents
running-harbor-agents
harbor
```

## Configuration and reference

```{toctree}
:maxdepth: 2

cli
evaluators
evaluator-trust-audit
evaluator-stability
evaluator-images
media
reset
api/index
```
