#!/usr/bin/env python3
"""Export a compact Bluesky tree cache for X-lite builds."""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys


BLUESKY_COLUMNS = ("type", "text", "created_at", "author", "author_did", "uri", "langs", "reply_to")


def import_pyarrow_parquet():
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError("This exporter requires pyarrow.") from exc
    return pq


def load_selected_nodes(annotation_csv: str, root_limit: int) -> dict[str, dict]:
    csv.field_size_limit(sys.maxsize)
    selected: dict[str, dict] = {}
    with open(annotation_csv, "r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            root_rank = int(row["root_rank"])
            if root_rank > root_limit:
                break
            node_id = row["node_id"]
            selected[node_id] = {
                "root_rank": root_rank,
                "depth": int(row["depth"]),
                "parent_node": row["parent_node"],
                "root_node": row["root_node"],
                "root_label": row["root_label"],
                "descendant_count": int(row["descendant_count"]),
                "direct_child_count": int(row["direct_child_count"]),
            }
    return selected


def export_cache(parquet_path: str, annotations_path: str, output_path: str, root_limit: int, batch_size: int) -> None:
    selected = load_selected_nodes(annotations_path, root_limit)
    remaining = set(selected)
    if not selected:
        raise RuntimeError("No selected nodes were loaded from the annotation CSV.")

    pq = import_pyarrow_parquet()
    parquet_file = pq.ParquetFile(parquet_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    tmp_path = f"{output_path}.tmp"
    written = 0
    scanned = 0

    with gzip.open(tmp_path, "wt", encoding="utf-8") as output:
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=list(BLUESKY_COLUMNS)):
            columns = {name: batch.column(name).to_pylist() for name in batch.schema.names}
            for index in range(batch.num_rows):
                scanned += 1
                uri = str(columns["uri"][index] or "")
                if uri not in remaining:
                    continue
                metadata = selected[uri]
                record = {name: columns[name][index] for name in BLUESKY_COLUMNS}
                record.update(metadata)
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                output.write("\n")
                remaining.remove(uri)
                written += 1
            if scanned and scanned % 1_000_000 < batch.num_rows:
                print(f"Scanned {scanned:,} rows; wrote {written:,}", file=sys.stderr)
            if not remaining:
                break

    os.replace(tmp_path, output_path)
    if remaining:
        print(f"Warning: {len(remaining):,} selected nodes were not found in the parquet", file=sys.stderr)
    print(f"Wrote {output_path}: {written:,} rows from {root_limit:,} roots")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", required=True)
    parser.add_argument("--annotations", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--root-limit", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=50000)
    args = parser.parse_args()

    export_cache(args.parquet, args.annotations, args.output, args.root_limit, args.batch_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
