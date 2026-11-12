"""Declarative JSON response predicates and correlated collection queries.

No task or website rules belong here. References use explicit scopes, queries
preserve response order, and unavailable evidence raises to backend_state.
"""
from __future__ import annotations

import math

from webarena_pro_core.eval.judge_cache import input_digest


def check_json_predicate(check: dict, data, context, resolved: dict) -> tuple[bool, str]:
    scope = {
        "data": data,
        "context": {"task_start_time_ms": getattr(context, "task_start_time_ms", None)},
        "resolved": resolved,
    }
    for guard in check.get("guards", []):
        if not _predicate(guard["predicate"], scope):
            raise ValueError(f"evidence guard failed: {guard['label']}")
    sizes = {}
    for binding in check.get("bindings", []):
        name = binding["name"]
        if not isinstance(name, str) or not name.isidentifier() or name in scope:
            raise ValueError(f"invalid or duplicate JSON binding: {name!r}")
        scope[name] = _value(binding["value"], scope)
        if isinstance(scope[name], list):
            sizes[name] = len(scope[name])
    passed = _predicate(check["predicate"], scope)
    return passed, f"JSON predicate={passed}; collection_sizes={sizes}; evidence_sha256={input_digest(data)}"


def _value(spec, scope):
    if not isinstance(spec, dict):
        return spec  # JSON scalars and literal arrays.
    if "ref" in spec and set(spec) <= {"ref", "default"}:
        path = spec["ref"]
        if not isinstance(path, str) or not path or any(not part for part in path.split(".")):
            raise ValueError("JSON reference must be a nonempty dotted path")
        value = scope
        for part in path.split("."):
            if not isinstance(value, dict):
                raise ValueError(f"JSON reference {path!r} traverses a non-object")
            if part not in value:
                if "default" in spec:
                    return spec["default"]
                raise ValueError(f"missing JSON reference {path!r}")
            value = value[part]
        return value
    if set(spec) == {"literal"}:
        return spec["literal"]
    if set(spec) == {"query"}:
        return _query(spec["query"], scope)
    if set(spec) == {"upper"}:
        value = _value(spec["upper"], scope)
        if not isinstance(value, str):
            raise ValueError("upper requires text")
        return value.upper()
    raise ValueError(f"unknown JSON value expression: {spec!r}")


def _rows(query, scope):
    items = _value(query["from"], scope)
    if not isinstance(items, list):
        raise ValueError("JSON query source must be an array")
    alias = query["as"]
    if not isinstance(alias, str) or not alias.isidentifier() or alias in scope:
        raise ValueError(f"invalid or shadowed JSON query alias: {alias!r}")
    return ((item, {**scope, alias: item}) for item in items)


def _query(query: dict, scope) -> list:
    if set(query) - {"from", "as", "where", "take", "select", "flatten"}:
        raise ValueError("unknown JSON query option")
    if type(query.get("flatten", False)) is not bool:
        raise ValueError("JSON query flatten must be boolean")
    rows = [(item, inner) for item, inner in _rows(query, scope)
            if _predicate(query.get("where", True), inner)]
    if "take" in query:
        if query["take"] != "last":
            raise ValueError("JSON query take must be 'last'")
        rows = rows[-1:]  # Filter first; keep the last match in response order.
    values = [_value(query["select"], inner) if "select" in query else item for item, inner in rows]
    if query.get("flatten", False):
        if any(not isinstance(value, list) for value in values):
            raise ValueError("JSON query flatten requires arrays")
        values = [item for value in values for item in value]
    return values


def _predicate(spec, scope) -> bool:
    if type(spec) is bool:
        return spec
    if not isinstance(spec, dict) or len(spec) != 1:
        raise ValueError("JSON predicate must contain exactly one operator")
    op, args = next(iter(spec.items()))
    if op in {"all", "any"}:
        if not isinstance(args, list) or not args:
            raise ValueError(f"{op} requires nonempty predicates")
        # Short circuit allows an explicit type test before a comparison.
        return (all if op == "all" else any)(_predicate(arg, scope) for arg in args)
    if op == "not":
        return not _predicate(args, scope)
    if op in {"some", "every"}:
        if set(args) - {"from", "as", "where"}:
            raise ValueError(f"unknown {op} option")
        # Inspect all records, so a matching row cannot hide malformed evidence.
        matches = [_predicate(args.get("where", True), inner) for _, inner in _rows(args, scope)]
        return (any if op == "some" else all)(matches)
    if op not in {"eq", "in", "gte", "lte", "gt", "lt", "type"}:
        raise ValueError(f"unknown JSON predicate operator: {op}")
    if not isinstance(args, list) or len(args) != 2:
        raise ValueError(f"{op} requires two operands")
    left, right = (_value(arg, scope) for arg in args)
    if op == "type":
        kinds = {"null": type(None), "boolean": bool, "integer": int,
                 "number": (int, float), "string": str, "array": list, "object": dict}
        if not isinstance(right, str) or right not in kinds:
            raise ValueError(f"unknown JSON type: {right!r}")
        if right == "number":
            return type(left) in {int, float} and math.isfinite(left)
        return type(left) is kinds[right]
    if op == "eq":
        # JSON booleans must not equal numeric 0/1 as they do in Python.
        return _equal(left, right)
    if op == "in":
        if not isinstance(right, list):
            raise ValueError("in requires an array on the right")
        return any(_equal(left, value) for value in right)
    if any(type(value) not in {int, float} or not math.isfinite(value) for value in (left, right)):
        raise ValueError(f"{op} requires finite numbers")
    return {"gte": lambda: left >= right, "lte": lambda: left <= right,
            "gt": lambda: left > right, "lt": lambda: left < right}[op]()


def _equal(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    return left == right
