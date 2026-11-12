"""Metabase dashboards snapshot provider.

Produces two entry layers in a single snapshot:

1. ``dashboard/{id}`` - one entry per dashboard with name/archived/card_count.
2. ``dashboard/{id}/dashcard/{row}_{col}`` - one entry per dashcard, flattened
   from the nested ``dashcards`` array. This lets predicates filter cards by
   position, text content, or parent dashboard without introducing a new
   nested check type.

Used by tasks 307 (create dashboard with layout) and 308 (add text section).
"""

from __future__ import annotations

from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.metabase_common import api_get
from webarena_pro_core.eval.snapshot import Snapshot


class MetabaseDashboardsProvider(SnapshotProvider):
    """Snapshot Metabase dashboards + their dashcards (flattened).

    params:
        archived (bool, optional): include archived dashboards (default False)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        listing = api_get(site, "/api/dashboard")
        if not isinstance(listing, list):
            raise ValueError("Metabase dashboard listing is not a list")

        include_archived = bool(params.get("archived", False))
        entries: dict[str, dict] = {}

        for summary in listing:
            if not isinstance(summary, dict):
                raise ValueError("Metabase dashboard summary is not an object")
            if summary.get("archived") and not include_archived:
                continue
            did = summary.get("id")
            if did is None:
                raise ValueError("Metabase dashboard summary has no id")

            detail = api_get(site, f"/api/dashboard/{did}")
            if not isinstance(detail, dict):
                raise ValueError(f"Metabase dashboard {did} detail is not an object")
            if detail.get("id") != did:
                raise ValueError(f"Metabase dashboard {did} detail has a missing or incorrect id")

            name = detail.get("name", "")
            archived = bool(detail.get("archived", False))
            dashcards = detail.get("dashcards", detail.get("ordered_cards"))
            if not isinstance(dashcards, list):
                raise ValueError(f"Metabase dashboard {did} has no dashcard list")

            entries[f"dashboard/{did}"] = {
                "name": name,
                "archived": archived,
                "card_count": len(dashcards),
                "creator_id": detail.get("creator_id"),
                "etag": str(detail.get("updated_at", "")),
            }

            for dc in dashcards:
                if not isinstance(dc, dict):
                    raise ValueError(f"Metabase dashboard {did} dashcard is not an object")
                row = dc.get("row", 0)
                col = dc.get("col", 0)
                card = dc.get("card") or {}
                if not isinstance(card, dict):
                    card = {}
                vs = dc.get("visualization_settings") or {}
                if not isinstance(vs, dict):
                    vs = {}
                card_text = (
                    vs.get("text") or vs.get("virtual_card", {}).get("text", "")
                    if isinstance(vs.get("virtual_card"), dict)
                    else vs.get("text", "")
                )
                if not card_text and card.get("description"):
                    card_text = card.get("description", "")
                entries[f"dashboard/{did}/dashcard/{row}_{col}"] = {
                    "dashboard_id": did,
                    "dashboard_name": name,
                    "card_id": dc.get("card_id"),
                    "card_name": card.get("name", ""),
                    "card_text": card_text or "",
                    "display": card.get("display", ""),
                    "row": row,
                    "col": col,
                    "size_x": dc.get("size_x", 0),
                    "size_y": dc.get("size_y", 0),
                    "etag": str(dc.get("updated_at", "")),
                }

        return Snapshot(entries=entries)
