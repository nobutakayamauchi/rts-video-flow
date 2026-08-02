#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-}"
MODE="${2:-preview}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${ROOT_DIR}/.ci-logs"
LOG_FILE="${LOG_DIR}/render-${PROJECT}.log"

if [[ ! "${PROJECT}" =~ ^[A-Za-z0-9._-]{1,80}$ ]]; then
  echo "[error] Invalid project name" >&2
  exit 2
fi
if [[ "${MODE}" != "preview" && "${MODE}" != "final" ]]; then
  echo "[error] Mode must be preview or final" >&2
  exit 2
fi

mkdir -p "${LOG_DIR}"
rm -f "${LOG_FILE}"

# Remotion uses Node's CPU view, which can differ from `nproc` on hosted runners.
AVAILABLE_CORES="$(node -e 'const os=require("os"); console.log(os.availableParallelism ? os.availableParallelism() : os.cpus().length)' 2>/dev/null || true)"
if [[ ! "${AVAILABLE_CORES}" =~ ^[0-9]+$ ]] || (( AVAILABLE_CORES < 1 )); then
  AVAILABLE_CORES=1
fi
REQUESTED_CONCURRENCY="${RENDER_CONCURRENCY:-${AVAILABLE_CORES}}"
if [[ ! "${REQUESTED_CONCURRENCY}" =~ ^[0-9]+$ ]] || (( REQUESTED_CONCURRENCY < 1 )); then
  REQUESTED_CONCURRENCY=1
fi
if (( REQUESTED_CONCURRENCY > AVAILABLE_CORES )); then
  REQUESTED_CONCURRENCY="${AVAILABLE_CORES}"
fi
# Current GitHub-hosted runner reports a Remotion maximum of 2.
if (( REQUESTED_CONCURRENCY > 2 )); then
  REQUESTED_CONCURRENCY=2
fi
export RENDER_CONCURRENCY="${REQUESTED_CONCURRENCY}"

if [[ "${MODE}" == "preview" ]]; then
  export SKIP_TRANSCRIPTION=1
  export VIDEO_WIDTH=640
  export VIDEO_HEIGHT=360
  export VIDEO_FPS=10
else
  export SKIP_TRANSCRIPTION=0
  export VIDEO_WIDTH=1920
  export VIDEO_HEIGHT=1080
  export VIDEO_FPS=30
  export WHISPER_MODELS="${WHISPER_MODELS:-small,base}"
fi

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-2}"

{
  echo "[job] project=${PROJECT}"
  echo "[job] mode=${MODE}"
  echo "[job] profile=${VIDEO_WIDTH}x${VIDEO_HEIGHT}@${VIDEO_FPS}"
  echo "[job] available_cores=${AVAILABLE_CORES}"
  echo "[job] concurrency=${RENDER_CONCURRENCY}"
  bash "${ROOT_DIR}/scripts/process_vlog.sh" "projects/${PROJECT}"
  bash "${ROOT_DIR}/scripts/render_vlog.sh" "${PROJECT}"
} 2>&1 | tee "${LOG_FILE}"

OUTPUT_FILE="${ROOT_DIR}/output/${PROJECT}/vlog.mp4"
if [[ ! -s "${OUTPUT_FILE}" ]]; then
  echo "[error] Rendered file is missing or empty: ${OUTPUT_FILE}" >&2
  exit 1
fi

DURATION="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "${OUTPUT_FILE}")"
VIDEO_STREAMS="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "${OUTPUT_FILE}" | wc -l)"

python3 - "${DURATION}" "${VIDEO_STREAMS}" <<'PY'
import sys

duration = float(sys.argv[1])
streams = int(sys.argv[2])
if duration <= 0:
    raise SystemExit("rendered video duration is not positive")
if streams < 1:
    raise SystemExit("rendered file has no video stream")
print(f"[ok] Validated rendered video: {duration:.3f} sec")
PY

printf '%s\n' "OUTPUT_FILE=${OUTPUT_FILE}"
printf '%s\n' "LOG_FILE=${LOG_FILE}"
