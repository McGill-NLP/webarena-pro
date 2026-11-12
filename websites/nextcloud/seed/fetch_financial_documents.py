#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch and pin the open-licensed customer-order workbook."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree


ORDER_WORKBOOK_URL = (
    "https://data.mendeley.com/public-files/datasets/ggbkd8ck3x/files/"
    "f128acca-c449-455c-bfc9-1f63de988771/file_downloaded"
)
ORDER_WORKBOOK_SHA256 = "67cc68d5e87295e622801ac7ec7f095de05ba94eb45c8ebf32cc8531edfe6037"
USERS = ("maya.patel", "daniel.brooks")
XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "WebArena-Pro seed fetcher/2"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def cell_column(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def xlsx_rows(path: Path):
    with zipfile.ZipFile(path) as archive:
        shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(node.text or "" for node in item.iter(f"{XLSX_NS}t"))
            for item in shared_root.findall(f"{XLSX_NS}si")
        ]
        with archive.open("xl/worksheets/sheet1.xml") as worksheet:
            for _, row in ElementTree.iterparse(worksheet, events=("end",)):
                if row.tag != f"{XLSX_NS}row":
                    continue
                values = [""] * 6
                for cell in row.findall(f"{XLSX_NS}c"):
                    index = cell_column(cell.get("r", "A1"))
                    raw_value = cell.findtext(f"{XLSX_NS}v") or ""
                    if 0 <= index < len(values):
                        values[index] = shared_strings[int(raw_value)] if cell.get("t") == "s" else raw_value
                row.clear()
                yield values


def selected_orders(path: Path) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for index, values in enumerate(xlsx_rows(path)):
        if index == 0:
            if values != ["rec_id", "order_id", "order_date", "shipped_at", "prod_sku", "prod_qty"]:
                raise ValueError(f"Unexpected order-workbook header: {values}")
            continue
        if values[1]:
            counts[values[1]] += 1
    multi_line = [(order_id, count) for order_id, count in counts.items() if 1 < count <= 20][:20]
    single_line = [(order_id, count) for order_id, count in counts.items() if count == 1][:20]
    if len(multi_line) != 20 or len(single_line) != 20:
        raise ValueError("Order workbook does not contain the expected single-line and multi-line records")
    selected: list[tuple[str, int]] = []
    for multi, single in zip(multi_line, single_line):
        selected.extend((multi, single))
    return selected


def verify(output_dir: Path, catalog_path: Path) -> None:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    order_dataset = catalog["order_dataset"]
    expected = {order_dataset["bundled_path"]: order_dataset["sha256"]}
    actual = {
        path.relative_to(output_dir.parent).as_posix(): sha256_file(path)
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError(f"Financial source coverage/hash mismatch: expected={expected}, actual={actual}")


def fetch(output_dir: Path, catalog_path: Path) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        order_workbook = Path(temporary_directory) / "E-Commerce DataSet.xlsx"
        download(ORDER_WORKBOOK_URL, order_workbook)
        if sha256_file(order_workbook) != ORDER_WORKBOOK_SHA256:
            raise ValueError("E-commerce order workbook SHA-256 mismatch")

        if output_dir.exists():
            shutil.rmtree(output_dir)
        (output_dir / "ecommerce-orders").mkdir(parents=True)
        order_bundled_path = "financial_documents/ecommerce-orders/E-Commerce DataSet.xlsx"
        order_destination = output_dir.parent / order_bundled_path
        shutil.copyfile(order_workbook, order_destination)

        owner_counts: Counter[str] = Counter()
        order_type_counts: Counter[str] = Counter()
        order_records = []
        for index, (order_id, line_count) in enumerate(selected_orders(order_workbook), start=1):
            order_type = "multi" if line_count > 1 else "single"
            owner = USERS[order_type_counts[order_type] % len(USERS)]
            order_type_counts[order_type] += 1
            owner_counts[owner] += 1
            order_records.append(
                {
                    "id": f"ecommerce-order-{index:03d}",
                    "owner": owner,
                    "order_id": order_id,
                    "line_count": line_count,
                    "document_destination_path": (
                        "Sales/Orders/Open Dataset Documents/"
                        f"Customer_Order_{owner_counts[owner]:03d}.xlsx"
                    ),
                }
            )

        catalog = {
            "version": 2,
            "description": "Pinned authentic customer-order records and their deterministic allocations.",
            "sources": {
                "ecommerce-orders": {
                    "title": "E-Commerce Dataset",
                    "creator": "Debjit Roy and Vishal Bansal",
                    "doi": "10.17632/ggbkd8ck3x.1",
                    "source_url": "https://data.mendeley.com/datasets/ggbkd8ck3x/1",
                    "file_url": ORDER_WORKBOOK_URL,
                    "revision": "version 1 (2020-11-23)",
                    "license": "CC-BY-4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                }
            },
            "order_dataset": {
                "bundled_path": order_bundled_path,
                "sha256": sha256_file(order_destination),
                "bytes": order_destination.stat().st_size,
                "destination_path": "Sales/Orders/Open Dataset Source/E-Commerce DataSet.xlsx",
            },
            "order_records": order_records,
        }
        catalog_path.write_text(json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verify(output_dir, catalog_path)
    print(
        f"Pinned one {order_destination.stat().st_size}-byte order workbook and selected "
        f"{len(order_records)} customer orders."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "media" / "financial_documents",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("financial_documents.json"),
    )
    parser.add_argument("--verify-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.verify_only:
        verify(args.output.resolve(), args.catalog.resolve())
        print("Financial source files match the checked-in catalog.")
    else:
        fetch(args.output.resolve(), args.catalog.resolve())


if __name__ == "__main__":
    main()
