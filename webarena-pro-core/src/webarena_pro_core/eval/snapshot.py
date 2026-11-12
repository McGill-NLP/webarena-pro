"""Generic state snapshot + diff primitives for eval.

A ``Snapshot`` is a flat mapping ``entry_id -> attributes``. Environment-
specific providers (see ``eval/providers/``) know how to produce one from a
live backend; the diff logic here is pure and works uniformly on all of them.

Design goals:
- **Pure data / no HTTP.** Trivially unit-testable.
- **Stable versioning key.** Each entry should carry an ``etag`` (or ``version``)
  so content changes are detectable without downloading the payload.
- **JSON roundtrippable.** Snapshots are persisted to ``exp_dir/baselines.json``
  for debug/repro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SnapshotUnavailableError(ValueError):
    """A diff cannot be computed because a required snapshot fetch failed."""


@dataclass
class Snapshot:
    """Flat mapping ``entry_id -> {etag, type?, ...extras}``.

    ``entry_id`` is whatever uniquely identifies a resource in the backend:
    - WebDAV: relative path (``"documents/memo.docx"``)
    - CalDAV: VEVENT UID
    - Talk: room token
    - OCS users: username
    """

    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    # An unavailable snapshot is not evidence of an empty collection.
    error: str | None = None

    def diff(self, other: "Snapshot") -> "SnapshotDiff":
        """Compute the change from ``self`` (baseline) to ``other`` (current).

        An entry is ``changed`` if it exists in both but its ``etag`` (or
        ``version``) differs. Entries without a version key are compared by
        the whole attribute dict.
        """
        errors = [
            f"{phase} snapshot unavailable: {snapshot.error}"
            for phase, snapshot in (("baseline", self), ("current", other))
            if snapshot.error is not None
        ]
        if errors:
            raise SnapshotUnavailableError("; ".join(errors))

        a_ids = set(self.entries)
        b_ids = set(other.entries)

        added = sorted(b_ids - a_ids)
        removed = sorted(a_ids - b_ids)

        changed: list[str] = []
        unchanged: list[str] = []
        for eid in sorted(a_ids & b_ids):
            if _entry_version(self.entries[eid]) != _entry_version(other.entries[eid]):
                changed.append(eid)
            else:
                unchanged.append(eid)

        return SnapshotDiff(
            added=added,
            removed=removed,
            changed=changed,
            unchanged=unchanged,
            baseline=self,
            current=other,
        )

    def to_json(self) -> dict:
        data = {"entries": self.entries}
        if self.error is not None:
            data["error"] = self.error
        return data

    @classmethod
    def from_json(cls, data: dict) -> "Snapshot":
        return cls(entries=dict(data.get("entries", {})), error=data.get("error"))


@dataclass
class SnapshotDiff:
    """Result of ``baseline.diff(current)``.

    ``added``/``removed``/``changed``/``unchanged`` are lists of entry ids.
    ``baseline`` and ``current`` refs are carried for attribute lookups by
    check evaluators (e.g. "does the new event's summary contain X").
    """

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    baseline: Snapshot | None = None
    current: Snapshot | None = None

    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def added_entries(self) -> dict[str, dict]:
        if self.current is None:
            return {}
        return {eid: self.current.entries[eid] for eid in self.added}

    def removed_entries(self) -> dict[str, dict]:
        if self.baseline is None:
            return {}
        return {eid: self.baseline.entries[eid] for eid in self.removed}

    def to_json(self) -> dict:
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": list(self.changed),
            "unchanged_count": len(self.unchanged),
        }


def build_snapshot_bundle(baseline: Snapshot, current: Snapshot) -> dict:
    """Keep fetch errors explicit in the evidence passed to DAG evaluators."""
    bundle = {"baseline": baseline, "current": current, "diff": None}
    try:
        bundle["diff"] = baseline.diff(current)
    except SnapshotUnavailableError as exc:
        bundle["error"] = str(exc)
    return bundle


def _entry_version(entry: dict) -> Any:
    """Extract a comparable version from an entry.

    Prefer ``etag``, fall back to ``version``, fall back to the whole dict.
    """
    if "etag" in entry:
        return entry["etag"]
    if "version" in entry:
        return entry["version"]
    return tuple(sorted(entry.items()))
