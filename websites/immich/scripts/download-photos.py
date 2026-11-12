#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "datasets",
#     "requests",
# ]
# ///
"""
Download a diverse subset of Open Images V7 (CC-BY 2.0) from Hugging Face
and organize into per-user folders for Immich WebArena seeding.

Usage:
    ./scripts/download-photos.py [--output seed/photos] [--per-user 300] [--num-agents 5]

Requires `uv` (https://docs.astral.sh/uv/). No manual install needed —
uv resolves dependencies automatically via the inline script metadata above.
"""

import argparse
import sys
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import requests
from datasets import load_dataset

DEFAULT_NUM_AGENTS = 5
DEFAULT_PER_USER = 300
DEFAULT_OUTPUT = "seed/photos"

DATASET_NAME = "bitmind/open-images-v7"
SPLIT = "train"

DOWNLOAD_TIMEOUT = 3  # seconds per image
MAX_WORKERS = 32


def fetch_image(url: str, filepath: Path) -> bool:
    """Download a single image. Returns True on success."""
    try:
        resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type:
            return False
        filepath.write_bytes(resp.content)
        return True
    except Exception:
        return False


def download_photos(output_dir: Path, per_user: int, users: list[str]):
    total_needed = per_user * len(users)

    for user in users:
        (output_dir / user).mkdir(parents=True, exist_ok=True)

    print(f"Users: {', '.join(users)}")
    print(f"Downloading {per_user} images per user ({total_needed} total) from Open Images V7...")
    print(f"Output: {output_dir.resolve()}")
    print(f"Streaming URLs from: {DATASET_NAME} ({SPLIT} split)")
    print()

    ds = load_dataset(DATASET_NAME, split=SPLIT, streaming=True)
    dataset_iter = iter(ds)
    dataset_exhausted = False
    sample_index = 0

    counts = defaultdict(int)
    total_saved = 0
    failed = 0

    def next_task(user: str):
        """Pull the next URL from the stream and return (url, filepath), or None if exhausted."""
        nonlocal sample_index, dataset_exhausted
        try:
            sample = next(dataset_iter)
        except StopIteration:
            dataset_exhausted = True
            return None
        url = sample["url"]
        ext = url.rsplit(".", 1)[-1].lower() if "." in url else "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        filepath = output_dir / user / f"oi7_{sample_index:06d}.{ext}"
        sample_index += 1
        return url, filepath

    def submit_for(user: str, pool, futures: dict) -> bool:
        """Submit one download task for user. Returns False if dataset is exhausted."""
        task = next_task(user)
        if task is None:
            return False
        url, filepath = task
        fut = pool.submit(fetch_image, url, filepath)
        futures[fut] = (filepath, user)
        return True

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}

        # Seed the pool: 2 tasks per user to start
        for user in users:
            for _ in range(2):
                if not submit_for(user, pool, futures):
                    break

        while futures:
            if all(counts[u] >= per_user for u in users):
                # All users satisfied — cancel remaining in-flight tasks
                for fut in list(futures):
                    fut.cancel()
                    filepath, _ = futures.pop(fut)
                    filepath.unlink(missing_ok=True)
                break

            done_set, _ = wait(list(futures), return_when=FIRST_COMPLETED)

            for fut in done_set:
                filepath, user = futures.pop(fut)
                try:
                    success = fut.result()
                except Exception:
                    success = False

                if success and counts[user] < per_user:
                    counts[user] += 1
                    total_saved += 1
                    if total_saved % 50 == 0:
                        status = ", ".join(f"{u}={counts[u]}" for u in users)
                        print(f"  [{total_saved}/{total_needed}] {status}")
                else:
                    filepath.unlink(missing_ok=True)
                    failed += 1

                # Refill: submit a new task for whichever user needs the most images
                needy = [u for u in users if counts[u] < per_user]
                if needy and not dataset_exhausted:
                    next_user = min(needy, key=lambda u: counts[u])
                    submit_for(next_user, pool, futures)

    print()
    if dataset_exhausted:
        short = [u for u in users if counts[u] < per_user]
        if short:
            print(f"WARNING: dataset exhausted before all users reached {per_user} images.")
            print(f"  Short: {', '.join(f'{u}={counts[u]}' for u in short)}")
        else:
            print(f"Done!")
    else:
        print(f"Done! ({failed} URLs failed/skipped)")

    for user in users:
        folder = output_dir / user
        files = [f for f in folder.iterdir() if f.is_file()]
        size_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
        print(f"  {user}: {counts[user]} images ({size_mb:.1f} MB)")


def main():
    parser = argparse.ArgumentParser(description="Download Open Images V7 subset for Immich seeding")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help=f"Output directory (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--per-user", type=int, default=DEFAULT_PER_USER, help=f"Images per user (default: {DEFAULT_PER_USER})")
    parser.add_argument("--num-agents", type=int, default=DEFAULT_NUM_AGENTS, help=f"Number of agent users (default: {DEFAULT_NUM_AGENTS}, creates agent1..agentN)")
    args = parser.parse_args()

    users = ["admin"] + [f"agent{i}" for i in range(1, args.num_agents + 1)]
    output_dir = Path(args.output)
    download_photos(output_dir, args.per_user, users)


if __name__ == "__main__":
    main()
