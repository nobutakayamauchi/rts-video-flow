#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INDEX_FILE="${ROOT_DIR}/web_console/static/index.html"
SCRIPT_TAG='<script src="static/delete_controls.js?v=20260802-1"></script>'

if [[ ! -f "${INDEX_FILE}" ]]; then
  echo "[error] index.html not found: ${INDEX_FILE}" >&2
  exit 1
fi

python3 - "${INDEX_FILE}" "${SCRIPT_TAG}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
tag = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = re.sub(
    r'\s*<script src="static/delete_controls\.js\?v=[^"]+"></script>\s*',
    "\n",
    text,
)
if "</body>" not in text:
    raise SystemExit("[error] </body> not found in index.html")
text = text.replace("</body>", f"{tag}\n</body>", 1)
path.write_text(text, encoding="utf-8")
print("[ok] Inline delete controls installed")
PY
