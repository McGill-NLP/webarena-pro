"""Generic predicate matcher for snapshot_diff_* check types.

A predicate is a JSON-serializable dict describing a condition on a snapshot
entry. It's reused across all snapshot-diff check types so task authors only
need to learn one vocabulary.

Supported forms::

    {"id_equals":       "agent3"}
    {"id_contains":     "emails"}
    {"id_starts_with":  "documents/"}
    {"id_regex":        "^meeting\\\\d+$"}
    {"attr_equals":     {"summary": "client meeting"}}
    {"attr_contains":   {"summary": "meeting"}}
    {"attr_regex":      {"dtstart": "T110000"}}
    {"type_equals":     "file"}           # shorthand for attr_equals.type

    # Compound:
    {"all": [<pred>, <pred>, ...]}   # AND
    {"any": [<pred>, <pred>, ...]}   # OR
"""

from __future__ import annotations

import re
from typing import Any


def match_entry(entry_id: str, attrs: dict[str, Any], predicate: dict) -> bool:
    """Return True iff ``(entry_id, attrs)`` satisfies the predicate."""
    if not predicate:
        return True  # empty predicate matches everything

    # Compound forms first
    if "all" in predicate:
        return all(match_entry(entry_id, attrs, p) for p in predicate["all"])
    if "any" in predicate:
        return any(match_entry(entry_id, attrs, p) for p in predicate["any"])

    for key, expected in predicate.items():
        if not _check_one(entry_id, attrs, key, expected):
            return False
    return True


def find_matches(
    entries: dict[str, dict[str, Any]],
    predicate: dict,
) -> list[str]:
    """Return ids from ``entries`` matching ``predicate``."""
    return [eid for eid, attrs in entries.items() if match_entry(eid, attrs, predicate)]


# ---------------------------------------------------------------------------
# Per-key dispatch
# ---------------------------------------------------------------------------


def _check_one(entry_id: str, attrs: dict[str, Any], key: str, expected: Any) -> bool:
    match key:
        case "id_equals":
            return entry_id == expected
        case "id_contains":
            return str(expected) in entry_id
        case "id_starts_with":
            return entry_id.startswith(str(expected))
        case "id_ends_with":
            return entry_id.endswith(str(expected))
        case "id_regex":
            return re.search(str(expected), entry_id) is not None
        case "type_equals":
            return attrs.get("type") == expected
        case "attr_equals":
            return all(attrs.get(k) == v for k, v in expected.items())
        case "attr_contains":
            return all(
                isinstance(attrs.get(k), (str, list)) and v in attrs[k]
                for k, v in expected.items()
            )
        case "attr_regex":
            for k, pattern in expected.items():
                val = attrs.get(k)
                if not isinstance(val, str):
                    return False
                if re.search(pattern, val) is None:
                    return False
            return True
        case _:
            # Unknown key - treat as no-match so typos fail loudly in tests.
            return False
