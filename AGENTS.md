# Repository guidance

These instructions apply throughout the repository. Check for a more specific
`AGENTS.md` before editing a subdirectory, and follow its additional guidance.
Inspect the working tree before making changes and preserve unrelated work.

## Repository map

| Path | Responsibility |
|---|---|
| `webarena-pro-core/` | Framework-neutral task loading, website registry, Docker/nginx lifecycle, resets, evaluators, sync/async autologin and UI evidence, and the `webarena-pro` CLI |
| `webarena-pro-media/` | Independent media capture, processing, and transcription with sync and async APIs |
| `webarena-pro-bgym/` | BrowserGym/AgentLab integration, supervised study execution, checkpoints, and run dashboard |
| `webarena-pro-mcp/` | Agent-independent browser/media MCP service and private Core evaluation bridge |
| `webarena-pro-harbor/` | Native Harbor task exporter, deployment configuration, and private result collection/verifier |
| `websites/` | Individual benchmark applications, seed data, and site-specific tests |
| `docs/source/` | Sphinx documentation for runtime behavior and public interfaces |
| `.github/workflows/` | CI setup and test commands for each package and selected websites |

Keep shared runtime behavior in Core. Core must remain usable without importing
BrowserGym or AgentLab.
Website projects have different stacks: read the site's README and build/test
configuration before changing its application or fixtures.

## Setup and validation

Use Python 3.12 and `uv` for a common environment across the Python packages.
There is no root Python project: run commands
from the relevant package directory. Keep lockfiles unchanged unless dependency
changes are part of the work; BrowserGym, MCP, and Harbor use editable sibling dependencies.

For BrowserGym, from `webarena-pro-bgym/`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked pytest -q tests
```

For Core, from `webarena-pro-core/`, install the test and optional verifier dependencies:

```bash
uv sync --python 3.12 --locked --group dev --extra verifier
uv run --locked python -m playwright install chromium
uv run --locked pytest -q tests
```

For MCP, from `webarena-pro-mcp/`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-mcp install
WP_MCP_BROWSER_TESTS=1 uv run --locked pytest -q tests
```

The MCP browser tests use local fixtures, Chromium, and the pinned Node runtime;
they need no Docker or model credentials. External orchestrators own task
selection, website provisioning/reset, agent execution, and retries. MCP serves
one browser session and enforces tool/action limits; keep agent code outside it.

For Harbor, from `webarena-pro-harbor/`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked webarena-pro-mcp install
WP_HARBOR_BROWSER_TESTS=1 uv run --locked pytest -q tests
```

The Harbor browser tests need Node 20 or newer. Native Harbor trials additionally
need Docker on Linux, the built runtime image, and the supported Harbor revision
documented in the package README. Run them on an isolated deployment; each trial
owns its website sidecars and private evaluator artifacts.

For `webarena-pro-media/`:

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked python -m playwright install chromium
uv run --locked pytest -q tests
uv build
```

Core's browser helpers live in `webarena-pro-core/src/webarena_pro_core/autologin/`
and `webarena-pro-core/src/webarena_pro_core/ui_evidence/`. Maintain each
`sync_api.py` and regenerate the native async APIs with Core's
`scripts/generate_autologin_async.py` and `scripts/generate_ui_evidence_async.py`;
verify both with `--check`. Core evaluators consume serialized UI facts, never
live browser objects. Keep URL/login-route metadata in `website_metadata`.
Playwright and evaluator libraries are required Core dependencies. Browser
imports remain lazy: loading tasks and evaluating captured/backend facts must
not initialize Playwright or import Media. Core's tests include the browser
fixtures for both helpers; Media remains independent of Core.

Media regression fixtures need FFmpeg/FFprobe on PATH.

- Run the affected tests first, then the relevant package suites for broader
  changes. Shared Core changes may require checks in downstream integrations.
- Add or update regression coverage when behavior changes. For task-data edits,
  check task loading, split membership, and the affected evaluator tests.
