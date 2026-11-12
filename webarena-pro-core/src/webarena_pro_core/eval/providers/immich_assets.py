"""Active Immich photos, keyed by stable asset ID for preservation checks."""
from __future__ import annotations

import json
from datetime import datetime

from webarena_pro_core.eval.backend_state import BackendStateEvaluator
from webarena_pro_core.eval.dag import EvalContext
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.snapshot import Snapshot


class ImmichAssetsProvider(SnapshotProvider):
    """Snapshot active photos; ``exclude_year`` omits the task's target year.

    Use the normal authenticated API template so per-worker URLs and login
    behavior match backend checks. A failed or partial listing is unavailable
    evidence, never an empty library. No adapter-specific code is required.
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        if site != "immich":
            raise ValueError("immich_assets requires the immich site")
        exclude_year = params.get("exclude_year")
        if exclude_year is not None and (type(exclude_year) is not int or not 1 <= exclude_year <= 9999):
            raise ValueError("exclude_year must be a calendar year")
        context = EvalContext(task_config={"sites": [site]})
        evaluator = BackendStateEvaluator()
        entries: dict[str, dict] = {}
        seen: set[str] = set()
        page = 1
        while page <= 10000:
            spec = evaluator._resolve_request({
                "api": "search_metadata",
                "params": {"body": json.dumps({"size": 1000, "page": page, "type": "IMAGE"})},
            }, context)
            response = evaluator._send(spec, context)
            response.raise_for_status()
            data = response.json()
            assets = data.get("assets") if isinstance(data, dict) else None
            if not isinstance(assets, dict) or not isinstance(assets.get("items"), list):
                raise ValueError("Immich asset listing has no items array")
            items = assets["items"]
            if assets.get("count") != len(items) or assets.get("total") != len(items) or "nextPage" not in assets:
                raise ValueError("Immich asset page is incomplete")
            for asset in items:
                if not isinstance(asset, dict):
                    raise ValueError("Immich asset is not an object")
                asset_id = asset.get("id")
                if not isinstance(asset_id, str) or not asset_id or asset_id in seen:
                    raise ValueError("Immich asset ID is missing or repeated")
                seen.add(asset_id)
                if asset.get("type") != "IMAGE" or asset.get("isTrashed") is not False:
                    raise ValueError("Immich active-photo query returned an unexpected asset")
                taken = asset.get("localDateTime")
                if not isinstance(taken, str):
                    raise ValueError("Immich photo has no capture date")
                year = datetime.fromisoformat(taken.replace("Z", "+00:00")).year
                if year != exclude_year:
                    entries[asset_id] = {"etag": asset.get("checksum", ""), "year": year}
            next_page = assets["nextPage"]
            if next_page is None:
                return Snapshot(entries=entries)
            if not items or str(next_page) != str(page + 1):
                raise ValueError("Immich pagination did not advance to the next page")
            page += 1
        raise ValueError("Immich asset listing exceeded the pagination limit")
