#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "vllm/qwen35-9b" \
  "Qwen3.5 9B" \
  "/mnt/data/neurips_runs/neurips_qwen35_9b" \
  "$@"
