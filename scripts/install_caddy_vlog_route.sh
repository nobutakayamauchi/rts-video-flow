#!/usr/bin/env bash
set -euo pipefail

CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
BACKUP="${CADDYFILE}.pre-rts-vlog.$(date +%Y%m%d-%H%M%S)"

if [[ ${EUID} -ne 0 ]]; then
  echo "[ERROR] Run with sudo: sudo bash scripts/install_caddy_vlog_route.sh" >&2
  exit 1
fi

if [[ ! -f "${CADDYFILE}" ]]; then
  echo "[ERROR] Caddyfile not found: ${CADDYFILE}" >&2
  exit 1
fi

cp "${CADDYFILE}" "${BACKUP}"
echo "[backup] ${BACKUP}"

python3 - "${CADDYFILE}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

begin = "# BEGIN RTS VLOG"
end = "# END RTS VLOG"

if begin in text:
    print("[config] RTS Vlog route already exists; no duplicate added")
    sys.exit(0)

match = re.search(r"(?m)^(?P<indent>[ \t]*)route[ \t]*\{[ \t]*$", text)
if not match:
    raise SystemExit("[ERROR] Could not find a standalone 'route {' block in Caddyfile")

indent = match.group("indent")
inner = indent + "    "
block = f'''\n{inner}{begin}\n{inner}redir /vlog /vlog/ 308\n\n{inner}handle_path /vlog/* {{\n{inner}    reverse_proxy 127.0.0.1:8000\n{inner}}}\n\n{inner}handle /static/* {{\n{inner}    reverse_proxy 127.0.0.1:8000\n{inner}}}\n\n{inner}@rts_vlog_api path /api/project/* /api/material /api/narration /api/reorder /api/compile /api/download/* /api/script /api/probe\n{inner}handle @rts_vlog_api {{\n{inner}    reverse_proxy 127.0.0.1:8000\n{inner}}}\n{inner}{end}\n'''

insert_at = match.end()
text = text[:insert_at] + block + text[insert_at:]
path.write_text(text, encoding="utf-8")
print("[config] Added RTS Vlog routes")
PY

if ! caddy validate --config "${CADDYFILE}"; then
  echo "[ERROR] Validation failed; restoring backup" >&2
  cp "${BACKUP}" "${CADDYFILE}"
  exit 1
fi

caddy fmt --overwrite "${CADDYFILE}"
caddy validate --config "${CADDYFILE}"
systemctl reload caddy

echo "[ok] Caddy reloaded"

if ss -ltn | grep -q ':8000 '; then
  echo "[ok] Vlog app is listening on port 8000"
else
  echo "[WARN] Nothing is listening on port 8000. Start the Vlog web console first." >&2
fi

SITE_HOST="$(awk 'NF && $1 !~ /^#/ {gsub(/[{:]/, "", $1); print $1; exit}' "${CADDYFILE}")"
if [[ -n "${SITE_HOST}" ]]; then
  echo "Open: https://${SITE_HOST}/vlog/"
else
  echo "Open: /vlog/ on your Caddy hostname"
fi
