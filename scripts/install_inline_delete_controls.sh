#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_TAG='<script src="/static/delete_controls.js?v=20260802-3"></script>'
FILES=(
  "${ROOT_DIR}/web_console/static/index.html"
  "${ROOT_DIR}/web_console/static/index-v2.html"
)

python3 - "${SCRIPT_TAG}" "${FILES[@]}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

tag = sys.argv[1]
paths = [Path(value) for value in sys.argv[2:]]
for path in paths:
    if not path.is_file():
        raise SystemExit(f"[error] HTML file not found: {path}")
    text = path.read_text(encoding="utf-8")
    text = re.sub(
        r'\s*<script src="(?:/)?static/delete_controls\.js\?v=[^"]+"></script>\s*',
        "\n",
        text,
    )
    if "</body>" not in text:
        raise SystemExit(f"[error] </body> not found in {path}")
    text = text.replace("</body>", f"{tag}\n</body>", 1)
    path.write_text(text, encoding="utf-8")
    print(f"[ok] Inline delete controls installed: {path.name}")
PY
