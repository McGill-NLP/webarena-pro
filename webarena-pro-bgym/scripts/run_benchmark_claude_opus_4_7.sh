#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "anthropic/claude-opus-4-7" \
  "Claude Opus 4.7 High Thinking" \
  "/mnt/data/neurips_runs/neurips_claude_opus_4_7_high_thinking" \
  "$@"
