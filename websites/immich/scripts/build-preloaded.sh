#!/bin/bash
# build-preloaded.sh — Build a pre-warmed Docker image with all data already expanded
#
# This script:
#   1. Builds the base image (with compressed seed tarballs)
#   2. Runs it and waits for full initialization (DB restore, upload/ML extraction)
#   3. Keeps the compressed seed files by default so backend reset still works
#   4. Commits the warm container as the final image
#   5. Optionally pushes to Docker Hub
#
# Usage:
#   ./scripts/build-preloaded.sh [OPTIONS]
#
# Options:
#   --base-image NAME      Base image name (default: immich-webarena:base)
#   --image NAME           Final preloaded image name (default: immich-webarena:preloaded)
#   --push REPO            Push to Docker Hub as REPO (e.g., user/immich-webarena:latest)
#   --skip-base-build      Skip base image build (assume it already exists)
#   --drop-seed-archives   Remove /seed/*.gz in the final image to save space
#   --stop-timeout SECS    Seconds to wait for clean shutdown (default: 30)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
BASE_IMAGE="immich-webarena:base"
FINAL_IMAGE="immich-webarena:preloaded"
PUSH_REPO=""
SKIP_BASE_BUILD=0
DROP_SEED_ARCHIVES=0
STOP_TIMEOUT=30
CONTAINER_NAME="immich-preload-$$"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-image)       BASE_IMAGE="$2";      shift 2 ;;
        --image)            FINAL_IMAGE="$2";      shift 2 ;;
        --push)             PUSH_REPO="$2";        shift 2 ;;
        --skip-base-build)  SKIP_BASE_BUILD=1;     shift ;;
        --drop-seed-archives) DROP_SEED_ARCHIVES=1; shift ;;
        --stop-timeout)     STOP_TIMEOUT="$2";     shift 2 ;;
        -h|--help)
            sed -n '/^# Usage/,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cleanup() {
    echo ""
    echo "[preload] Cleaning up container $CONTAINER_NAME..."
    docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
}
trap cleanup EXIT

echo "========================================"
echo "  Immich WebArena — Preloaded Build"
echo "========================================"
echo "  Base image:  $BASE_IMAGE"
echo "  Final image: $FINAL_IMAGE"
echo "  Push to:     ${PUSH_REPO:-<none>}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Build base image
# ---------------------------------------------------------------------------
if [ "$SKIP_BASE_BUILD" -eq 0 ]; then
    echo "=== [1/5] Building base image: $BASE_IMAGE ==="
    docker build -t "$BASE_IMAGE" "$PROJECT_DIR"
    echo ""
else
    echo "=== [1/5] Skipping base build (--skip-base-build) ==="
    echo ""
fi

# ---------------------------------------------------------------------------
# Step 2: Run container and wait for initialization
# ---------------------------------------------------------------------------
echo "=== [2/5] Starting container for initialization... ==="
docker run -d --name "$CONTAINER_NAME" "$BASE_IMAGE"

echo "  Waiting for Immich to fully initialize (DB restore + upload extraction)..."
echo "  This may take a few minutes on first boot."
echo ""

# Wait for the health endpoint (same as healthcheck.sh)
MAX_WAIT=300  # 5 minutes
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if docker exec "$CONTAINER_NAME" curl -sf http://localhost:2283/api/server/ping > /dev/null 2>&1; then
        echo "  Immich API is responding after ${ELAPSED}s."
        break
    fi
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "ERROR: Container exited unexpectedly."
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    if [ $((ELAPSED % 30)) -eq 0 ]; then
        echo "  Still waiting... (${ELAPSED}s)"
    fi
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "ERROR: Immich did not become healthy within ${MAX_WAIT}s"
    echo "Container logs:"
    docker logs --tail 50 "$CONTAINER_NAME"
    exit 1
fi

# Give a few extra seconds for all services to stabilize
sleep 5
echo ""

# ---------------------------------------------------------------------------
# Step 3: Verify seed markers exist, then optionally remove compressed seed files
# ---------------------------------------------------------------------------
echo "=== [3/5] Verifying preloaded seed state... ==="

# Verify the seed actually ran
docker exec "$CONTAINER_NAME" test -f /data/.seeded \
    || { echo "ERROR: /data/.seeded not found — seed extraction didn't complete"; exit 1; }
docker exec "$CONTAINER_NAME" test -f /cache/.seeded \
    || { echo "ERROR: /cache/.seeded not found — ML cache extraction didn't complete"; exit 1; }

if [ "$DROP_SEED_ARCHIVES" -eq 1 ]; then
    docker exec "$CONTAINER_NAME" rm -f /seed/immich_db.sql.gz /seed/upload.tar.gz /seed/ml-cache.tar.gz
    echo "  Removed /seed/*.gz — saved space in final image."
else
    echo "  Keeping /seed/*.gz so /usr/local/bin/webarena-reset-state can restore state."
fi
echo ""

# ---------------------------------------------------------------------------
# Step 4: Stop container cleanly and commit
# ---------------------------------------------------------------------------
echo "=== [4/5] Stopping container and committing image... ==="

# Stop gracefully so PostgreSQL shuts down cleanly
docker stop -t "$STOP_TIMEOUT" "$CONTAINER_NAME"
echo "  Container stopped."

# Commit with the same CMD/ENTRYPOINT as the original
docker commit \
    --change 'ENTRYPOINT ["tini", "--"]' \
    --change 'CMD ["/usr/local/bin/start.sh"]' \
    --change 'ENV NODE_ENV=production' \
    --change 'EXPOSE 2283' \
    --change 'USER user' \
    "$CONTAINER_NAME" "$FINAL_IMAGE"

echo "  Committed as: $FINAL_IMAGE"

# Show size comparison
BASE_SIZE=$(docker image inspect "$BASE_IMAGE" --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1024/1024}')
FINAL_SIZE=$(docker image inspect "$FINAL_IMAGE" --format '{{.Size}}' | awk '{printf "%.0f MB", $1/1024/1024}')
echo "  Base image:  $BASE_SIZE"
echo "  Final image: $FINAL_SIZE"
echo ""

# ---------------------------------------------------------------------------
# Step 5: Push to Docker Hub (optional)
# ---------------------------------------------------------------------------
if [ -n "$PUSH_REPO" ]; then
    echo "=== [5/5] Pushing to Docker Hub: $PUSH_REPO ==="
    docker tag "$FINAL_IMAGE" "$PUSH_REPO"
    docker push "$PUSH_REPO"
    echo "  Pushed: $PUSH_REPO"
    echo ""
    echo "  Pull with:"
    echo "    docker pull $PUSH_REPO"
    echo "    docker run -p 2283:2283 $PUSH_REPO"
else
    echo "=== [5/5] Skipping push (no --push specified) ==="
    echo ""
    echo "  To push later:"
    echo "    docker tag $FINAL_IMAGE YOUR_USER/immich-webarena:latest"
    echo "    docker push YOUR_USER/immich-webarena:latest"
fi

# Disable the EXIT trap since we're done cleanly
trap - EXIT
docker rm "$CONTAINER_NAME" 2>/dev/null || true

echo ""
echo "========================================"
echo "  Done! Run with:"
echo "    docker run -p 2283:2283 $FINAL_IMAGE"
echo "========================================"
