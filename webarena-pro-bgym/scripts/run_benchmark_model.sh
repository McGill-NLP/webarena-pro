#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $(basename "$0") <agent-model-key> <model-label> <exp-root> [webarena-pro run args...]" >&2
  exit 2
fi

AGENT_MODEL="$1"
MODEL_LABEL="$2"
EXP_ROOT="$3"
shift 3
ORIGINAL_ARGS=("$@")

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

TARGET_MODE="all"
TARGET_SITE=""
HAS_N_JOBS=0
HAS_MAX_STEPS=0
IS_EXPLICIT_RESUME=0
IS_DRY_RUN=0
SHOW_HELP=0
TASK_FILTER=""
RUN_ARGS=()
RESUME_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --agent-model|--agent-model=*)
      echo "This wrapper already sets --agent-model to ${AGENT_MODEL}." >&2
      exit 2
      ;;
    --study-dir|--study-dir=*)
      echo "This wrapper manages --study-dir so it can resume model runs automatically." >&2
      exit 2
      ;;
    --site)
      if [[ $# -lt 2 ]]; then
        echo "--site requires a value." >&2
        exit 2
      fi
      TARGET_MODE="site"
      TARGET_SITE="$2"
      shift 2
      ;;
    --site=*)
      TARGET_MODE="site"
      TARGET_SITE="${1#*=}"
      shift
      ;;
    --all)
      TARGET_MODE="all"
      shift
      ;;
    --resume-study|--resume-study=*)
      IS_EXPLICIT_RESUME=1
      RUN_ARGS+=("$1")
      shift
      ;;
    --parallel)
      echo "--parallel has been removed; use --n-jobs instead." >&2
      exit 2
      ;;
    --parallel=*)
      echo "--parallel has been removed; use --n-jobs instead." >&2
      exit 2
      ;;
    --task)
      if [[ $# -lt 2 ]]; then
        echo "--task requires a value." >&2
        exit 2
      fi
      TASK_FILTER="$2"
      RUN_ARGS+=("$1" "$2")
      shift 2
      ;;
    --task=*)
      TASK_FILTER="${1#*=}"
      RUN_ARGS+=("$1")
      shift
      ;;
    --split|--config-dir)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 2
      fi
      # A resumed study keeps its original task definitions and split.
      RUN_ARGS+=("$1" "$2")
      shift 2
      ;;
    --split=*|--config-dir=*)
      RUN_ARGS+=("$1")
      shift
      ;;
    --dry-run)
      IS_DRY_RUN=1
      RUN_ARGS+=("$1")
      shift
      ;;
    -h|--help)
      SHOW_HELP=1
      RUN_ARGS+=("$1")
      shift
      ;;
    --max-steps)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 2
      fi
      HAS_MAX_STEPS=1
      RUN_ARGS+=("$1" "$2")
      RESUME_ARGS+=("$1" "$2")
      shift 2
      ;;
    --max-steps=*)
      HAS_MAX_STEPS=1
      RUN_ARGS+=("$1")
      RESUME_ARGS+=("$1")
      shift
      ;;
    --n-jobs)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 2
      fi
      HAS_N_JOBS=1
      RUN_ARGS+=("$1" "$2")
      RESUME_ARGS+=("$1" "$2")
      shift 2
      ;;
    --n-jobs=*)
      HAS_N_JOBS=1
      RUN_ARGS+=("$1")
      RESUME_ARGS+=("$1")
      shift
      ;;
    --n-relaunch)
      if [[ $# -lt 2 ]]; then
        echo "$1 requires a value." >&2
        exit 2
      fi
      RUN_ARGS+=("$1" "$2")
      RESUME_ARGS+=("$1" "$2")
      shift 2
      ;;
    --n-relaunch=*)
      RUN_ARGS+=("$1")
      RESUME_ARGS+=("$1")
      shift
      ;;
    --skip-preflight|--no-autostart|-v|--verbose|--incomplete-only|--reset-per-task|--no-reset-per-task)
      RUN_ARGS+=("$1")
      RESUME_ARGS+=("$1")
      shift
      ;;
    *)
      RUN_ARGS+=("$1")
      RESUME_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ "${HAS_MAX_STEPS}" == "0" ]]; then
  DEFAULT_MAX_STEPS="${BENCHMARK_MAX_STEPS:-50}"
  RUN_ARGS+=(--max-steps "${DEFAULT_MAX_STEPS}")
  if [[ "${SHOW_HELP}" == "0" && "${IS_EXPLICIT_RESUME}" == "0" ]]; then
    ORIGINAL_ARGS+=(--max-steps "${DEFAULT_MAX_STEPS}")
  fi
