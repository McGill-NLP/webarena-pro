#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/run_benchmark_model.sh" \
  "openai/gpt-5.5" \
  "GPT-5.5 High Reasoning" \
  "/mnt/data/neurips_runs/neurips_gpt_5_5_high_reasoning" \
  "$@"
