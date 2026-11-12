#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "vllm/gemma4-26b-a4b" \
  "Gemma 4 26B A4B" \
  "/mnt/data/neurips_runs/neurips_gemma4_26b_a4b" \
  "$@"
