"""Metabase saved-questions (``card``) snapshot provider.

Lists every card visible to the admin, keyed by ``card/{id}``. Used by
tasks that create / modify saved questions (301, 304, 305, 309).
"""

from __future__ import annotations

from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.metabase_common import api_get
from webarena_pro_core.eval.snapshot import Snapshot


class MetabaseCardsProvider(SnapshotProvider):
    """Snapshot Metabase saved questions.

    params:
        archived (bool, optional): include archived cards (default False)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        data = api_get(site, "/api/card")
        if not isinstance(data, list):
            raise ValueError("Metabase card listing is not a list")

        include_archived = bool(params.get("archived", False))
        entries: dict[str, dict] = {}
        for card in data:
            if not isinstance(card, dict):
                raise ValueError("Metabase card is not an object")
            if card.get("archived") and not include_archived:
                continue
            cid = card.get("id")
            if cid is None:
                raise ValueError("Metabase card has no id")
            dataset_query = card.get("dataset_query") or {}
            has_aggregation = False
            query_block = dataset_query.get("query") or {}
            if isinstance(query_block, dict) and query_block.get("aggregation"):
                has_aggregation = True
            entries[f"card/{cid}"] = {
                "name": card.get("name", ""),
                "database_id": card.get("database_id"),
                "display": card.get("display", ""),
                "query_type": card.get("query_type", ""),
                "archived": bool(card.get("archived", False)),
                "creator_id": card.get("creator_id"),
                "has_aggregation": has_aggregation,
                "etag": str(card.get("updated_at", "")),
            }
        return Snapshot(entries=entries)
