#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "gemini/gemini-3.1-pro-preview" \
  "Gemini 3.1 Pro High Thinking" \
  "/mnt/data/neurips_runs/neurips_gemini_3_1_pro_high_thinking" \
  "$@"
