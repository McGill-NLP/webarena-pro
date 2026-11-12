#!/usr/bin/env bash
set -euo pipefail

# GPT-6.1 Sol through Codex and OpenRouter, as in the recorded study.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
Usage: run_codex.sh <exported-dataset> <job-name> [harbor run arguments...]
Requires OPENROUTER_API_KEY, WP_HARBOR_JUDGE_API_KEY, and WP_HARBOR_EVAL_TOKEN.
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

# Harbor accepts inline JSON and writes the agent's TOML configuration.
# The key stays in the environment; Responses uses HTTP rather than WebSockets.
CODEX_CONFIG='{
  "model_provider": "openrouter",
  "model_providers": {
    "openrouter": {
      "name": "OpenRouter",
      "base_url": "https://openrouter.ai/api/v1",
      "wire_api": "responses",
      "env_key": "OPENROUTER_API_KEY",
      "requires_openai_auth": false,
      "supports_websockets": false
    }
  }
}'

exec "${HARBOR_BIN:-harbor}" run \
  -p "${DATASET}" -a codex -m openrouter/openai/gpt-6.1-sol \
  --api-key-name OPENROUTER_API_KEY \
  --ak version=0.166.0 --ak reasoning_effort=high --ak disable_web_search=true \
  --ak "config=${CODEX_CONFIG}" \
  -e docker -n "${N_CONCURRENT:-1}" -k 1 -r 0 \
  -o "${JOBS_DIR:-./jobs}" --job-name "${JOB_NAME}" "$@"
