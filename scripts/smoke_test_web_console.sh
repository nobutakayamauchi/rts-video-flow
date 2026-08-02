#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${VLOG_SMOKE_BASE_URL:-http://127.0.0.1:8000}"
PROJECT="__smoke-$(date +%s)-$$"
TMP_DIR="$(mktemp -d)"
VIDEO_FILE="${TMP_DIR}/smoke.mp4"
ADD_JSON="${TMP_DIR}/add.json"
DELETE_JSON="${TMP_DIR}/delete.json"
REJECT_JSON="${TMP_DIR}/reject.json"

cleanup() {
  rm -rf "${TMP_DIR}" "${ROOT_DIR}/projects/${PROJECT}" "${ROOT_DIR}/output/${PROJECT}"
}
trap cleanup EXIT

printf 'rts-vlog-smoke' > "${VIDEO_FILE}"

echo "[smoke] upload video as opening"
curl -fsS \
  -F "project=${PROJECT}" \
  -F "action=save" \
  -F "role=opening" \
  -F "description=smoke" \
  -F "media=@${VIDEO_FILE};type=video/mp4" \
  "${BASE_URL}/api/material" > "${ADD_JSON}"

ITEM_ID="$(python3 - "${ADD_JSON}" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
item_id = payload.get("item", {}).get("id")
if not item_id:
    raise SystemExit("missing item id")
print(item_id)
PY
)"

echo "[smoke] delete uploaded material through POST action"
curl -fsS \
  -F "project=${PROJECT}" \
  -F "action=delete" \
  -F "item_id=${ITEM_ID}" \
  "${BASE_URL}/api/material" > "${DELETE_JSON}"

python3 - "${DELETE_JSON}" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("timeline") != []:
    raise SystemExit("timeline was not emptied")
if not payload.get("movedToTrash"):
    raise SystemExit("deleted file was not moved to trash")
PY

echo "[smoke] reject video registered as screenshot"
HTTP_CODE="$(curl -sS -o "${REJECT_JSON}" -w '%{http_code}' \
  -F "project=${PROJECT}" \
  -F "action=save" \
  -F "role=screenshot" \
  -F "description=wrong-kind" \
  -F "media=@${VIDEO_FILE};type=video/mp4" \
  "${BASE_URL}/api/material")"

if [[ "${HTTP_CODE}" != "400" ]]; then
  echo "[error] expected HTTP 400 for screenshot/video mismatch, got ${HTTP_CODE}" >&2
  cat "${REJECT_JSON}" >&2 || true
  exit 1
fi

echo "[ok] Vlog API smoke test passed"
