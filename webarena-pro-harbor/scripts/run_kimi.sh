#!/usr/bin/env bash
set -euo pipefail

# Kimi K3.1 Pro through OpenCode and OpenRouter, as in the recorded study.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
Usage: run_kimi.sh <exported-dataset> <job-name> [harbor run arguments...]
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

# Preserve the recorded model registration, reasoning, and media permissions.
# Use OpenRouter directly in place of the study host's audit proxy.
OPENCODE_CONFIG="$(cat <<'JSON'
{
  "share": "disabled",
  "autoupdate": false,
  "small_model": "openrouter/moonshotai/kimi-k3.1-pro",
  "permission": {"*": "allow", "*media_watch*": "deny", "*media_listen*": "deny"},
  "provider": {
    "openrouter": {
      "npm": "@openrouter/ai-sdk-provider",
      "options": {"baseURL": "https://openrouter.ai/api/v1"},
      "models": {
        "moonshotai/kimi-k3.1-pro": {
          "name": "Kimi K3.1 Pro",
          "reasoning": true,
          "tool_call": true,
          "modalities": {"input": ["text", "image"], "output": ["text"]},
          "limit": {"context": 1048576, "output": 32768},
          "options": {"reasoning": {"effort": "high"}, "provider": {"require_parameters": true}},
          "variants": {"high": {"reasoning": {"effort": "high"}}}
        }
      }
    }
  }
}
JSON
)"

exec "${HARBOR_BIN:-harbor}" run \
  --plugin webarena_pro_core.atif_usage:HarborRequestUsage \
  -p "${DATASET}" -a opencode -m openrouter/moonshotai/kimi-k3.1-pro \
  --api-key-name OPENROUTER_API_KEY \
  --ak version=1.19.5 --ak reasoning_effort=high --ak disable_web_search=true \
  --ak "opencode_config=${OPENCODE_CONFIG}" \
  -e docker -n "${N_CONCURRENT:-1}" -k 1 -r 0 \
  -o "${JOBS_DIR:-./jobs}" --job-name "${JOB_NAME}" "$@"
