#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "vllm/qwen36-27b" \
  "Qwen3.6 27B" \
  "/mnt/data/neurips_runs/neurips_qwen3_6_27b" \
  "$@"
