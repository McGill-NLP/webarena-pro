import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DEFAULT_REPO_ID = "WebArena-Pro/yt-lite-data"
ALLOW_PATTERNS = ["videos/*", "thumbnails/*"]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch yt-lite video and thumbnail assets from Hugging Face."
    )
    parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
        help="Hugging Face dataset repo containing videos/ and thumbnails/.",
    )
    parser.add_argument(
        "--revision",
        default=None,
        help="Optional repo revision, branch, or commit.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Optional HF token. Falls back to cached login or HF_TOKEN.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if local cached copies already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without downloading files.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    result = snapshot_download(
        repo_id=args.repo_id,
        repo_type="dataset",
        revision=args.revision,
        local_dir=STATIC_DIR,
        allow_patterns=ALLOW_PATTERNS,
        force_download=args.force,
        token=args.token,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        planned = result if isinstance(result, list) else []
        print(f"Repo: {args.repo_id}")
        print(f"Would fetch files: {len(planned)}")
        for item in planned[:20]:
            print(item.filename)
        if len(planned) > 20:
            print(f"... and {len(planned) - 20} more")
        return 0

    video_count = len(list((STATIC_DIR / "videos").glob("*.mp4")))
    thumb_count = len(list((STATIC_DIR / "thumbnails").glob("*.*")))
    print(f"Fetched assets from {args.repo_id}")
    print(f"Videos present: {video_count}")
    print(f"Thumbnails present: {thumb_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
