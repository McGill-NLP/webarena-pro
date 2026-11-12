import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE_DIR = ROOT / "static" / "videos"
DEFAULT_OUTPUT_DIR = ROOT / "static" / "videos_h265"
SCALE_FILTER = (
    "scale=w=1280:h=720:force_original_aspect_ratio=decrease,"
    "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black"
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Safely transcode local yt-lite videos to 720p HEVC."
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing source MP4 files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where transcoded MP4 files should be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on how many pending files to process in this run.",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="ffmpeg executable to use.",
    )
    parser.add_argument(
        "--ffprobe",
        default="ffprobe",
        help="ffprobe executable to use.",
    )
    return parser.parse_args()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_video(ffprobe_bin, path):
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,level",
        "-of",
        "json",
        str(path),
    ]
    result = run(cmd)
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") or []
    return streams[0] if streams else None


def is_expected_output(ffprobe_bin, path):
    if not path.exists() or path.stat().st_size == 0:
        return False
    stream = probe_video(ffprobe_bin, path)
    if not stream:
        return False
    if stream.get("codec_name") != "hevc":
        return False
    return stream.get("width") == 1280 and stream.get("height") == 720


def transcode_one(ffmpeg_bin, source_path, output_path):
    temp_path = output_path.with_suffix(".tmp.mp4")
    if temp_path.exists():
        temp_path.unlink()

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-vf",
        SCALE_FILTER,
        "-c:v",
        "libx265",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-x265-params",
        "level-idc=31",
        "-tag:v",
        "hvc1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(temp_path),
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        if temp_path.exists():
            temp_path.unlink()
        return False
    temp_path.replace(output_path)
    return True


def human_gb(byte_count):
    return byte_count / (1024 ** 3)


def main():
    args = parse_args()
    source_dir = args.source_dir.resolve()
    output_dir = args.output_dir.resolve()

    if not source_dir.exists():
        print(f"Source directory does not exist: {source_dir}", file=sys.stderr)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    source_files = sorted(source_dir.glob("*.mp4"))
    pending_files = []
    skipped_existing = 0

    for source_path in source_files:
        output_path = output_dir / source_path.name
        if is_expected_output(args.ffprobe, output_path):
            skipped_existing += 1
            continue
        pending_files.append(source_path)

    if args.limit is not None:
        pending_files = pending_files[: args.limit]

    transcoded = 0
    failed = []

    for index, source_path in enumerate(pending_files, start=1):
        output_path = output_dir / source_path.name
        print(
            f"[{index}/{len(pending_files)}] Transcoding {source_path.name} -> {output_path.name}",
            flush=True,
        )
        success = transcode_one(args.ffmpeg, source_path, output_path)
        if not success or not is_expected_output(args.ffprobe, output_path):
            failed.append(source_path.name)
            print(f"  failed: {source_path.name}", flush=True)
            continue
        transcoded += 1
        print(f"  ok: {source_path.name}", flush=True)

    output_files = sorted(output_dir.glob("*.mp4"))
    output_bytes = sum(path.stat().st_size for path in output_files)
    consistent_count = sum(1 for path in output_files if is_expected_output(args.ffprobe, path))

    print("")
    print("Summary")
    print(f"  source files: {len(source_files)}")
    print(f"  skipped existing outputs: {skipped_existing}")
    print(f"  transcoded this run: {transcoded}")
    print(f"  failed this run: {len(failed)}")
    print(f"  output files present: {len(output_files)}")
    print(f"  consistent outputs: {consistent_count}")
    print(f"  output size GB: {human_gb(output_bytes):.4f}")
    if failed:
        print("  failed files:")
        for name in failed:
            print(f"    {name}")

    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
