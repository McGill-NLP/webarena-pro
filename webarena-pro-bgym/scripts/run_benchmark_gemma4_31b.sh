#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "vllm/gemma4-31b" \
  "Gemma 4 31B" \
  "/mnt/data/neurips_runs/neurips_gemma4_31b" \
  "$@"
