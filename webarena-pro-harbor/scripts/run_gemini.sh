#!/usr/bin/env bash
set -euo pipefail

# Gemini 3.1 Pro through OpenCode, using the recorded Google API configuration.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
Usage: run_gemini.sh <exported-dataset> <job-name> [harbor run arguments...]
Requires GOOGLE_GENERATIVE_AI_API_KEY (or GEMINI_API_KEY),
WP_HARBOR_JUDGE_API_KEY, and WP_HARBOR_EVAL_TOKEN.
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

export GOOGLE_GENERATIVE_AI_API_KEY="${GOOGLE_GENERATIVE_AI_API_KEY:-${GEMINI_API_KEY:-}}"
: "${GOOGLE_GENERATIVE_AI_API_KEY:?Load the Google agent API key first}"
: "${WP_HARBOR_JUDGE_API_KEY:?Load the private judge API key first}"
: "${WP_HARBOR_EVAL_TOKEN:?Set the private evaluator token first}"

# Keep the model registration and high-thinking variant in this standalone file.
# Use Google's public endpoint in place of the study host's audit proxy.
OPENCODE_CONFIG="$(cat <<'JSON'
{
  "share": "disabled",
  "autoupdate": false,
  "small_model": "google/gemini-3.1-pro-preview",
  "permission": {"*": "allow", "*media_watch*": "deny", "*media_listen*": "deny"},
  "provider": {
    "google": {
      "npm": "@ai-sdk/google",
      "options": {
        "baseURL": "https://generativelanguage.googleapis.com/v1beta",
        "apiKey": "{env:GOOGLE_GENERATIVE_AI_API_KEY}"
      },
      "models": {
        "gemini-3.1-pro-preview": {
          "name": "Gemini 3.1 Pro Preview",
          "reasoning": true,
          "tool_call": true,
          "modalities": {"input": ["text", "image"], "output": ["text"]},
          "limit": {"context": 1048576, "output": 32768},
          "options": {"thinkingConfig": {"thinkingLevel": "high", "includeThoughts": true}},
          "variants": {"high": {"thinkingConfig": {"thinkingLevel": "high", "includeThoughts": true}}}
        }
      }
    }
  }
}
JSON
)"

exec "${HARBOR_BIN:-harbor}" run \
  -p "${DATASET}" -a opencode -m gemini/gemini-3.1-pro-preview \
  --api-key-name GOOGLE_GENERATIVE_AI_API_KEY \
  --ak version=1.19.5 --ak reasoning_effort=high --ak disable_web_search=true \
  --ak "opencode_config=${OPENCODE_CONFIG}" \
  -e docker -n "${N_CONCURRENT:-1}" -k 1 -r 0 \
  -o "${JOBS_DIR:-./jobs}" --job-name "${JOB_NAME}" "$@"
