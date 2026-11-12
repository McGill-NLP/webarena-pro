"""
Bounded FineVideo batch importer for yt-lite.

This importer supports two bounded sources:
- rows: the Hugging Face dataset-viewer /rows endpoint.
- hub-parquet: explicitly selected Hugging Face repo parquet shards.

Both modes decode MP4 payloads, generate local thumbnails with ffmpeg, and
write each successful local-video entry immediately to
data/finevideo_local_seed.json.

For unstable ranges, prefer smaller batches such as --count 10 or --count 25
and rerun from the same offset; completed rows are skipped unless --overwrite is
used.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from huggingface_hub import hf_hub_download, get_token
except ImportError:
    hf_hub_download = None
    get_token = None

try:
    import pyarrow.parquet as pq
except ImportError:
    pq = None


DATASET = "HuggingFaceFV/finevideo"
API_ROOT = "https://datasets-server.huggingface.co"
ROOT = Path(__file__).resolve().parent
VIDEO_DIR = ROOT / "static" / "videos"
THUMBNAIL_DIR = ROOT / "static" / "thumbnails"
SEED_PATH = ROOT / "data" / "finevideo_local_seed.json"
MAX_COUNT = 100
MAX_SHARD_COUNT = 5
MAX_PARQUET_ROWS = 100
RETRYABLE_HTTP_CODES = {502, 503, 504}


def token_from_env() -> str | None:
    return (
        os.environ.get("HF_TOKEN") or
        os.environ.get("HUGGINGFACE_HUB_TOKEN") or
        (get_token() if get_token else None)
    )


def api_get_rows(offset: int, token: str | None, retries: int, backoff: float) -> dict:
    params = {
        "dataset": DATASET,
        "config": "default",
        "split": "train",
        "offset": str(offset),
        "length": "1",
    }
    url = f"{API_ROOT}/rows?{urlencode(params)}"
    headers = {"User-Agent": "yt-lite-finevideo-batch/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for attempt in range(1, retries + 1):
        try:
            with urlopen(Request(url, headers=headers), timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code not in RETRYABLE_HTTP_CODES or attempt == retries:
                raise SystemExit(
                    f"Dataset-viewer /rows failed at offset {offset}: "
                    f"HTTP {exc.code}\n{detail}"
                ) from exc
            wait = backoff * (2 ** (attempt - 1))
            print(
                f"Retryable HTTP {exc.code} at offset {offset}; "
                f"retry {attempt}/{retries} after {wait:.1f}s"
            )
            time.sleep(wait)
        except URLError as exc:
            if attempt == retries:
                raise SystemExit(
                    f"Dataset-viewer /rows failed at offset {offset}: {exc}"
                ) from exc
            wait = backoff * (2 ** (attempt - 1))
            print(
                f"Retryable network error at offset {offset}: {exc}; "
                f"retry {attempt}/{retries} after {wait:.1f}s"
            )
            time.sleep(wait)

    raise SystemExit(f"Dataset-viewer /rows failed at offset {offset}")


def decode_mp4(value) -> bytes:
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        if len(data) < 16 or data[4:8] != b"ftyp":
            raise ValueError("binary payload does not look like an MP4")
        return data

    if not isinstance(value, str):
        raise ValueError("mp4 field is not a string or bytes")
    if value.startswith(("http://", "https://")):
        raise ValueError("mp4 field is a URL, not an inline payload")

    payload = value.strip()
    if payload.startswith('"') and payload.endswith('"'):
        payload = json.loads(payload)
    elif payload.startswith('"'):
        raise ValueError("mp4 field appears truncated")

    data = base64.b64decode(payload, validate=True)
    if len(data) < 16 or data[4:8] != b"ftyp":
        raise ValueError("decoded payload does not look like an MP4")
    return data


def normalize_metadata(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return json.loads(bytes(value).decode("utf-8"))
    raise ValueError("metadata is not a JSON object")


def format_duration(seconds) -> str:
    try:
        total = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "0:00"
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def site_category(metadata: dict) -> str:
    parent = (metadata.get("content_parent_category") or "").lower()
    fine = (metadata.get("content_fine_category") or "").lower()
    joined = f"{parent} {fine}"
    if "game" in joined:
        return "Gaming"
    if "music" in joined:
        return "Music"
    if "travel" in joined:
        return "Travel"
    if "news" in joined:
        return "News"
    if "education" in joined or "engineering" in joined or "career" in joined:
        return "Learning"
    return "Other"


def seed_entry(
    row_number: int,
    metadata: dict,
    source: str | None = None,
    source_shard: int | None = None,
    source_row: int | None = None,
) -> dict:
    video_id = f"fv{row_number:03d}"
    title = (
        metadata.get("youtube_title") or
        metadata.get("content_metadata", {}).get("title") or
        f"FineVideo sample {row_number:03d}"
    )
    channel = metadata.get("youtube_channel") or "FineVideo"
    views = metadata.get("youtube_view_count")
    description = (
        metadata.get("youtube_description") or
        metadata.get("content_metadata", {}).get("description") or
        "FineVideo local prototype sample."
    )
    fine = metadata.get("content_fine_category")
    parent = metadata.get("content_parent_category")
    if fine or parent:
        description = f"FineVideo sample: {fine or 'Unknown'} / {parent or 'Unknown'}."

    entry = {
        "id": video_id,
        "title": title,
        "channel": channel,
        "views": f"{views} views" if views is not None else "0 views",
        "duration": format_duration(metadata.get("duration_seconds")),
        "category": site_category(metadata),
        "video_path": f"videos/finevideo_test_{row_number:03d}.mp4",
        "thumbnail": f"/static/thumbnails/finevideo_test_{row_number:03d}.jpg",
        "description": description,
        "created_at": datetime.utcnow().isoformat(),
    }
    if source:
        entry["source"] = source
    if source_shard is not None:
        entry["source_shard"] = source_shard
    if source_row is not None:
        entry["source_row"] = source_row
    return entry


def generate_thumbnail(video_path: Path, thumbnail_path: Path, overwrite: bool) -> None:
    if thumbnail_path.exists() and not overwrite:
        return
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "00:00:01",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(thumbnail_path),
        ],
        check=True,
    )


def read_seed() -> list[dict]:
    if not SEED_PATH.exists():
        return []
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def write_seed(entries: list[dict]) -> None:
    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    entries = sorted(entries, key=lambda entry: entry["id"])
    SEED_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def update_seed(new_entries: list[dict]) -> None:
    entries_by_id = {entry["id"]: entry for entry in read_seed()}
    for entry in new_entries:
        entries_by_id[entry["id"]] = entry
    write_seed(list(entries_by_id.values()))


def seed_has_entry(video_id: str) -> bool:
    return any(entry.get("id") == video_id for entry in read_seed())


def seed_entry_for_source(source: str, source_shard: int, source_row: int) -> dict | None:
    for entry in read_seed():
        if (
            entry.get("source") == source and
            entry.get("source_shard") == source_shard and
            entry.get("source_row") == source_row
        ):
            return entry
    return None


def next_row_number() -> int:
    max_id = 0
    for entry in read_seed():
        video_id = entry.get("id", "")
        if video_id.startswith("fv"):
            try:
                max_id = max(max_id, int(video_id[2:]))
            except ValueError:
                pass
    return max_id + 1


def import_rows(
    offset: int,
    count: int,
    overwrite: bool,
    token: str | None,
    retries: int,
    backoff: float,
) -> None:
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_offset in range(offset, offset + count):
        row_number = dataset_offset + 1
        video_id = f"fv{row_number:03d}"
        video_path = VIDEO_DIR / f"finevideo_test_{row_number:03d}.mp4"
        thumbnail_path = THUMBNAIL_DIR / f"finevideo_test_{row_number:03d}.jpg"
        seeded = seed_has_entry(video_id)

        if video_path.exists() and thumbnail_path.exists() and seeded and not overwrite:
            print(f"Skipping existing seeded row: {video_id}")
            continue

        payload = api_get_rows(dataset_offset, token, retries, backoff)
        rows = payload.get("rows", [])
        if len(rows) != 1:
            raise SystemExit(f"Expected exactly one row at offset {dataset_offset}, got {len(rows)}")

        item = rows[0]
        row = item.get("row", {})
        if item.get("truncated_cells"):
            raise SystemExit(f"Row {dataset_offset} has truncated cells: {item['truncated_cells']}")

        metadata = row.get("json") or {}
        if not isinstance(metadata, dict):
            raise SystemExit(f"Row {dataset_offset} metadata is not a JSON object")

        if video_path.exists() and not overwrite:
            print(f"Keeping existing video: {video_path}")
        else:
            video_path.write_bytes(decode_mp4(row.get("mp4")))
            print(f"Saved video: {video_path}")

        generate_thumbnail(video_path, thumbnail_path, overwrite)
        print(f"Ready thumbnail: {thumbnail_path}")
        if seeded and not overwrite:
            print(f"Keeping existing seed entry: {video_id}")
        else:
            update_seed([seed_entry(row_number, metadata)])
            print(f"Updated seed entry: {video_id}")

    print(f"Seed file ready: {SEED_PATH}")


def shard_filename(shard_index: int) -> str:
    return f"data/train-{shard_index:05d}-of-01357.parquet"


def download_shard(shard_index: int, token: str | None) -> Path:
    if hf_hub_download is None:
        raise SystemExit("huggingface_hub is required for --source hub-parquet")
    filename = shard_filename(shard_index)
    path = hf_hub_download(
        repo_id=DATASET,
        repo_type="dataset",
        filename=filename,
        token=token,
    )
    return Path(path)


def import_hub_parquet(
    shard_start: int,
    shard_count: int,
    max_rows: int,
    overwrite: bool,
    token: str | None,
) -> None:
    if pq is None:
        raise SystemExit("pyarrow is required for --source hub-parquet")

    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    imported = 0
    for shard_index in range(shard_start, shard_start + shard_count):
        if imported >= max_rows:
            break
        parquet_path = download_shard(shard_index, token)
        table = pq.read_table(parquet_path, columns=["mp4", "json"])
        rows = table.to_pylist()
        print(f"Reading shard {shard_index}: {parquet_path} rows={len(rows)}")

        for source_row, row in enumerate(rows):
            if imported >= max_rows:
                break

            existing = seed_entry_for_source("hub-parquet", shard_index, source_row)
            if existing and not overwrite:
                video_path = ROOT / "static" / existing["video_path"]
                thumbnail_path = ROOT / existing["thumbnail"].lstrip("/")
                if video_path.exists() and thumbnail_path.exists():
                    print(
                        "Skipping existing source row: "
                        f"shard={shard_index} row={source_row} id={existing['id']}"
                    )
                    continue

            row_number = (
                int(existing["id"][2:])
                if existing and existing.get("id", "").startswith("fv")
                else next_row_number()
            )
            video_id = f"fv{row_number:03d}"
            video_path = VIDEO_DIR / f"finevideo_test_{row_number:03d}.mp4"
            thumbnail_path = THUMBNAIL_DIR / f"finevideo_test_{row_number:03d}.jpg"

            if video_path.exists() and thumbnail_path.exists() and seed_has_entry(video_id) and not overwrite:
                print(f"Skipping existing seeded row: {video_id}")
                continue

            if video_path.exists() and not overwrite:
                print(f"Keeping existing video: {video_path}")
            else:
                video_path.write_bytes(decode_mp4(row.get("mp4")))
                print(f"Saved video: {video_path}")

            generate_thumbnail(video_path, thumbnail_path, overwrite)
            print(f"Ready thumbnail: {thumbnail_path}")
            metadata = normalize_metadata(row.get("json") or {})
            if existing and not overwrite:
                print(f"Keeping existing seed entry: {video_id}")
            else:
                update_seed([
                    seed_entry(
                        row_number,
                        metadata,
                        source="hub-parquet",
                        source_shard=shard_index,
                        source_row=source_row,
                    )
                ])
                print(
                    "Updated seed entry: "
                    f"{video_id} shard={shard_index} row={source_row}"
                )
            imported += 1

    print(f"Imported {imported} new/updated rows from hub parquet shards")
    print(f"Seed file ready: {SEED_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["rows", "hub-parquet"], default="rows")
    parser.add_argument("--offset", type=int)
    parser.add_argument("--count", type=int)
    parser.add_argument("--shard-start", type=int)
    parser.add_argument("--shard-count", type=int)
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--backoff", type=float, default=5.0)
    parser.add_argument("--token", default=token_from_env())
    args = parser.parse_args()

    if args.retries < 1:
        parser.error("--retries must be >= 1")
    if args.backoff < 0:
        parser.error("--backoff must be >= 0")

    if args.source == "rows":
        if args.offset is None:
            parser.error("--offset is required for --source rows")
        if args.count is None:
            parser.error("--count is required for --source rows")
        if args.offset < 0:
            parser.error("--offset must be >= 0")
        if args.count < 1:
            parser.error("--count must be >= 1")
        if args.count > MAX_COUNT:
            parser.error(f"--count is capped at {MAX_COUNT}")

        import_rows(args.offset, args.count, args.overwrite, args.token, args.retries, args.backoff)
    else:
        if args.shard_start is None:
            parser.error("--shard-start is required for --source hub-parquet")
        if args.shard_count is None:
            parser.error("--shard-count is required for --source hub-parquet")
        if args.max_rows is None:
            parser.error("--max-rows is required for --source hub-parquet")
        if args.shard_start < 0:
            parser.error("--shard-start must be >= 0")
        if args.shard_count < 1:
            parser.error("--shard-count must be >= 1")
        if args.shard_count > MAX_SHARD_COUNT:
            parser.error(f"--shard-count is capped at {MAX_SHARD_COUNT}")
        if args.max_rows < 1:
            parser.error("--max-rows must be >= 1")
        if args.max_rows > MAX_PARQUET_ROWS:
            parser.error(f"--max-rows is capped at {MAX_PARQUET_ROWS}")

        import_hub_parquet(
            args.shard_start,
            args.shard_count,
            args.max_rows,
            args.overwrite,
            args.token,
        )


if __name__ == "__main__":
    main()
