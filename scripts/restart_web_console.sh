#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

bash scripts/install_inline_delete_controls.sh

pkill -f "uvicorn web_console.app:app" 2>/dev/null || true
sleep 1

nohup bash scripts/start_web_console.sh > web-console.log 2>&1 &
PID=$!
echo "[start] web console pid=${PID}"

for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/ >/dev/null 2>&1; then
    echo "[ok] Vlog web console restarted"
    echo "Open: https://140-238-62-74.sslip.io/vlog/"
    echo "Manage: https://140-238-62-74.sslip.io/vlog/static/manage.html?project=vlog-001"
    exit 0
  fi
  sleep 1
done

echo "[error] Web console did not become ready" >&2
tail -n 80 web-console.log >&2 || true
exit 1
