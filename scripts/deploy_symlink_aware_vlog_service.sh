#!/usr/bin/env bash
set -euo pipefail

SERVICE="${SERVICE:-rts-video-flow-web.service}"
UNIT_PATH="/etc/systemd/system/${SERVICE}"
FEATURE="${FEATURE:-/home/ubuntu/rts-video-flow-segment-test}"
PYTHON="${PYTHON:-/home/ubuntu/rts-video-flow/venv/bin/python3}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 2
fi

for required in \
  "${PYTHON}" \
  "${FEATURE}/web_console/app_v4.py" \
  "${FEATURE}/web_console/app_v3.py" \
  "${FEATURE}/web_console/static/new-vlog.html" \
  "${FEATURE}/web_console/static/timed-narration.html"; do
  if [[ ! -e "${required}" ]]; then
    echo "Missing required path: ${required}" >&2
    exit 3
  fi
done

cat >"${UNIT_PATH}" <<'EOF'
[Unit]
Description=RTS Video Flow Composition Console
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/rts-video-flow-segment-test
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/rts-video-flow/venv/bin/python3 -m uvicorn web_console.app_v4:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl restart "${SERVICE}"

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health; then
    echo
    systemctl status "${SERVICE}" --no-pager -l
    exit 0
  fi
  sleep 1
done

echo "[error] service health check failed" >&2
systemctl status "${SERVICE}" --no-pager -l || true
journalctl -u "${SERVICE}" -n 100 --no-pager || true
exit 1
