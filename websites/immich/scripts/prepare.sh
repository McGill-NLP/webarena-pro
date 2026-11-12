#!/bin/bash
# prepare.sh — Full pipeline: download photos → manual review → docker build
#
# Usage:
#   ./scripts/prepare.sh [OPTIONS]
#
# Options:
#   --num-agents N    Number of agent users, creates agent1..agentN (default: 5)
#   --per-user N      Photos per user (default: 300)
#   --output DIR      Photo output directory (default: seed/photos)
#   --image NAME      Docker image name (default: immich-webarena)
#   --skip-download   Skip photo download (use existing seed/photos/)
#   --skip-seed       Deprecated no-op; seeding happens inside the Dockerfile
#   --skip-build      Skip docker build; only download and review photos
#   --preloaded       Deprecated compatibility path; Dockerfile preloads runtime state
#   --push REPO       Push preloaded image to Docker Hub (e.g., user/immich-webarena:latest)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
NUM_AGENTS=5
PER_USER=300
OUTPUT="$PROJECT_DIR/seed/photos"
IMAGE_NAME="immich-webarena"
SKIP_DOWNLOAD=0
SKIP_BUILD=0
PRELOADED=0
PUSH_REPO=""

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --num-agents)  NUM_AGENTS="$2";   shift 2 ;;
        --per-user)    PER_USER="$2";     shift 2 ;;
        --output)      OUTPUT="$2";       shift 2 ;;
        --image)       IMAGE_NAME="$2";   shift 2 ;;
        --skip-download) SKIP_DOWNLOAD=1; shift ;;
        --skip-seed)   echo "NOTE: --skip-seed is deprecated; seeding happens inside the Dockerfile."; shift ;;
        --skip-build)  SKIP_BUILD=1;      shift ;;
        --preloaded)   PRELOADED=1;       shift ;;
        --push)        PUSH_REPO="$2"; PRELOADED=1; shift 2 ;;
        -h|--help)
            sed -n '/^# Usage/,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "========================================"
echo "  Immich WebArena — Build Pipeline"
echo "========================================"
echo "  Agents:      $NUM_AGENTS  (admin + agent1..agent${NUM_AGENTS})"
echo "  Photos/user: $PER_USER"
echo "  Photo dir:   $OUTPUT"
echo "  Docker image: $IMAGE_NAME"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Download photos
# ---------------------------------------------------------------------------
if [ "$SKIP_DOWNLOAD" -eq 0 ]; then
    echo "=== [1/3] Downloading photos ==="
    "$SCRIPT_DIR/download-photos.py" \
        --num-agents "$NUM_AGENTS" \
        --per-user "$PER_USER" \
        --output "$OUTPUT"
    echo ""
else
    echo "=== [1/3] Skipping download (--skip-download) ==="
fi

# ---------------------------------------------------------------------------
# Step 2: Manual review pause
# ---------------------------------------------------------------------------
if [ "$SKIP_DOWNLOAD" -eq 0 ] && [ "$SKIP_BUILD" -eq 0 ]; then
    echo "=== MANUAL REVIEW ==="
    echo ""
    echo "Photos are in: $OUTPUT"
    echo ""
    echo "Current counts:"
    for d in "$OUTPUT"/*/; do
        [ -d "$d" ] || continue
        count=$(find "$d" -type f | wc -l | tr -d ' ')
        printf "  %-12s %s images\n" "$(basename "$d"):" "$count"
    done
    echo ""
    echo "You can now open $OUTPUT/ and delete any unwanted images."
    echo "When ready, press Enter to continue (or Ctrl+C to abort)."
    read -r _
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 3: Docker build, including seeding inside the Dockerfile
# ---------------------------------------------------------------------------
if [ "$SKIP_BUILD" -eq 0 ]; then
    echo "=== [2/2] Building Docker image with Dockerfile seeding: $IMAGE_NAME ==="
    docker build -t "$IMAGE_NAME" "$PROJECT_DIR"
    echo ""

    if [ "$PRELOADED" -eq 1 ]; then
        echo "=== [bonus] Building compatibility preloaded image ==="
        PRELOAD_ARGS=(--skip-base-build --base-image "$IMAGE_NAME" --image "${IMAGE_NAME}:preloaded")
        if [ -n "$PUSH_REPO" ]; then
            PRELOAD_ARGS+=(--push "$PUSH_REPO")
        fi
        "$SCRIPT_DIR/build-preloaded.sh" "${PRELOAD_ARGS[@]}"
    else
        echo "========================================"
        echo "  Done!"
        echo "  Run: docker run -p 2283:2283 $IMAGE_NAME"
        echo "========================================"
    fi
else
    echo "=== [2/2] Skipping docker build (--skip-build) ==="
    echo ""
    echo "Reviewed photos are in $OUTPUT/. Build with:"
    echo "  docker build -t $IMAGE_NAME $PROJECT_DIR"
fi
