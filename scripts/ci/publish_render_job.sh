#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${1:-}"
PROJECT="${2:-}"
OUTPUT_FILE="${3:-}"
LOG_FILE="${4:-}"

: "${ORACLE_HOST:?ORACLE_HOST is required}"
: "${ORACLE_USER:?ORACLE_USER is required}"
: "${ORACLE_REPO_DIR:?ORACLE_REPO_DIR is required}"
ORACLE_PORT="${ORACLE_PORT:-22}"

if [[ ! "${JOB_ID}" =~ ^[A-Za-z0-9._-]{1,160}$ ]]; then
  echo "[error] Invalid job id" >&2
  exit 2
fi
if [[ ! "${PROJECT}" =~ ^[A-Za-z0-9._-]{1,80}$ ]]; then
  echo "[error] Invalid project name" >&2
  exit 2
fi
if [[ ! -s "${OUTPUT_FILE}" ]]; then
  echo "[error] Output file missing or empty: ${OUTPUT_FILE}" >&2
  exit 1
fi

REMOTE="${ORACLE_USER}@${ORACLE_HOST}"
REMOTE_INCOMING="${ORACLE_REPO_DIR}/output/.incoming/${JOB_ID}"
REMOTE_OUTPUT="${ORACLE_REPO_DIR}/output/${PROJECT}"
REMOTE_LOG_DIR="${ORACLE_REPO_DIR}/jobs/${JOB_ID}/logs"

ssh -p "${ORACLE_PORT}" "${REMOTE}" \
  "mkdir -p '${REMOTE_INCOMING}' '${REMOTE_OUTPUT}' '${REMOTE_LOG_DIR}'"

rsync -az --partial -e "ssh -p ${ORACLE_PORT}" \
  "${OUTPUT_FILE}" \
  "${REMOTE}:${REMOTE_INCOMING}/vlog.mp4"

if [[ -f "${LOG_FILE}" ]]; then
  rsync -az -e "ssh -p ${ORACLE_PORT}" \
    "${LOG_FILE}" \
    "${REMOTE}:${REMOTE_LOG_DIR}/render.log"
fi

ssh -p "${ORACLE_PORT}" "${REMOTE}" bash -s -- \
  "${REMOTE_INCOMING}/vlog.mp4" \
  "${REMOTE_OUTPUT}/vlog.mp4" <<'REMOTE'
set -euo pipefail
incoming="$1"
target="$2"

if [[ ! -s "${incoming}" ]]; then
  echo "[error] Incoming video is missing or empty" >&2
  exit 1
fi

ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name \
  -of csv=p=0 "${incoming}" | grep -q .

duration="$(ffprobe -v error -show_entries format=duration \
  -of default=noprint_wrappers=1:nokey=1 "${incoming}")"
python3 - "${duration}" <<'PY'
import sys
if float(sys.argv[1]) <= 0:
    raise SystemExit("invalid video duration")
PY

mkdir -p "$(dirname "${target}")"
mv -f "${incoming}" "${target}"
echo "[ok] Published ${target}"
REMOTE

echo "[ok] Rendered video returned to Oracle"
