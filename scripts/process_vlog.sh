#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${1:-}"
SKIP_TRANSCRIPTION="${SKIP_TRANSCRIPTION:-0}"
VIDEO_WIDTH="${VIDEO_WIDTH:-1920}"
VIDEO_HEIGHT="${VIDEO_HEIGHT:-1080}"
VIDEO_FPS="${VIDEO_FPS:-30}"

if [[ -z "${PROJECT_DIR}" ]]; then
  echo "Usage: ./scripts/process_vlog.sh projects/vlog-001" >&2
  exit 1
fi

if [[ -d "${ROOT_DIR}/${PROJECT_DIR}" ]]; then
  PROJECT_PATH="${ROOT_DIR}/${PROJECT_DIR}"
elif [[ -d "${PROJECT_DIR}" ]]; then
  PROJECT_PATH="$(cd "${PROJECT_DIR}" && pwd)"
else
  echo "[ERROR] Project folder not found: ${PROJECT_DIR}" >&2
  exit 1
fi

PROJECT_NAME="$(basename "${PROJECT_PATH}")"
WORK_DIR="${ROOT_DIR}/temp/${PROJECT_NAME}"
OUTPUT_DIR="${ROOT_DIR}/output/${PROJECT_NAME}"
VENV_PYTHON="${ROOT_DIR}/venv/bin/python3"

mkdir -p "${WORK_DIR}" "${OUTPUT_DIR}"
if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "[ERROR] Run ./scripts/setup.sh first." >&2
  exit 1
fi

find_primary_video() {
  find "${PROJECT_PATH}/camera" "${PROJECT_PATH}/screen" -maxdepth 1 -type f \
    \( -iname '*.mov' -o -iname '*.mp4' -o -iname '*.m4v' -o -iname '*.webm' \) \
    2>/dev/null | sort | head -n 1
}

PRIMARY_VIDEO="$(find_primary_video || true)"
if [[ -z "${PRIMARY_VIDEO}" ]]; then
  echo "[ERROR] No camera or screen video found." >&2
  exit 1
fi

echo "[profile] ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${VIDEO_FPS} fps"
echo "[1/10] Building asset manifest"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/build_vlog_manifest.py" \
  "${PROJECT_PATH}" \
  --output "${WORK_DIR}/base-manifest.json"

if [[ "${SKIP_TRANSCRIPTION}" == "1" ]]; then
  echo "[2/10] Skipping opening audio extraction for preview"
  echo "[3/10] Skipping Whisper transcription for preview"
  printf '{"text":"","segments":[],"previewMode":true}\n' > "${WORK_DIR}/opening-whisper.json"
  echo "[4/10] Writing empty opening subtitles for preview"
  printf '[]\n' > "${WORK_DIR}/opening-subtitles.json"
else
  echo "[2/10] Extracting opening audio"
  ffmpeg -y -i "${PRIMARY_VIDEO}" -vn -ac 1 -ar 16000 \
    "${WORK_DIR}/voice_audio.wav" >/dev/null 2>&1

  echo "[3/10] Transcribing opening"
  "${VENV_PYTHON}" "${ROOT_DIR}/scripts/transcribe.py" \
    --input "${WORK_DIR}/voice_audio.wav" \
    --output "${WORK_DIR}/opening-whisper.json"

  echo "[4/10] Segmenting opening subtitles"
  "${VENV_PYTHON}" "${ROOT_DIR}/scripts/segment_subtitles.py" \
    --input "${WORK_DIR}/opening-whisper.json" \
    --output "${WORK_DIR}/opening-subtitles.json"
fi

echo "[5/10] Processing screenshot narrations"
NARRATION_ARGS=(
  --project "${PROJECT_PATH}"
  --manifest "${WORK_DIR}/base-manifest.json"
  --work-dir "${WORK_DIR}/narrations"
  --python "${VENV_PYTHON}"
  --output-manifest "${OUTPUT_DIR}/manifest.json"
  --output-subtitles "${WORK_DIR}/narration-subtitles.json"
)
if [[ "${SKIP_TRANSCRIPTION}" == "1" ]]; then
  NARRATION_ARGS+=(--skip-transcription)
fi
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/prepare_screenshot_narrations.py" \
  "${NARRATION_ARGS[@]}"

echo "[6/10] Merging subtitles"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/merge_subtitles.py" \
  --output "${WORK_DIR}/subtitles.json" \
  "${WORK_DIR}/opening-subtitles.json" \
  "${WORK_DIR}/narration-subtitles.json"

echo "[7/10] Exporting SRT"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/subtitles_to_srt.py" \
  --input "${WORK_DIR}/subtitles.json" \
  --output "${OUTPUT_DIR}/subtitles.srt"

echo "[8/10] Exporting transcript"
"${VENV_PYTHON}" - \
  "${WORK_DIR}/opening-whisper.json" \
  "${OUTPUT_DIR}/transcript.md" \
  "${SKIP_TRANSCRIPTION}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
skipped = sys.argv[3] == "1"
body = "# Transcript\n\n"
if skipped:
    body += "Preview mode: transcription was skipped.\n"
else:
    body += str(payload.get("text", "")).strip() + "\n"
Path(sys.argv[2]).write_text(body, encoding="utf-8")
PY

echo "[9/10] Preparing Remotion"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/prepare_vlog_remotion.py" \
  "${PROJECT_PATH}" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --subtitles "${WORK_DIR}/subtitles.json" \
  --remotion-dir "${ROOT_DIR}/remotion-project" \
  --width "${VIDEO_WIDTH}" \
  --height "${VIDEO_HEIGHT}" \
  --fps "${VIDEO_FPS}"

echo "[10/10] Writing review gate"
cat > "${OUTPUT_DIR}/NEXT_STEPS.md" <<EOF
# Next steps for ${PROJECT_NAME}

Generated:
- manifest.json
- subtitles.srt
- transcript.md
- screenshot narration audio integration
- Remotion timeline and assets

Render profile: ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${VIDEO_FPS} fps
Preview mode transcription skipped: ${SKIP_TRANSCRIPTION}

Before rendering:
- [ ] No notifications, names, email addresses, account IDs, API keys or private URLs are visible
- [ ] Screenshot explanations are accurate
- [ ] Narration audio is understandable and matched to the correct screenshot
- [ ] Subtitle wording and timing are acceptable
- [ ] Opening, inserted materials and ending are in the intended order

Render:

    ./scripts/render_vlog.sh ${PROJECT_NAME}
EOF

echo "Prepared: ${OUTPUT_DIR}"
echo "Next: review NEXT_STEPS.md, then ./scripts/render_vlog.sh ${PROJECT_NAME}"
