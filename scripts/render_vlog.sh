#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="${1:-}"
RENDER_CONCURRENCY="${RENDER_CONCURRENCY:-1}"
AUDIO_SAFETY_MODE="${AUDIO_SAFETY_MODE:-warn}"

if [[ -z "${PROJECT_NAME}" ]]; then
  echo "Usage: ./scripts/render_vlog.sh vlog-001" >&2
  exit 1
fi

case "${AUDIO_SAFETY_MODE}" in
  off|warn|strict) ;;
  *)
    echo "[ERROR] AUDIO_SAFETY_MODE must be off, warn, or strict" >&2
    exit 2
    ;;
esac

REMOTION_DIR="${ROOT_DIR}/remotion-project"
OUTPUT_DIR="${ROOT_DIR}/output/${PROJECT_NAME}"
OUTPUT_FILE="${OUTPUT_DIR}/vlog.mp4"
VENV_PYTHON="${ROOT_DIR}/venv/bin/python3"
AUDIT_JSON="${OUTPUT_DIR}/audio-safety.json"
AUDIT_MARKDOWN="${OUTPUT_DIR}/AUDIO_SAFETY.md"

if [[ ! -f "${REMOTION_DIR}/src/index.ts" ]]; then
  echo "[ERROR] Remotion sources are not prepared. Run process_vlog.sh first." >&2
  exit 1
fi

if [[ ! -f "${OUTPUT_DIR}/NEXT_STEPS.md" ]]; then
  echo "[ERROR] Output project not found: ${OUTPUT_DIR}" >&2
  exit 1
fi

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "[ERROR] Run ./scripts/setup.sh first." >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "Before rendering, confirm the privacy checklist in:"
echo "  ${OUTPUT_DIR}/NEXT_STEPS.md"
echo
echo "Rendering ${PROJECT_NAME} with concurrency=${RENDER_CONCURRENCY}..."
(
  cd "${REMOTION_DIR}"
  npx remotion render src/index.ts VlogVideo "${OUTPUT_FILE}" \
    --codec=h264 \
    --concurrency="${RENDER_CONCURRENCY}"
)

echo "Rendered: ${OUTPUT_FILE}"

if [[ "${AUDIO_SAFETY_MODE}" == "off" ]]; then
  echo "Audio safety audit: skipped (AUDIO_SAFETY_MODE=off)"
  exit 0
fi

echo "Auditing final mixed audio for persistent narrow-band high-frequency tones..."
set +e
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/audit_high_frequency_audio.py" \
  --input "${OUTPUT_FILE}" \
  --json "${AUDIT_JSON}" \
  --markdown "${AUDIT_MARKDOWN}"
AUDIT_STATUS=$?
set -e

case "${AUDIT_STATUS}" in
  0)
    echo "Audio safety audit: PASS"
    echo "Report: ${AUDIT_MARKDOWN}"
    ;;
  2)
    echo "[WARNING] A possible loud, persistent high-frequency tone was detected." >&2
    echo "Review at low device volume before publishing: ${AUDIT_MARKDOWN}" >&2
    if [[ "${AUDIO_SAFETY_MODE}" == "strict" ]]; then
      echo "[ERROR] Strict audio safety mode blocks completion." >&2
      exit 4
    fi
    ;;
  *)
    echo "[WARNING] Audio safety audit could not be completed." >&2
    echo "Review the report and listen at low device volume: ${AUDIT_MARKDOWN}" >&2
    if [[ "${AUDIO_SAFETY_MODE}" == "strict" ]]; then
      echo "[ERROR] Strict audio safety mode blocks completion." >&2
      exit 5
    fi
    ;;
esac
