#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/venv"
REMOTION_DIR="${ROOT_DIR}/remotion-project"
REMOTION_VERSION="4.0.366"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: $cmd" >&2
    exit 1
  fi
}

echo "[setup] project root: ${ROOT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[setup] creating virtual environment at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
else
  echo "[setup] virtual environment already exists: ${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

echo "[setup] upgrading pip"
python -m pip install --upgrade pip

echo "[setup] installing Python dependencies"
python -m pip install torch silero-vad openai-whisper budoux fastapi uvicorn python-multipart

require_cmd ffmpeg
require_cmd ffprobe
echo "[setup] ffmpeg: $(command -v ffmpeg)"
echo "[setup] ffprobe: $(command -v ffprobe)"

require_cmd node
require_cmd npm
require_cmd npx
echo "[setup] node: $(command -v node)"
echo "[setup] npm: $(command -v npm)"
echo "[setup] npx: $(command -v npx)"

mkdir -p "${REMOTION_DIR}"

if [[ ! -f "${REMOTION_DIR}/package.json" ]]; then
  echo "[setup] creating remotion-project/package.json"
  cat > "${REMOTION_DIR}/package.json" <<JSON
{
  "name": "rts-video-flow-remotion",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "dependencies": {
    "@remotion/cli": "${REMOTION_VERSION}",
    "@remotion/google-fonts": "${REMOTION_VERSION}",
    "react": "18.3.1",
    "react-dom": "18.3.1",
    "remotion": "${REMOTION_VERSION}"
  }
}
JSON
fi

echo "[setup] installing Remotion dependencies"
(cd "${REMOTION_DIR}" && npm install)

echo "[setup] done"