fi

N_JOBS_ARGS=()
if [[ "${HAS_N_JOBS}" == "0" && "${IS_EXPLICIT_RESUME}" == "0" && "${IS_DRY_RUN}" == "0" ]]; then
  N_JOBS_ARGS=(--n-jobs "${BENCHMARK_N_JOBS:-4}")
fi

cd "${REPO_DIR}"
: "${UV_CACHE_DIR:=/tmp/uv-cache}"
export UV_CACHE_DIR
mkdir -p "${UV_CACHE_DIR}"

export AGENTLAB_EXP_ROOT="${EXP_ROOT}"
mkdir -p "${AGENTLAB_EXP_ROOT}"

echo "Running WebArena-Pro benchmark with ${MODEL_LABEL} (${AGENT_MODEL})" >&2
echo "Writing AgentLab results to ${AGENTLAB_EXP_ROOT}" >&2

if [[ "${SHOW_HELP}" == "1" || "${IS_EXPLICIT_RESUME}" == "1" ]]; then
  exec uv run webarena-pro run --agent-model "${AGENT_MODEL}" "${ORIGINAL_ARGS[@]}"
fi

if [[ "${IS_DRY_RUN}" == "1" ]]; then
  if [[ "${TARGET_MODE}" == "site" ]]; then
    exec uv run webarena-pro run --site "${TARGET_SITE}" --agent-model "${AGENT_MODEL}" "${RUN_ARGS[@]}"
  fi
  exec uv run webarena-pro run --all --agent-model "${AGENT_MODEL}" "${RUN_ARGS[@]}"
fi

study_dir_for_site() {
  local site="$1"
  local dir_name="${site}"
  if [[ -n "${TASK_FILTER}" ]]; then
    local task_slug
    task_slug="$(printf '%s' "${TASK_FILTER}" | tr -c 'A-Za-z0-9_.-' '_')"
    dir_name="${site}_task_${task_slug}"
  fi
  printf '%s/%s' "${AGENTLAB_EXP_ROOT}" "${dir_name}"
}

study_dir_for_all() {
  if [[ -n "${TASK_FILTER}" ]]; then
    local task_slug
    task_slug="$(printf '%s' "${TASK_FILTER}" | tr -c 'A-Za-z0-9_.-' '_')"
    printf '%s/all_task_%s' "${AGENTLAB_EXP_ROOT}" "${task_slug}"
    return
  fi
  printf '%s' "${AGENTLAB_EXP_ROOT}"
}

run_or_resume_site() {
  local site="$1"
  local study_dir
  study_dir="$(study_dir_for_site "${site}")"

  if [[ -f "${study_dir}/study.pkl.gz" ]]; then
    echo "Resuming ${site} study at ${study_dir}" >&2
    # The guarded expansion also supports empty arrays with Bash 3's set -u.
    uv run webarena-pro run --resume-study "${study_dir}" ${RESUME_ARGS[@]+"${RESUME_ARGS[@]}"}
  else
    echo "Launching ${site} study at ${study_dir}" >&2
    uv run webarena-pro run \
      --site "${site}" \
      ${N_JOBS_ARGS[@]+"${N_JOBS_ARGS[@]}"} \
      --agent-model "${AGENT_MODEL}" \
      --study-dir "${study_dir}" \
      "${RUN_ARGS[@]}"
  fi
}

if [[ "${TARGET_MODE}" == "all" ]]; then
  study_dir="$(study_dir_for_all)"
  mkdir -p "${study_dir}"
  if [[ -f "${study_dir}/study.pkl.gz" || -f "${study_dir}/queue.jsonl" ]]; then
    echo "Resuming all-site study at ${study_dir}" >&2
    exec uv run webarena-pro run --resume-study "${study_dir}" ${RESUME_ARGS[@]+"${RESUME_ARGS[@]}"}
  fi
  echo "Launching all-site study at ${study_dir}" >&2
  exec uv run webarena-pro run \
    --all \
    ${N_JOBS_ARGS[@]+"${N_JOBS_ARGS[@]}"} \
    --agent-model "${AGENT_MODEL}" \
    --study-dir "${study_dir}" \
    "${RUN_ARGS[@]}"
fi

exit_code=0
set +e
run_or_resume_site "${TARGET_SITE}"
rc=$?
set -e
if [[ "${rc}" != "0" ]]; then
  exit_code="${rc}"
fi

exit "${exit_code}"
