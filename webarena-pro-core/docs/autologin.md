# Core autologin

Site-specific Playwright login, verification and storage-state export, with
explicit synchronous and asynchronous APIs. Website metadata and credentials
are bundled with these helpers in `webarena-pro-core`.

```bash
pip install "webarena-pro-core"
python -m playwright install chromium
```

```python
from webarena_pro_core.autologin.sync_api import ui_login, save_storage_state

ui_login("x-lite", sync_page, username="techvalueinvestor")
save_storage_state("x-lite", ".auth/x-lite.json")
```

```python
from webarena_pro_core.autologin.async_api import ui_login, save_storage_state

await ui_login("x-lite", async_page, username="techvalueinvestor")
await save_storage_state("x-lite", ".auth/x-lite.json")
```

Both modules expose `AutoLogin` with the same configuration and login methods.
Pass the matching Playwright page type. Async readiness callbacks are awaited;
legacy blocking readiness callbacks run in a thread. Login failures propagate,
and temporary login pages close on failure or cancellation.

The sync module is the maintained source for site flows. The checked-in async
module is generated with `python scripts/generate_autologin_async.py`, producing native
async Playwright calls, async context managers, and nonblocking retry waits.
Credentials and configuration logic are shared. CI checks generation freshness
and tests both APIs against the same login fixtures.

From `webarena-pro-core/`: `uv sync --group dev`, then `uv run pytest -q tests`.
Use `python scripts/generate_autologin_async.py --check` to verify generated source.
