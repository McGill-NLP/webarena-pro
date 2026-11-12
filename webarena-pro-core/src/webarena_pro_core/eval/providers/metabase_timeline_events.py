"""Metabase timeline-events snapshot provider.

Flattens every event under every timeline into a single snapshot keyed by
``event/{id}``. Each entry carries a pre-computed ``days_from_now``
attribute so tasks can assert relative-time scheduling (e.g. "7 days from
today") with the existing ``attr_equals`` predicate - no new predicate
type required.

Used by task 302 (schedule event one week from today).
"""

from __future__ import annotations

from datetime import datetime, timezone

from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.metabase_common import api_get
from webarena_pro_core.eval.snapshot import Snapshot


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


class MetabaseTimelineEventsProvider(SnapshotProvider):
    """Snapshot Metabase timeline events.

    params: (none)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        timelines = api_get(site, "/api/timeline", params={"include": "events"})
        if not isinstance(timelines, list):
            raise ValueError("Metabase timeline listing is not a list")

        now = datetime.now(tz=timezone.utc)
        entries: dict[str, dict] = {}
        for tl in timelines:
            if not isinstance(tl, dict):
                raise ValueError("Metabase timeline is not an object")
            events = tl.get("events")
            if not isinstance(events, list):
                raise ValueError("Metabase timeline has no event list")
            for ev in events:
                if not isinstance(ev, dict):
                    raise ValueError("Metabase timeline event is not an object")
                eid = ev.get("id")
                if eid is None:
                    raise ValueError("Metabase timeline event has no id")
                ts = ev.get("timestamp", "")
                dt = _parse_iso(ts)
                days_from_now: int | None = None
                if dt is not None:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    days_from_now = (dt - now).days
                entries[f"event/{eid}"] = {
                    "name": ev.get("name", ""),
                    "description": ev.get("description", ""),
                    "timestamp": ts,
                    "days_from_now": days_from_now,
                    "timeline_id": tl.get("id"),
                    "collection_id": tl.get("collection_id"),
                    "archived": bool(ev.get("archived", False)),
                    "etag": str(ev.get("updated_at", "")),
                }
        return Snapshot(entries=entries)
