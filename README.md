# WebArena-Pro 🌐

A self-hosted benchmark for browser agents: **400 tasks across 20 websites**,
with **100 dev / 300 test tasks**, multimodal interactions, and tiered DAG
evaluation. Run agents through BrowserGym/AgentLab, Harbor, or an external
agent connected to the browser/media MCP service.

https://github.com/user-attachments/assets/a66d1924-ad3e-4a31-a13c-7aad175b2549

## Choose an integration

| Integration | Use it to | Start here |
|---|---|---|
| BrowserGym/AgentLab | Run AgentLab studies with supervised workers and a study dashboard | [Getting started](docs/source/getting-started.md) |
| Harbor | Export native Harbor tasks and run existing MCP-capable agents | [Harbor integration](docs/source/harbor.md) |
| MCP | Connect your own agent/orchestrator to browser and media tools with Core grading | [MCP runtime](docs/source/mcp.md) |

## Quickstart

This quickstart uses BrowserGym/AgentLab. You need **Python 3.12+**, **Docker**, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/McGill-NLP/webarena-pro.git
cd webarena-pro/webarena-pro-bgym
uv sync --python 3.12 --locked
uv run python -m playwright install chromium
```

Preview tasks without starting an agent or containers:

```bash
uv run webarena-pro run --split dev --site nextcloud --list
```

Set your agent and evaluator [API credentials](docs/source/getting-started.md#model-credentials),
then run a small selection. The runner starts the required websites automatically:

```bash
uv run webarena-pro run --split dev --site nextcloud --task 172,173 --max-steps 50
```

In another terminal, run `uv run webarena-pro run dashboard` from
`webarena-pro-bgym/` and open <http://127.0.0.1:8765> to follow progress.

For installation details, environment controls, and full dev/test runs, see
[Getting started](docs/source/getting-started.md).

## Documentation

| Guide | Contents |
|---|---|
| [Benchmark overview](docs/source/benchmark.md) | Task splits, package architecture, website catalog, and integration choices |
| [Running agents](docs/source/running-agents.md) | BrowserGym parallel runs, recovery, step budgets, and reporting |
| [CLI reference](docs/source/cli.md) | Website lifecycle, dashboards, and deployment URLs |
| [Run Harbor agents](docs/source/running-harbor-agents.md) | Export tasks, launch an existing agent, and inspect results |
| [Run MCP-connected agents](docs/source/running-mcp-agents.md) | Prepare a session, connect an external agent, and finalize grading |
| [Evaluators](docs/source/evaluators.md) | DAG scoring, judge configuration, and backend authentication |
| [Media](docs/source/media.md) · [Resets](docs/source/reset.md) | Multimodal actions and environment state management |
| [Task configuration](webarena-pro-core/src/webarena_pro_core/config/README.md) | Task fields and embedded evaluation DAGs |

Package guides: [Core](webarena-pro-core/README.md) ·
[Autologin](webarena-pro-core/docs/autologin.md) ·
[Media](webarena-pro-media/README.md) ·
[UI evidence](webarena-pro-core/docs/ui-evidence.md) ·
[BrowserGym/AgentLab](webarena-pro-bgym/README.md) ·
[Playwright MCP](webarena-pro-mcp/README.md) ·
[Harbor](webarena-pro-harbor/README.md).
See the [documentation index](docs/source/index.md) for all guides.
[AGENTS.md](AGENTS.md) covers development setup and validation commands.

## Citation

If you use WebArena-Pro in your research, please cite our
[paper](https://arxiv.org/abs/2611.17955):

```bibtex
@misc{kerboua2026webarenaproheterogeneousmultimodalreproducible,
  title={WebArena-Pro: A Heterogeneous, Multimodal, Reproducible Benchmark for Web Agents},
  author={Imene Kerboua and Fatemeh Pesaran Zadeh and Xing Han Lù and Weijian Qi
          and Alexander Miller and Junyi Song and Yunjia Tian and Dongjin Kang
          and Seyeon Choi and Marzia Nouri and Ewen Gueguen and Matteo Boglioni
          and Fengyuan Liu and Zeyi Liao and Mengqi Yuan and Yue Li
          and Alexandre Lacoste and Alexandre Drouin and Spandana Gella
          and Huan Sun and Gunhee Kim and Siva Reddy},
  year={2026},
  eprint={2611.17955},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2611.17955},
}
```
