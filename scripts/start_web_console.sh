#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${VLOG_HOST:-0.0.0.0}"
PORT="${VLOG_PORT:-8000}"
PYTHON="${ROOT_DIR}/venv/bin/python3"

if [[ ! -x "${PYTHON}" ]]; then
  echo "[ERROR] Run ./scripts/setup.sh first." >&2
  exit 1
fi

cd "${ROOT_DIR}"
echo "RTS Vlog Web Console: http://${HOST}:${PORT}"
exec "${PYTHON}" -m uvicorn web_console.app:app --host "${HOST}" --port "${PORT}"
