#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_NAME="${1:-}"

if [[ -z "${PROJECT_NAME}" ]]; then
  echo "Usage: ./scripts/render_vlog.sh vlog-001" >&2
  exit 1
fi

REMOTION_DIR="${ROOT_DIR}/remotion-project"
OUTPUT_DIR="${ROOT_DIR}/output/${PROJECT_NAME}"
OUTPUT_FILE="${OUTPUT_DIR}/vlog.mp4"

if [[ ! -f "${REMOTION_DIR}/src/index.ts" ]]; then
  echo "[ERROR] Remotion sources are not prepared. Run process_vlog.sh first." >&2
  exit 1
fi

if [[ ! -f "${OUTPUT_DIR}/NEXT_STEPS.md" ]]; then
  echo "[ERROR] Output project not found: ${OUTPUT_DIR}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

echo "Before rendering, confirm the privacy checklist in:"
echo "  ${OUTPUT_DIR}/NEXT_STEPS.md"
echo
echo "Rendering ${PROJECT_NAME}..."
(
  cd "${REMOTION_DIR}"
  npx remotion render src/index.ts VlogVideo "${OUTPUT_FILE}" --codec=h264
)

echo "Rendered: ${OUTPUT_FILE}"
