"""Read-only synchronous Playwright evidence capture; maintained source."""
from __future__ import annotations

import time
from uuid import uuid4

from webarena_pro_core.eval.ui_evidence import (
    MAX_REACTIONS, MAX_TEXT, UIEvidence, UIEvidencePlan, UIProbeResult,
)
from ._shared import FIRST_TEXT, IDENTITY, REACTION_SELECTOR, REACTIONS


def collect_ui_evidence(page, plan: UIEvidencePlan, *, evaluation_id=None, step=None) -> UIEvidence:
    """Capture a bounded evaluation snapshot without exposing verdicts to agents.

    The caller owns the selected page and must not perform concurrent actions.
    Navigation/reload/tab changes during capture invalidate the whole snapshot.
    Errors contain exception types only, never potentially sensitive DOM text.
    """
    values = dict(
        evaluation_id=evaluation_id or uuid4().hex, step=step,
        captured_at=time.time(), plan_sha256=plan.sha256,
        status="unavailable", results={},
    )
    if page is None:
        return UIEvidence(**values)
    try:
        tab = page.context.pages.index(page)
        before = page.evaluate(IDENTITY)
        identity = dict(tab_id=str(tab), url=before["url"], document_id=before["document"], status="ok")
        # Validate browser-controlled metadata before retaining it: an oversized
        # URL must produce unavailable evidence, not also break the error path.
        UIEvidence(**{**values, **identity})
        values.update(identity)
        for probe in plan.probes:
            try:
                if probe.kind == "count":
                    result = UIProbeResult(probe=probe, status="ok", count=page.locator(probe.selector).count())
                elif probe.kind == "first_text":
                    raw = page.locator(probe.selector).evaluate_all(FIRST_TEXT, MAX_TEXT)
                    result = UIProbeResult(probe=probe, status="truncated" if raw["truncated"] else "ok", text=raw["text"])
                else:
                    raw = page.locator(REACTION_SELECTOR).evaluate_all(REACTIONS, {"records": MAX_REACTIONS, "text": MAX_TEXT})
                    result = UIProbeResult(probe=probe, status="truncated" if raw["truncated"] else "ok", reactions=raw["records"])
                values["results"][probe.key] = result
            except Exception as error:
                values["results"][probe.key] = UIProbeResult(probe=probe, status="error", error=type(error).__name__)
        after = page.evaluate(IDENTITY)
        if after != before or page.context.pages.index(page) != tab:
            values.update(status="stale", results={}, error="Page identity changed during capture")
        return UIEvidence(**values)
    except Exception as error:
        # Also covers closed pages and an oversized aggregate payload.
        values.update(status="error", results={}, error=type(error).__name__)
        return UIEvidence(**values)
