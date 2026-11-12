#!/usr/bin/env python3
"""Compile seeded messages into root-and-reply conversation trees."""

from __future__ import annotations

import argparse
import gzip
import json
from collections import defaultdict
from pathlib import Path


def normalize_message_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not text.startswith("<"):
        text = f"<{text}"
    if not text.endswith(">"):
        text = f"{text}>"
    return text


def read_messages(path: Path) -> list[dict[str, object]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def compile_index(messages: list[dict[str, object]]) -> dict[str, object]:
    by_id = {
        normalize_message_id(message["message_id"]): message
        for message in messages
    }
    children: dict[str, list[str]] = defaultdict(list)
    parent_by_id: dict[str, str] = {}

    for message_id, message in by_id.items():
        parent = normalize_message_id(message.get("in_reply_to"))
        if parent in by_id and parent != message_id:
            parent_by_id[message_id] = parent
            children[parent].append(message_id)

    for message_ids in children.values():
        message_ids.sort(key=lambda item: str(by_id[item]["date"]))

    roots = sorted(
        (message_id for message_id in by_id if message_id not in parent_by_id),
        key=lambda item: str(by_id[item]["date"]),
    )
    visited: set[str] = set()
    lookup: dict[str, str] = {}
    threads: dict[str, dict[str, object]] = {}
    max_depth = 0

    def walk(message_id: str, depth: int, output: list[dict[str, object]]) -> None:
        nonlocal max_depth
        if message_id in visited:
            return
        visited.add(message_id)
        max_depth = max(max_depth, depth)
        message = by_id[message_id]
        output.append(
            {
                "id": message["id"],
                "message_id": message_id,
                "parent_message_id": parent_by_id.get(message_id, ""),
                "depth": depth,
                "from": message["from"],
                "to": message.get("to", []),
                "cc": message.get("cc", []),
                "subject": message["subject"],
                "date": message["date"],
                "body": message["body"],
                "folder": message["folder"],
            }
        )
        for child in children.get(message_id, []):
            walk(child, depth + 1, output)

    for root_id in roots:
        records: list[dict[str, object]] = []
        walk(root_id, 0, records)
        if not records:
            continue
        thread_id = str(records[0]["id"])
        threads[thread_id] = {
            "thread_id": thread_id,
            "root_message_id": root_id,
            "subject": records[0]["subject"],
            "message_count": len(records),
            "messages": records,
        }
        for record in records:
            lookup[str(record["message_id"])] = thread_id

    # A malformed cycle should not make a message disappear from the index.
    for message_id in sorted(set(by_id) - visited):
        message = by_id[message_id]
        thread_id = str(message["id"])
        record = {
            "id": message["id"],
            "message_id": message_id,
            "parent_message_id": "",
            "depth": 0,
            "from": message["from"],
            "to": message.get("to", []),
            "cc": message.get("cc", []),
            "subject": message["subject"],
            "date": message["date"],
            "body": message["body"],
            "folder": message["folder"],
        }
        threads[thread_id] = {
            "thread_id": thread_id,
            "root_message_id": message_id,
            "subject": message["subject"],
            "message_count": 1,
            "messages": [record],
        }
        lookup[message_id] = thread_id

    return {
        "version": 1,
        "message_count": len(messages),
        "thread_count": len(threads),
        "multi_message_thread_count": sum(
            int(thread["message_count"]) > 1 for thread in threads.values()
        ),
        "max_depth": max_depth,
        "lookup": lookup,
        "threads": threads,
    }


def write_index(path: Path, index: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(index, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as archive:
            archive.write(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("messages", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    index = compile_index(read_messages(args.messages))
    write_index(args.output, index)
    print(
        "Compiled "
        f"{index['message_count']} messages into {index['thread_count']} conversations "
        f"({index['multi_message_thread_count']} with replies, max depth {index['max_depth']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
