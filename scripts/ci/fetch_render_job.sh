#!/usr/bin/env bash
set -euo pipefail

JOB_ID="${1:-}"
PROJECT="${2:-}"

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

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REMOTE="${ORACLE_USER}@${ORACLE_HOST}"
REMOTE_JOB_DIR="${ORACLE_REPO_DIR}/jobs/${JOB_ID}"
LOCAL_PROJECT_DIR="${ROOT_DIR}/projects/${PROJECT}"
LOCAL_JOB_DIR="${ROOT_DIR}/.ci-jobs/${JOB_ID}"

mkdir -p "${LOCAL_PROJECT_DIR}" "${LOCAL_JOB_DIR}"

ssh -p "${ORACLE_PORT}" "${REMOTE}" \
  "test -f '${REMOTE_JOB_DIR}/job.json' && test -f '${REMOTE_JOB_DIR}/project/vlog-plan.json'"

rsync -az --delete -e "ssh -p ${ORACLE_PORT}" \
  "${REMOTE}:${REMOTE_JOB_DIR}/project/" \
  "${LOCAL_PROJECT_DIR}/"

scp -P "${ORACLE_PORT}" \
  "${REMOTE}:${REMOTE_JOB_DIR}/job.json" \
  "${LOCAL_JOB_DIR}/job.json"

python3 - "${LOCAL_JOB_DIR}/job.json" "${JOB_ID}" "${PROJECT}" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
if payload.get("jobId") != sys.argv[2]:
    raise SystemExit("job id mismatch")
if payload.get("project") != sys.argv[3]:
    raise SystemExit("project mismatch")
if payload.get("mode") not in {"preview", "final"}:
    raise SystemExit("invalid job mode")
PY

echo "[ok] Fetched render job ${JOB_ID} for project ${PROJECT}"
