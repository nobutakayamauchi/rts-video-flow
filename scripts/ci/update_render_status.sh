#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${1:-}"
PROJECT="${2:-}"
MODE="${3:-}"
STATUS="${4:-}"
STEP="${5:-}"
MESSAGE="${6:-}"

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

TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

python3 - "${TMP_FILE}" "${JOB_ID}" "${PROJECT}" "${MODE}" "${STATUS}" "${STEP}" "${MESSAGE}" "${GITHUB_RUN_ID:-}" "${GITHUB_RUN_ATTEMPT:-}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "jobId": sys.argv[2],
    "project": sys.argv[3],
    "mode": sys.argv[4],
    "status": sys.argv[5],
    "step": sys.argv[6],
    "message": sys.argv[7],
    "githubRunId": sys.argv[8],
    "githubRunAttempt": sys.argv[9],
    "updatedAt": datetime.now(timezone.utc).isoformat(),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

REMOTE="${ORACLE_USER}@${ORACLE_HOST}"
REMOTE_JOB_DIR="${ORACLE_REPO_DIR}/jobs/${JOB_ID}"
ssh -p "${ORACLE_PORT}" "${REMOTE}" "mkdir -p '${REMOTE_JOB_DIR}'"
scp -P "${ORACLE_PORT}" "${TMP_FILE}" "${REMOTE}:${REMOTE_JOB_DIR}/status.json.tmp"
ssh -p "${ORACLE_PORT}" "${REMOTE}" \
  "mv '${REMOTE_JOB_DIR}/status.json.tmp' '${REMOTE_JOB_DIR}/status.json'"
