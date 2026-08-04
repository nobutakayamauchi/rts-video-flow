#!/usr/bin/env bash
set -euo pipefail

PROD="${PROD:-/home/ubuntu/rts-video-flow}"
FEATURE="${FEATURE:-/home/ubuntu/rts-video-flow-segment-test}"
SERVICE="${SERVICE:-rts-video-flow-web.service}"
UNIT_PATH="/etc/systemd/system/${SERVICE}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run with sudo: sudo bash $0" >&2
  exit 2
fi

for required in \
  "${PROD}/venv/bin/python3" \
  "${FEATURE}/web_console/app_v2.py" \
  "${FEATURE}/web_console/app.py"; do
  if [[ ! -e "${required}" ]]; then
    echo "Missing required path: ${required}" >&2
    exit 3
  fi
done

for name in projects output; do
  target="${FEATURE}/${name}"
  source="${PROD}/${name}"
  mkdir -p "${source}"
  if [[ -e "${target}" && ! -L "${target}" ]]; then
    backup="${target}.before-service-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "${target}" "${backup}"
    echo "[backup] ${target} -> ${backup}"
  fi
  ln -sfn "${source}" "${target}"
  chown -h ubuntu:ubuntu "${target}"
done

cat >"${UNIT_PATH}" <<'EOF'
[Unit]
Description=RTS Video Flow Web Console
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/rts-video-flow-segment-test
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/rts-video-flow/venv/bin/python3 -m uvicorn web_console.app_v2:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
EOF

mapfile -t old_pids < <(
  pgrep -f '^/home/ubuntu/rts-video-flow/venv/bin/python3 -m uvicorn web_console\.app_v2:app .*--port 8000' || true
)

systemctl daemon-reload
systemctl enable "${SERVICE}" >/dev/null

for pid in "${old_pids[@]:-}"; do
  [[ -n "${pid}" ]] || continue
  echo "[stop] old PID=${pid}"
  kill -TERM "${pid}" 2>/dev/null || true
done

for _ in $(seq 1 20); do
  alive=0
  for pid in "${old_pids[@]:-}"; do
    [[ -n "${pid}" ]] || continue
    if kill -0 "${pid}" 2>/dev/null; then
      alive=1
    fi
  done
  [[ "${alive}" -eq 0 ]] && break
  sleep 1
done

systemctl restart "${SERVICE}"

ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/health >/tmp/rts-video-flow-health.json; then
    ok=1
    break
  fi
  sleep 1
done

if [[ "${ok}" -ne 1 ]]; then
  echo "[error] service health check failed" >&2
  systemctl status "${SERVICE}" --no-pager -l || true
  journalctl -u "${SERVICE}" -n 100 --no-pager || true
  exit 1
fi

cat /tmp/rts-video-flow-health.json
echo
systemctl status "${SERVICE}" --no-pager -l
