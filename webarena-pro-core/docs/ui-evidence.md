# Core UI evidence collection

Read-only sync and async Playwright collectors for Core evaluation. Core defines
required probes and grades captured facts in `eval.ui_evidence`; the separate
`ui_evidence` module performs browser I/O. Core includes Playwright and evaluator
dependencies by default.
Install the Chromium binary for browser capture.
No verdicts, credentials, or browser handles enter the evidence record.

```python
from webarena_pro_core.eval.ui_evidence import build_ui_evidence_plan
from webarena_pro_core.ui_evidence.async_api import collect_ui_evidence

plan = build_ui_evidence_plan(task.evaluation)
evidence = await collect_ui_evidence(page, plan, step=5)
```

Use `sync_api.collect_ui_evidence` without `await` for synchronous Playwright.
Keep the selected page stable while capturing. Navigation, document reloads,
and changes to the selected page's tab index during capture invalidate the
snapshot. Collect immediately before grading, outside the agent action loop.

Supported probes are element counts, the first matching element's inner text,
and bounded visible Nextcloud Talk reaction facts. Playwright selector semantics
(including `:visible`) are retained. Nextcloud records contain message IDs, emoji
text, and selected state; Core binds them to backend-verified conversation,
account, poll, vote, and timing evidence. The current DOM is captured, not unseen
or virtualized history. Absent rendered elements preserve the existing UI-check
semantics; capture failures and truncated results are inconclusive.

Each record includes a schema version, evaluation ID, step, tab index, URL,
document identity, capture time/status, collection-plan digest, and probe results.
Limits: 128 unique probes, 16,384 characters per text result, 512 reaction
records, and 4 MiB per serialized capture. Errors contain exception types only.
Save `evidence.model_dump(mode="json")` in private evaluation artifacts, never in
the agent's observations. Use Core's `restore_ui_evidence` for trusted saved
evaluation records; old traces without records cannot recover DOM evidence from
screenshots or accessibility text.

## Development

Run from `webarena-pro-core/`.

```bash
uv sync --python 3.12 --locked --group dev
uv run --locked python -m playwright install chromium
uv run --locked pytest -q tests
uv run --locked python scripts/generate_ui_evidence_async.py --check
uv build
```

Maintain `sync_api.py` and `_shared.py`; generate the async flow with
`python scripts/generate_ui_evidence_async.py`. Browser I/O stays on its owning event loop.
