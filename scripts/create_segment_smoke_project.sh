#!/usr/bin/env bash
set -euo pipefail

STORAGE_ROOT="${1:-/home/ubuntu/rts-video-flow}"
SOURCE_PROJECT="${2:-01}"
TARGET_PROJECT="${3:-01-segment-smoke}"
START_SECONDS="${4:-5}"
END_SECONDS="${5:-7}"

SOURCE_DIR="${STORAGE_ROOT}/projects/${SOURCE_PROJECT}"
TARGET_DIR="${STORAGE_ROOT}/projects/${TARGET_PROJECT}"
PLAN_PATH="${TARGET_DIR}/vlog-plan.json"
AUDIO_DIR="${TARGET_DIR}/narration/segments"
AUDIO_PATH="${AUDIO_DIR}/segment-smoke-tone.m4a"

if [[ ! -f "${SOURCE_DIR}/vlog-plan.json" ]]; then
  echo "[error] Source project plan not found: ${SOURCE_DIR}/vlog-plan.json" >&2
  exit 1
fi

rm -rf "${TARGET_DIR}"
mkdir -p "${TARGET_DIR}"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude '.trash/' "${SOURCE_DIR}/" "${TARGET_DIR}/"
else
  cp -a "${SOURCE_DIR}/." "${TARGET_DIR}/"
  rm -rf "${TARGET_DIR}/.trash"
fi

mkdir -p "${AUDIO_DIR}"
DURATION="$(python3 -c "s=float('${START_SECONDS}'); e=float('${END_SECONDS}'); assert e>s; print(e-s)")"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "sine=frequency=880:sample_rate=48000:duration=${DURATION}" \
  -c:a aac -b:a 128k "${AUDIO_PATH}"

python3 - "${PLAN_PATH}" "${TARGET_DIR}" "${START_SECONDS}" "${END_SECONDS}" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

plan_path = Path(sys.argv[1])
project_dir = Path(sys.argv[2])
start = float(sys.argv[3])
end = float(sys.argv[4])

plan = json.loads(plan_path.read_text(encoding="utf-8"))
timeline = plan.get("timeline")
if not isinstance(timeline, list):
    raise SystemExit("[error] Invalid timeline")

chosen = None
for item in timeline:
    if not isinstance(item, dict) or item.get("type") != "video":
        continue
    source_value = item.get("source")
    if not isinstance(source_value, str):
        continue
    source = project_dir / source_value
    if not source.is_file():
        continue
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(result.stdout.strip())
    if end <= duration:
        chosen = item
        break

if chosen is None:
    raise SystemExit(f"[error] No video is long enough for {start:.3f}-{end:.3f}s")

chosen.pop("narration", None)
chosen.pop("narrationSizeBytes", None)
chosen["audioMode"] = "source"
chosen["subtitleMode"] = "auto"
chosen["narrationSegments"] = [
    {
        "id": "segment-smoke-001",
        "startSeconds": round(start, 3),
        "endSeconds": round(end, 3),
        "mode": "replace",
        "subtitleMode": "none",
        "narration": "narration/segments/segment-smoke-tone.m4a",
    }
]
plan["version"] = max(5, int(plan.get("version", 1)))
plan["project"] = project_dir.name
plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"[ok] Added segment patch to {chosen.get('id', chosen.get('source'))}")
print(f"RANGE={start:.3f}-{end:.3f}")
print("PATCH_AUDIO=narration/segments/segment-smoke-tone.m4a")
PY

bash "${STORAGE_ROOT}/scripts/create_render_job.sh" "${TARGET_PROJECT}" preview
