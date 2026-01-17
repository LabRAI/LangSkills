#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DOMAIN="linux"
RUN_ID=""
RUNS_DIR="${REPO_ROOT}/runs"
CACHE_DIR="${REPO_ROOT}/.cache/web"
OUT_DIR=""

CRAWL_MAX_PAGES="5"
CRAWL_MAX_DEPTH="2"
EXTRACT_MAX_DOCS="20"
SKIP_REPO_INGEST="0"

# Note: use `${VAR-default}` (not `${VAR:-default}`) so users can explicitly pass empty to disable LLM.
CURATOR_LLM_PROVIDER="${CURATOR_LLM_PROVIDER-openai}"
CURATOR_LLM_TARGET_ACTIONS="${CURATOR_LLM_TARGET_ACTIONS:-manual}"
CURATOR_LLM_MAX_PROPOSALS="${CURATOR_LLM_MAX_PROPOSALS:-50}"

SKILLGEN_LLM_PROVIDER="${SKILLGEN_LLM_PROVIDER-openai}"
SKILLGEN_ACTIONS="${SKILLGEN_ACTIONS:-auto,manual}"
MAX_SKILLS="${MAX_SKILLS:-5}"
SKILLGEN_CONCURRENCY="${SKILLGEN_CONCURRENCY:-1}"

VALIDATE_STRICT="1"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/closed-loop.sh [options]

Options:
  --domain <name>              Default: linux
  --run-id <id>                Default: auto (timestamp-based)
  --runs-dir <dir>             Default: ./runs
  --cache-dir <dir>            Default: ./.cache/web
  --out <dir>                  Default: <runs-dir>/<run-id>/skills

  --crawl-max-pages <n>        Default: 5
  --crawl-max-depth <n>        Default: 2
  --extract-max-docs <n>       Default: 20
  --skip-repo-ingest           Skip Tier0 github_repo ingest (smoke/debug)

  --curator-llm-provider <p>   Default: openai (or env CURATOR_LLM_PROVIDER)
  --curator-llm-target-actions <set>  Default: manual (or env CURATOR_LLM_TARGET_ACTIONS)
  --curator-llm-max-proposals <n>     Default: 50 (or env CURATOR_LLM_MAX_PROPOSALS)

  --skillgen-llm-provider <p>  Default: openai (or env SKILLGEN_LLM_PROVIDER)
  --skillgen-actions <set>     Default: auto,manual (or env SKILLGEN_ACTIONS)
  --max-skills <n>             Default: 5 (or env MAX_SKILLS)
  --skillgen-concurrency <n>   Default: 1 (or env SKILLGEN_CONCURRENCY)

  --no-validate                Skip validate-skills --strict

Notes:
  - LLM credentials are read from `.env` (OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL) or environment.
  - This script writes logs under: runs/<run-id>/logs/
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="${2:-}"; shift 2;;
    --run-id) RUN_ID="${2:-}"; shift 2;;
    --runs-dir) RUNS_DIR="${2:-}"; shift 2;;
    --cache-dir) CACHE_DIR="${2:-}"; shift 2;;
    --out) OUT_DIR="${2:-}"; shift 2;;
    --crawl-max-pages) CRAWL_MAX_PAGES="${2:-}"; shift 2;;
    --crawl-max-depth) CRAWL_MAX_DEPTH="${2:-}"; shift 2;;
    --extract-max-docs) EXTRACT_MAX_DOCS="${2:-}"; shift 2;;
    --skip-repo-ingest) SKIP_REPO_INGEST="1"; shift;;
    --curator-llm-provider) CURATOR_LLM_PROVIDER="${2:-}"; shift 2;;
    --curator-llm-target-actions) CURATOR_LLM_TARGET_ACTIONS="${2:-}"; shift 2;;
    --curator-llm-max-proposals) CURATOR_LLM_MAX_PROPOSALS="${2:-}"; shift 2;;
    --skillgen-llm-provider) SKILLGEN_LLM_PROVIDER="${2:-}"; shift 2;;
    --skillgen-actions) SKILLGEN_ACTIONS="${2:-}"; shift 2;;
    --max-skills) MAX_SKILLS="${2:-}"; shift 2;;
    --skillgen-concurrency) SKILLGEN_CONCURRENCY="${2:-}"; shift 2;;
    --no-validate) VALIDATE_STRICT="0"; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "Missing --domain" >&2
  exit 2
fi

if [[ -z "$RUN_ID" ]]; then
  RUN_ID="closedloop-${DOMAIN}-$(date -u +%Y%m%d-%H%M%S)-$RANDOM"
fi

