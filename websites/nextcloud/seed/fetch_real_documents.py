#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch or verify the pinned open-license real-document corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_catalog(path: Path) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("version") != 1:
        raise ValueError(f"Unsupported catalog version in {path}")
    return catalog


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "webarena-pro-real-document-fetcher/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=script_dir / "real_documents.json")
    parser.add_argument("--media", type=Path, default=script_dir.parent / "media")
    parser.add_argument("--verify-only", action="store_true", help="Fail instead of downloading missing files")
    args = parser.parse_args()

    catalog = read_catalog(args.catalog.resolve())
    media_dir = args.media.resolve()
    expected_paths: set[Path] = set()
    downloaded = verified = 0

    for entry in catalog["documents"]:
        source = catalog["sources"][entry["source"]]
        destination = media_dir / entry["bundled_path"]
        expected_paths.add(destination)
        if destination.is_file() and sha256_bytes(destination.read_bytes()) == entry["sha256"]:
            verified += 1
            continue
        if args.verify_only:
            raise ValueError(f"Missing or modified real document: {destination}")
        url = source["raw_base_url"].rstrip("/") + "/" + entry["source_path"]
        payload = fetch(url)
        actual_hash = sha256_bytes(payload)
        if actual_hash != entry["sha256"]:
            raise ValueError(f"SHA-256 mismatch for {url}: {actual_hash}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(destination)
        downloaded += 1

    real_root = media_dir / "real_documents"
    actual_paths = {path for path in real_root.rglob("*") if path.is_file() and not path.name.startswith(".")}
    extras = sorted(actual_paths - expected_paths)
    if extras:
        raise ValueError(f"Undocumented real documents: {extras}")
    print(f"Verified {verified + downloaded} real documents ({downloaded} downloaded).")


if __name__ == "__main__":
    main()
