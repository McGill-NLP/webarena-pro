#!/usr/bin/env python3
"""Export compact Bluesky reply edges from the cached Parquet file.

The C++ tree annotator intentionally consumes CSV so it can run without Python
or pyarrow in production-style build steps.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
from pathlib import Path

import pyarrow.parquet as pq


DEFAULT_PARQUET = "/private/tmp/x-lite-bluesky-cache/bluesky-ten-million-train.parquet"
DEFAULT_OUTPUT = "/private/tmp/x-lite-bluesky-tree-input.csv"
COLUMNS = ["type", "text", "created_at", "author", "author_did", "uri", "langs", "reply_to"]

TOPIC_TERMS = {
    "sports": {
        "sport", "sports", "game", "games", "team", "teams", "match", "league",
        "season", "playoff", "playoffs", "coach", "football", "soccer",
        "basketball", "baseball", "hockey", "tennis", "golf", "nfl", "nba",
        "mlb", "nhl", "fifa", "goal", "player",
    },
    "movies": {
        "movie", "movies", "film", "films", "cinema", "theater", "trailer",
        "premiere", "boxoffice", "oscars", "actor", "actress", "director",
        "sequel", "marvel", "pixar", "screening",
    },
    "tv": {
        "tv", "television", "show", "shows", "series", "episode", "episodes",
        "season", "streaming", "netflix", "hulu", "hbo", "disney", "prime",
        "finale", "sitcom", "documentary",
    },
    "music": {
        "music", "song", "songs", "album", "track", "single", "concert",
        "tour", "festival", "band", "artist", "singer", "playlist", "grammy",
        "rap", "pop", "rock", "jazz",
    },
}


def parse_langs(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.lower()} if value.strip() else set()
    try:
        return {str(item).lower() for item in value if str(item).strip()}
    except TypeError:
        return {str(value).lower()} if str(value).strip() else set()


def label_for_text(text: str) -> str:
    tokens = set(re.findall(r"[a-z][a-z0-9]+", (text or "").lower()))
    tokens |= {token[1:].lower() for token in re.findall(r"#[A-Za-z][A-Za-z0-9_]+", text or "")}
    scores = {
        topic: len(tokens & terms)
        for topic, terms in TOPIC_TERMS.items()
    }
    topic, score = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[0]
    return topic if score else "general"


def export_csv(parquet_path: str, output_path: str, langs: set[str], batch_size: int) -> tuple[int, int]:
    parquet = pq.ParquetFile(parquet_path)
    written = 0
    scanned = 0
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["node_id", "parent_node", "label"])
        for batch in parquet.iter_batches(batch_size=batch_size, columns=COLUMNS):
            rows = batch.to_pylist()
            for row in rows:
                scanned += 1
                if row.get("type") and row.get("type") != "post":
                    continue
                node_id = str(row.get("uri") or "")
                text = row.get("text") or ""
                if not node_id or not text:
                    continue
                if langs and not (parse_langs(row.get("langs")) & langs):
                    continue
                writer.writerow([node_id, str(row.get("reply_to") or ""), label_for_text(text)])
                written += 1
            if scanned and scanned % 1_000_000 < len(rows):
                print(f"exported {written:,} eligible rows after scanning {scanned:,}", flush=True)
    return scanned, written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parquet", default=os.environ.get("X_LITE_BLUESKY_PARQUET", DEFAULT_PARQUET))
    parser.add_argument("--output", default=os.environ.get("X_LITE_BLUESKY_TREE_CSV", DEFAULT_OUTPUT))
    parser.add_argument("--langs", default=os.environ.get("X_LITE_BLUESKY_LANGS", "en"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("X_LITE_BLUESKY_BATCH_SIZE", "50000")))
    args = parser.parse_args()
    langs = {part.strip().lower() for part in args.langs.split(",") if part.strip()}
    scanned, written = export_csv(args.parquet, args.output, langs, args.batch_size)
    print(f"wrote {written:,} rows to {args.output} after scanning {scanned:,}")


if __name__ == "__main__":
    main()
