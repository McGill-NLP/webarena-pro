#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "vllm/qwen36-36b-moe" \
  "Qwen3.6 36B MoE" \
  "/mnt/data/neurips_runs/neurips_qwen3_6_36b_moe" \
  "$@"