- Browser integration tests need Chromium (`uv run python -m playwright install
  chromium`). Media tests may need system `ffmpeg`/`ffprobe`; local transcription
  uses `webarena-pro-media[local]`. Live website checks need an available Docker
  daemon and the appropriate site fixtures.
- Report missing prerequisites, failures, and skipped tests accurately. Do not
  weaken assertions or change behavior to hide an environment limitation.
- Preserve nearby formatting and keep the diff focused. There is no shared
  repository-wide formatter command; use package-specific configuration.
- Run `git diff --check` before finishing. When package data or build metadata
  changes, build the affected package with `uv build` from its directory and
  inspect the archive contents.

## Supported runtime entry points

Use the installed CLI from `webarena-pro-bgym/`:

```bash
uv run webarena-pro env list
uv run webarena-pro run --help
uv run webarena-pro run --split dev --list
uv run webarena-pro run --split test --list
uv run webarena-pro run dashboard --help
```

`--list` inspects task selection without starting an agent or containers.
`--dry-run` can perform live setup and evaluator checks. Actual runs require
the selected model's credentials and the necessary environments, and normally
reset website state. Start only the sites needed for the requested work.

The old standalone evaluation/dashboard wrappers and
`webarena_pro_bgym.verifier` compatibility package were removed. Use
`webarena-pro run`, `webarena-pro run dashboard`, and the Core verifier modules.
`run_eval_cli.py` still contains shared execution helpers, and
`legacy_recovery.py` still handles older studies; their names do not make them
unused. Trace imports and callers before removing code.

## Task and evaluation invariants

- Active configs live under `webarena-pro-core/src/webarena_pro_core/config/`.
  Website `*.raw.json` files contain 300 Test tasks; `splits/dev.json` contains
  100 Dev tasks plus sampling provenance. The sets are disjoint, and each task
  appears once with an embedded evaluation DAG under `eval`.
- Keep task IDs unique and zero-padded; do not renumber unrelated tasks or reuse
  retired IDs. Preserve intents, accounts, DAG criteria, and sampling metadata
  unless the requested change calls for modifying them. Update tests and docs
  together when intentionally changing the corpus or split contract.
- Use `sites` and per-site `login_usernames` for task setup. The first site is
  the primary site. Do not add the ignored JSON fields `start_url` or
  `require_reset`: URLs come from deployment settings, and reset policy comes
  from runtime controls. See the [task configuration guide](webarena-pro-core/src/webarena_pro_core/config/README.md).
- Preserve DAG dependencies and equal partial-credit behavior. Tiered
  evaluation trusts definitive Tier 0 results, including failures; a failed
  deterministic check must not become a pass by falling through to an LLM.
  Heuristic and inconclusive results follow each strategy's trust policy.
  There is no additional whole-task rubric judge.
- Keep step budgets, cutoff scores, terminal grading, and checkpoint resume
  behavior consistent with the [running-agents guide](docs/source/running-agents.md).
  Resume must preserve compatible saved work; a fresh retry is an explicit
  runtime choice.

## Runtime changes and documentation

- Preserve per-worker URL, container, and reset isolation. Use the shared Core
  URL/reset helpers instead of hardcoded hosts, ports, or process-global state.
  Check downstream integrations when changing these contracts.
- Keep benchmark launchers, CLI forwarding, dashboard process detection, tests,
  and examples aligned when entry points change.
- Keep local `.env` files, provider credentials, evaluator tokens, browser auth
  state, and generated run artifacts out of commits. Preserve deterministic
  website seed fixtures when they are part of the tracked benchmark.
- Update the relevant package README or `docs/source/` page alongside public
  behavior changes. Build Sphinx documentation with `make docs-build` from the
  repository root; generated output is under `docs/_build/`.
- Check the Git remote and target branch before pushing or opening a PR. The
  public repository is `McGill-NLP/webarena-pro`; another checkout may point
  at an internal mirror. Describe the resulting behavior, validation, and any
  compatibility changes in the PR.

Further references: [CLI](docs/source/cli.md),
[evaluators](docs/source/evaluators.md), [resets](docs/source/reset.md),
[media](docs/source/media.md), and [BrowserGym](webarena-pro-bgym/README.md).
