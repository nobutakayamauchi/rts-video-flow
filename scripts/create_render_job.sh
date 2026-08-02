#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="${1:-}"
MODE="${2:-preview}"

if [[ -z "${PROJECT_NAME}" ]]; then
  echo "Usage: bash scripts/create_render_job.sh <project> [preview|final]" >&2
  exit 2
fi

if [[ ! "${PROJECT_NAME}" =~ ^[A-Za-z0-9._-]{1,80}$ ]]; then
  echo "[error] Invalid project name" >&2
  exit 2
fi

if [[ "${MODE}" != "preview" && "${MODE}" != "final" ]]; then
  echo "[error] Mode must be preview or final" >&2
  exit 2
fi

PROJECT_DIR="${ROOT_DIR}/projects/${PROJECT_NAME}"
if [[ ! -f "${PROJECT_DIR}/vlog-plan.json" ]]; then
  echo "[error] Project plan not found: ${PROJECT_DIR}/vlog-plan.json" >&2
  exit 1
fi

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RANDOM_SUFFIX="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(3))
PY
)"
JOB_ID="${PROJECT_NAME}-${TIMESTAMP}-${RANDOM_SUFFIX}"
JOB_DIR="${ROOT_DIR}/jobs/${JOB_ID}"
SNAPSHOT_DIR="${JOB_DIR}/project"

mkdir -p "${SNAPSHOT_DIR}" "${JOB_DIR}/logs"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete --exclude '.trash/' "${PROJECT_DIR}/" "${SNAPSHOT_DIR}/"
else
  cp -a "${PROJECT_DIR}/." "${SNAPSHOT_DIR}/"
  rm -rf "${SNAPSHOT_DIR}/.trash"
fi

python3 - "${JOB_DIR}" "${JOB_ID}" "${PROJECT_NAME}" "${MODE}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

job_dir = Path(sys.argv[1])
job_id = sys.argv[2]
project = sys.argv[3]
mode = sys.argv[4]
created_at = datetime.now(timezone.utc).isoformat()

job = {
    "version": 1,
    "jobId": job_id,
    "project": project,
    "mode": mode,
    "createdAt": created_at,
}
status = {
    "jobId": job_id,
    "project": project,
    "mode": mode,
    "status": "queued",
    "step": "snapshot-created",
    "updatedAt": created_at,
}
(job_dir / "job.json").write_text(
    json.dumps(job, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
(job_dir / "status.json").write_text(
    json.dumps(status, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

printf '%s\n' "[ok] Render job snapshot created"
printf '%s\n' "JOB_ID=${JOB_ID}"
printf '%s\n' "PROJECT=${PROJECT_NAME}"
printf '%s\n' "MODE=${MODE}"
printf '%s\n' "PATH=${JOB_DIR}"
