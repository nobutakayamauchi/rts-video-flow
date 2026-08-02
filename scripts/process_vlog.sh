#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${1:-}"

if [[ -z "${PROJECT_DIR}" ]]; then
  echo "Usage: ./scripts/process_vlog.sh projects/vlog-001" >&2
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/${PROJECT_DIR}" && ! -d "${PROJECT_DIR}" ]]; then
  echo "[ERROR] Project folder not found: ${PROJECT_DIR}" >&2
  exit 1
fi

if [[ -d "${ROOT_DIR}/${PROJECT_DIR}" ]]; then
  PROJECT_PATH="${ROOT_DIR}/${PROJECT_DIR}"
else
  PROJECT_PATH="$(cd "${PROJECT_DIR}" && pwd)"
fi

PROJECT_NAME="$(basename "${PROJECT_PATH}")"
WORK_DIR="${ROOT_DIR}/temp/${PROJECT_NAME}"
OUTPUT_DIR="${ROOT_DIR}/output/${PROJECT_NAME}"
VENV_PYTHON="${ROOT_DIR}/venv/bin/python3"

mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "[ERROR] Python environment not found. Run ./scripts/setup.sh first." >&2
  exit 1
fi

find_primary_video() {
  find "${PROJECT_PATH}/camera" "${PROJECT_PATH}/screen" \
    -maxdepth 1 -type f \( -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' \) \
    2>/dev/null | sort | head -n 1
}

PRIMARY_VIDEO="$(find_primary_video || true)"
if [[ -z "${PRIMARY_VIDEO}" ]]; then
  echo "[ERROR] No camera or screen video found in ${PROJECT_PATH}." >&2
  exit 1
fi

echo "[1/6] Building asset manifest"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/build_vlog_manifest.py" \
  "${PROJECT_PATH}" --output "${OUTPUT_DIR}/manifest.json"

echo "[2/6] Extracting audio from: ${PRIMARY_VIDEO}"
ffmpeg -y -i "${PRIMARY_VIDEO}" -vn -ac 1 -ar 16000 "${WORK_DIR}/voice_audio.wav" >/dev/null 2>&1

echo "[3/6] Transcribing Japanese speech"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/transcribe.py" \
  --input "${WORK_DIR}/voice_audio.wav" \
  --output "${WORK_DIR}/whisper_result.json"

echo "[4/6] Segmenting subtitles"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/segment_subtitles.py" \
  --input "${WORK_DIR}/whisper_result.json" \
  --output "${WORK_DIR}/subtitles.json"

echo "[5/6] Exporting SRT"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/subtitles_to_srt.py" \
  --input "${WORK_DIR}/subtitles.json" \
  --output "${OUTPUT_DIR}/subtitles.srt"

echo "[6/6] Exporting transcript"
"${VENV_PYTHON}" - "${WORK_DIR}/whisper_result.json" "${OUTPUT_DIR}/transcript.md" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
payload = json.loads(source.read_text(encoding="utf-8"))
text = str(payload.get("text", "")).strip()
target.write_text(f"# Transcript\n\n{text}\n", encoding="utf-8")
print(f"Saved transcript: {target}")
PY

cat > "${OUTPUT_DIR}/NEXT_STEPS.md" <<EOF
# Next steps for ${PROJECT_NAME}

Generated automatically:

- manifest.json
- subtitles.srt
- transcript.md

Manual gate before rendering or publishing:

- [ ] Notifications, names, email addresses and account IDs are not visible
- [ ] API keys, passwords and private URLs are not visible
- [ ] Screen recording is limited to the necessary demonstration
- [ ] Screenshot order in manifest.json is correct
- [ ] Spoken content is safe to publish

The first MVP intentionally stops before automatic publishing.
EOF

echo "Done: ${OUTPUT_DIR}"
