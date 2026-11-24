#!/usr/bin/env bash
set -euo pipefail

# Claude Opus 5.5 through Claude Code/OpenRouter, matching the Kimi-parity run.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
Usage: run_claude_code.sh <exported-dataset> <job-name> [harbor run arguments...]
Requires OPENROUTER_API_KEY, WP_HARBOR_JUDGE_API_KEY, and WP_HARBOR_EVAL_TOKEN.
Writes JOBS_DIR/<job-name>/model_requests.json with input and output tokens for each recorded inference.
Overrides: HARBOR_BIN=harbor, N_CONCURRENT=1, JOBS_DIR=./jobs.
HELP
  exit 0
fi
if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <exported-dataset> <job-name> [harbor run arguments...]" >&2
  exit 2
fi
DATASET="$1"
JOB_NAME="$2"
shift 2

: "${OPENROUTER_API_KEY:?Load the OpenRouter agent API key first}"
: "${WP_HARBOR_JUDGE_API_KEY:?Load the private judge API key first}"
: "${WP_HARBOR_EVAL_TOKEN:?Set the private evaluator token first}"

# OpenRouter's Anthropic Messages endpoint replaces the host-local audit proxy.
exec "${HARBOR_BIN:-harbor}" run \
  --plugin webarena_pro_core.atif_usage:HarborRequestUsage \
  -p "${DATASET}" -a claude-code -m openrouter/anthropic/claude-opus-5.5 \
  --base-url https://openrouter.ai/api --api-key-name OPENROUTER_API_KEY \
  --ak version=2.1.318 --ak reasoning_effort=high --ak disable_web_search=true \
  --ak disallowed_tools=mcp__webarena-pro__media_watch,mcp__webarena-pro__media_listen \
  --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=32768 \
  --ae CLAUDE_CODE_SUBAGENT_MODEL=anthropic/claude-opus-5.5 \
  -e docker -n "${N_CONCURRENT:-1}" -k 1 -r 0 \
  -o "${JOBS_DIR:-./jobs}" --job-name "${JOB_NAME}" "$@"
