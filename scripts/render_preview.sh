#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="${1:-01}"
PROJECT_DIR="projects/${PROJECT_NAME}"
LOG_FILE="${ROOT_DIR}/render-${PROJECT_NAME}.log"

cd "${ROOT_DIR}"

bash scripts/ensure_swap.sh

echo "[preview] Starting no-transcription preview render for ${PROJECT_NAME}"
rm -f "${LOG_FILE}"
nohup env \
  SKIP_TRANSCRIPTION=1 \
  RENDER_CONCURRENCY=1 \
  OMP_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 \
  bash -lc "bash scripts/process_vlog.sh '${PROJECT_DIR}' && bash scripts/render_vlog.sh '${PROJECT_NAME}'" \
  > "${LOG_FILE}" 2>&1 &
PID=$!

echo "[ok] Preview render started: pid=${PID}"
echo "Log: ${LOG_FILE}"
echo "Watch: tail -f ${LOG_FILE}"
echo "When complete: https://140-238-62-74.sslip.io/api/download/${PROJECT_NAME}"
