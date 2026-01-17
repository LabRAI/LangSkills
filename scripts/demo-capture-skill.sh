#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

DOMAIN="linux"
TOPIC_ID=""
OUT_DIR=""
CACHE_DIR=""
NO_VERBATIM_AUDIT="0"
REQUIRE_NETWORK="0"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/demo-capture-skill.sh [--domain <linux|integrations>] [--topic <topic/slug>] [--out <dir>] [--cache-dir <dir>]
    [--no-verbatim-audit] [--require-network]

Examples:
  bash scripts/demo-capture-skill.sh
  bash scripts/demo-capture-skill.sh --domain linux --topic filesystem/find-files
  bash scripts/demo-capture-skill.sh --domain integrations --topic slack/incoming-webhooks

Notes:
  - This script runs ONE capture and prints the generated files.
  - It validates the output with:
      - validate-skills --strict --fail-on-license-review-all
      - validate-skills --strict --require-no-verbatim-copy (unless --no-verbatim-audit)
  - If network fetch fails, it retries with docs/fixtures/web-cache (best-effort),
    unless --require-network is set.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      DOMAIN="${2:-}"; shift 2;;
    --topic)
      TOPIC_ID="${2:-}"; shift 2;;
    --out)
      OUT_DIR="${2:-}"; shift 2;;
    --cache-dir)
      CACHE_DIR="${2:-}"; shift 2;;
    --no-verbatim-audit)
      NO_VERBATIM_AUDIT="1"; shift;;
    --require-network)
      REQUIRE_NETWORK="1"; shift;;
    -h|--help)
      usage; exit 0;;
    *)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 2;;
  esac
done

if [[ -z "$DOMAIN" ]]; then
  echo "Missing --domain" >&2
  exit 2
fi

if [[ -z "$TOPIC_ID" ]]; then
  if [[ "$DOMAIN" == "linux" ]]; then
    TOPIC_ID="filesystem/find-files"
  elif [[ "$DOMAIN" == "integrations" ]]; then
    TOPIC_ID="slack/incoming-webhooks"
  else
    echo "Missing --topic (domain '${DOMAIN}' has no default)" >&2
    exit 2
  fi
fi

IFS='/' read -r -a _parts <<<"$TOPIC_ID"
if [[ "${#_parts[@]}" -eq 3 ]]; then
  TOPIC_ID="${_parts[1]}/${_parts[2]}"
fi
IFS='/' read -r -a _parts2 <<<"$TOPIC_ID"
if [[ "${#_parts2[@]}" -ne 2 ]]; then
  echo "--topic must be 'topic/slug' (got: $TOPIC_ID)" >&2
  exit 2
fi
TOPIC="${_parts2[0]}"
SLUG="${_parts2[1]}"

TMP_BASE="${TMPDIR:-/tmp}"
TMP_BASE="${TMP_BASE%/}"

if [[ -z "$OUT_DIR" ]]; then
  OUT_DIR="$(mktemp -d "${TMP_BASE}/skill-capture-out.XXXXXX")"
fi
if [[ -z "$CACHE_DIR" ]]; then
  CACHE_DIR="$(mktemp -d "${TMP_BASE}/skill-capture-cache.XXXXXX")"
fi

CAPTURE_LOG="$(mktemp "${TMP_BASE}/skill-capture-log.XXXXXX")"
FIXTURE_CACHE="${REPO_ROOT}/docs/fixtures/web-cache"
CACHE_MODE="network"

run_capture() {
  local cache="$1"
  node "${REPO_ROOT}/agents/run_local.js" \
    --domain "${DOMAIN}" \
    --topic "${TOPIC_ID}" \
    --out "${OUT_DIR}" \
    --overwrite \
    --capture \
    --capture-strict \
    --cache-dir "${cache}"
}

echo "[demo] repo=${REPO_ROOT}"
echo "[demo] domain=${DOMAIN}"
echo "[demo] topic=${TOPIC_ID}"
echo "[demo] out=${OUT_DIR}"
echo "[demo] cache=${CACHE_DIR}"

set +e
run_capture "${CACHE_DIR}" 2>&1 | tee "${CAPTURE_LOG}"
CAPTURE_EXIT="${PIPESTATUS[0]}"
set -e

if [[ "${CAPTURE_EXIT}" -ne 0 ]]; then
  if [[ "${REQUIRE_NETWORK}" == "1" ]]; then
    echo "[demo] capture failed and --require-network is set. See log: ${CAPTURE_LOG}" >&2
    exit "${CAPTURE_EXIT}"
  fi
  if grep -Eqi "fetch failed|ENOTFOUND|ECONNRESET|ETIMEDOUT|EAI_AGAIN|ECONNREFUSED|certificate|AbortError" "${CAPTURE_LOG}"; then
    if [[ -d "${FIXTURE_CACHE}" ]]; then
      echo "[demo] capture failed due to network; retrying with fixture cache: ${FIXTURE_CACHE}"
      CACHE_MODE="fixture"
      CACHE_DIR="${FIXTURE_CACHE}"
      run_capture "${CACHE_DIR}"
    else
      echo "[demo] capture failed (network) and fixture cache is missing: ${FIXTURE_CACHE}" >&2
      exit "${CAPTURE_EXIT}"
    fi
  else
    echo "[demo] capture failed (non-network). See log: ${CAPTURE_LOG}" >&2
    exit "${CAPTURE_EXIT}"
  fi
fi

SKILL_DIR="${OUT_DIR}/${DOMAIN}/${TOPIC}/${SLUG}"
SKILL_MD="${SKILL_DIR}/skill.md"
SOURCES_MD="${SKILL_DIR}/reference/sources.md"
META_YAML="${SKILL_DIR}/metadata.yaml"

echo
echo "[demo] validate (strict + publish gate)"
node "${REPO_ROOT}/scripts/validate-skills.js" \
  --skills-root "${OUT_DIR}" \
  --strict \
  --fail-on-license-review-all

if [[ "${NO_VERBATIM_AUDIT}" != "1" ]]; then
  echo
  echo "[demo] validate (verbatim-copy audit; requires cache-dir=${CACHE_DIR} mode=${CACHE_MODE})"
  node "${REPO_ROOT}/scripts/validate-skills.js" \
    --skills-root "${OUT_DIR}" \
    --strict \
    --require-no-verbatim-copy \
    --cache-dir "${CACHE_DIR}"
fi

echo
echo "[demo] outputs:"
echo "  - ${META_YAML}"
echo "  - ${SKILL_MD}"
echo "  - ${SOURCES_MD}"

echo
echo "===== metadata.yaml ====="
cat "${META_YAML}"

echo
echo "===== skill.md ====="
cat "${SKILL_MD}"

echo
echo "===== reference/sources.md ====="
cat "${SOURCES_MD}"

echo
echo "[demo] done (cache_mode=${CACHE_MODE})"
