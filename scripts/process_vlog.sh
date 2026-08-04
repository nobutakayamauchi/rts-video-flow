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

echo "[profile] ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${VIDEO_FPS} fps"
echo "[1/7] Building asset manifest"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/build_vlog_manifest.py" \
  "${PROJECT_PATH}" \
  --output "${WORK_DIR}/base-manifest.json"

echo "[2/7] Resolving per-asset audio, narration, and subtitles"
ASSET_AUDIO_ARGS=(
  --project "${PROJECT_PATH}"
  --manifest "${WORK_DIR}/base-manifest.json"
  --work-dir "${WORK_DIR}/asset-audio"
  --python "${VENV_PYTHON}"
  --output-manifest "${OUTPUT_DIR}/manifest.json"
  --output-subtitles "${OUTPUT_DIR}/subtitles.json"
  --output-transcript "${OUTPUT_DIR}/transcript.md"
)
if [[ "${SKIP_TRANSCRIPTION}" == "1" ]]; then
  ASSET_AUDIO_ARGS+=(--skip-transcription)
fi
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/prepare_asset_audio.py" \
  "${ASSET_AUDIO_ARGS[@]}"

echo "[3/7] Baking range narration patches into render sources"
rm -rf "${OUTPUT_DIR}/render-assets"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/materialize_segment_patches.py" \
  --project "${PROJECT_PATH}" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --output-dir "${OUTPUT_DIR}/render-assets"

echo "[4/7] Applying boundary-only automatic jump cuts"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/apply_boundary_jump_cuts.py" \
  --project "${PROJECT_PATH}" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --subtitles "${OUTPUT_DIR}/subtitles.json" \
  --output-dir "${OUTPUT_DIR}/render-assets/boundary-cuts"

echo "[5/7] Exporting SRT"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/subtitles_to_srt.py" \
  --input "${OUTPUT_DIR}/subtitles.json" \
  --output "${OUTPUT_DIR}/subtitles.srt"

echo "[6/7] Preparing Remotion"
"${VENV_PYTHON}" "${ROOT_DIR}/scripts/prepare_vlog_remotion.py" \
  "${PROJECT_PATH}" \
  --manifest "${OUTPUT_DIR}/manifest.json" \
  --subtitles "${OUTPUT_DIR}/subtitles.json" \
  --remotion-dir "${ROOT_DIR}/remotion-project" \
  --width "${VIDEO_WIDTH}" \
  --height "${VIDEO_HEIGHT}" \
  --fps "${VIDEO_FPS}"

echo "[7/7] Writing review gate"
cat > "${OUTPUT_DIR}/NEXT_STEPS.md" <<EOF
# Next steps for ${PROJECT_NAME}

Generated:
- manifest.json
- subtitles.json
- subtitles.srt
- transcript.md
- per-asset source audio / narration integration
- range narration patches baked into temporary render-source videos
- start/end boundary silence automatically jump-cut with 0.1-second handles
- Remotion timeline and assets

Boundary jump-cut policy:
- only the start and end of each material are eligible
- 0.1 seconds are retained after the prior voice and before the next voice
- adjacent materials therefore retain at most 0.2 seconds of transition silence
- internal pauses and fully silent materials are preserved
- BGM is excluded from silence detection
- project source files are never modified

Render profile: ${VIDEO_WIDTH}x${VIDEO_HEIGHT} @ ${VIDEO_FPS} fps
Preview mode transcription skipped: ${SKIP_TRANSCRIPTION}

Before rendering:
- [ ] No notifications, names, email addresses, account IDs, API keys or private URLs are visible
- [ ] Every video uses the intended audio mode: source, narration, or mute
- [ ] Narration audio is understandable and matched to the correct asset
- [ ] Range narration begins and ends at the intended seconds
- [ ] Automatic boundary cuts did not remove a wanted pause
- [ ] Audio warnings in manifest.json were reviewed
- [ ] Subtitle wording and timing are acceptable
- [ ] Opening, inserted materials and ending are in the intended order

Render:

    ./scripts/render_vlog.sh ${PROJECT_NAME}
EOF

echo "Prepared: ${OUTPUT_DIR}"
echo "Next: review NEXT_STEPS.md, then ./scripts/render_vlog.sh ${PROJECT_NAME}"
