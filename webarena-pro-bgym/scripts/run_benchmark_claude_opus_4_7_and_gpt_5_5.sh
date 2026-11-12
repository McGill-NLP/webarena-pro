#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/run_benchmark_claude_opus_4_7.sh" "$@"
"${SCRIPT_DIR}/run_benchmark_gpt_5_5.sh" "$@"
