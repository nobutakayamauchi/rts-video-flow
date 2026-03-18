#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_FILE="${1:-${ROOT_DIR}/input/ai_video_edit.mov}"
TEMP_DIR="${ROOT_DIR}/temp"
OUTPUT_DIR="${ROOT_DIR}/output"
AUDIO_16K="${TEMP_DIR}/audio_16k.wav"
VOICE_AUDIO="${TEMP_DIR}/voice_audio.wav"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $cmd" >&2
    exit 1
  fi
}

require_cmd ffmpeg

if [[ ! -f "${INPUT_FILE}" ]]; then
  echo "[ERROR] Input video not found: ${INPUT_FILE}" >&2
  echo "        Put a file at input/ai_video_edit.mov or pass a custom path:" >&2
  echo "        ./scripts/extract_audio.sh /path/to/video.mov" >&2
  exit 1
fi

mkdir -p "${TEMP_DIR}" "${OUTPUT_DIR}"

echo "[extract_audio] input: ${INPUT_FILE}"
echo "[extract_audio] writing: ${AUDIO_16K}"
ffmpeg -y -i "${INPUT_FILE}" \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le \
  "${AUDIO_16K}"

echo "[extract_audio] writing: ${VOICE_AUDIO}"
ffmpeg -y -i "${INPUT_FILE}" \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le \
  -af "highpass=f=80,lowpass=f=7800" \
  "${VOICE_AUDIO}"

echo "[extract_audio] done"
