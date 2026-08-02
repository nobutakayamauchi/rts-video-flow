#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-preview}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${ROOT_DIR}/venv"

if [[ "${MODE}" != "preview" && "${MODE}" != "final" ]]; then
  echo "[error] Mode must be preview or final" >&2
  exit 2
fi

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel

if [[ "${MODE}" == "final" ]]; then
  echo "[setup] Installing CPU-only PyTorch and Whisper dependencies"
  "${VENV_DIR}/bin/python" -m pip install \
    --index-url https://download.pytorch.org/whl/cpu \
    torch
  "${VENV_DIR}/bin/python" -m pip install openai-whisper budoux
else
  echo "[setup] Preview mode skips Whisper dependencies"
fi

cd "${ROOT_DIR}/remotion-project"
npm install --no-audit --no-fund

node --version
npm --version
npx remotion versions
ffmpeg -version 2>&1 | sed -n '1p'
ffprobe -version 2>&1 | sed -n '1p'