RUNS_DIR="$(cd "${RUNS_DIR}" 2>/dev/null && pwd || true)"
if [[ -z "${RUNS_DIR}" ]]; then
  RUNS_DIR="${REPO_ROOT}/runs"
fi

RUN_DIR="${RUNS_DIR}/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
REPORTS_DIR="${RUN_DIR}/reports"

mkdir -p "${LOG_DIR}" "${REPORTS_DIR}"

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="${RUN_DIR}/skills"
fi

echo "[closed-loop] repo=${REPO_ROOT}"
echo "[closed-loop] domain=${DOMAIN}"
echo "[closed-loop] run_id=${RUN_ID}"
echo "[closed-loop] run_dir=${RUN_DIR}"
echo "[closed-loop] cache_dir=${CACHE_DIR}"
echo "[closed-loop] out=${OUT_DIR}"
echo

echo "[closed-loop][1/5] orchestrator (crawl+extract+tier0 ingest) ..."
ORCH_ARGS=(
  "${REPO_ROOT}/agents/orchestrator/run.js"
  --domain "${DOMAIN}"
  --run-id "${RUN_ID}"
  --runs-dir "${RUNS_DIR}"
  --cache-dir "${CACHE_DIR}"
  --crawl-max-pages "${CRAWL_MAX_PAGES}"
  --crawl-max-depth "${CRAWL_MAX_DEPTH}"
  --extract-max-docs "${EXTRACT_MAX_DOCS}"
  --generate-max-topics 0
)
if [[ "${SKIP_REPO_INGEST}" == "1" ]]; then
  ORCH_ARGS+=(--skip-repo-ingest)
fi

node "${ORCH_ARGS[@]}" \
  2>&1 | tee "${LOG_DIR}/01_orchestrator.log"
echo "[closed-loop] orchestrator_log=${LOG_DIR}/01_orchestrator.log"
echo

echo "[closed-loop][2/5] curator (candidates → curation, LLM-enhanced) ..."
node "${REPO_ROOT}/agents/curator/run.js" \
  --domain "${DOMAIN}" \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}" \
  --llm-provider "${CURATOR_LLM_PROVIDER}" \
  --llm-target-actions "${CURATOR_LLM_TARGET_ACTIONS}" \
  --llm-max-proposals "${CURATOR_LLM_MAX_PROPOSALS}" \
  --llm-capture \
  2>&1 | tee "${LOG_DIR}/02_curator.log"
echo "[closed-loop] curator_log=${LOG_DIR}/02_curator.log"
echo

echo "[closed-loop][3/5] skillgen (curation → skills) ..."
node "${REPO_ROOT}/agents/skillgen/run.js" \
  --domain "${DOMAIN}" \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}" \
  --out "${OUT_DIR}" \
  --cache-dir "${CACHE_DIR}" \
  --max-skills "${MAX_SKILLS}" \
  --concurrency "${SKILLGEN_CONCURRENCY}" \
  --actions "${SKILLGEN_ACTIONS}" \
  --llm-provider "${SKILLGEN_LLM_PROVIDER}" \
  --llm-capture \
  --report-json "${REPORTS_DIR}/skillgen.json" \
  2>&1 | tee "${LOG_DIR}/03_skillgen.log"
echo "[closed-loop] skillgen_log=${LOG_DIR}/03_skillgen.log"
echo "[closed-loop] skillgen_report=${REPORTS_DIR}/skillgen.json"
echo

if [[ "${VALIDATE_STRICT}" == "1" ]]; then
  echo "[closed-loop][4/5] validate (validate-skills --strict) ..."
  node "${REPO_ROOT}/scripts/validate-skills.js" \
    --skills-root "${OUT_DIR}" \
    --strict \
    2>&1 | tee "${LOG_DIR}/04_validate.log"
  echo "[closed-loop] validate_log=${LOG_DIR}/04_validate.log"
  echo
else
  echo "[closed-loop][4/5] validate skipped (--no-validate)"
  echo
fi

echo "[closed-loop][5/5] summary ..."
node "${REPO_ROOT}/scripts/closed-loop-summary.js" \
  --domain "${DOMAIN}" \
  --run-id "${RUN_ID}" \
  --runs-dir "${RUNS_DIR}" \
  --out "${OUT_DIR}" \
  --skillgen-report "${REPORTS_DIR}/skillgen.json" \
  2>&1 | tee "${LOG_DIR}/05_summary.log"

echo
echo "[closed-loop] done"
echo "  - run_dir: ${RUN_DIR}"
echo "  - domain_readme: ${OUT_DIR}/${DOMAIN}/README.md"
echo "  - logs: ${LOG_DIR}"
