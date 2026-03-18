# rts-video-flow

Scaffold for a Codex-driven video editing pipeline.

## Goals
- Japanese subtitle generation
- Silence cutting (jumpcut)
- Remotion-based rendering
- Modular script-based workflow

## Status
This repository currently contains **structure + starter files only**.
Implementation logic will be added in the next step.

## Setup
1. Bootstrap Python + Remotion dependencies:
   ```bash
   ./scripts/setup.sh
   ```
2. Extract audio from the default input file (`input/ai_video_edit.mov`):
   ```bash
   ./scripts/extract_audio.sh
   ```
   Or pass a custom input video path:
   ```bash
   ./scripts/extract_audio.sh /path/to/video.mov
   ```

## Jumpcut (silence cutting)
After extracting `temp/audio_16k.wav`, run:
```bash
./venv/bin/python3 scripts/jumpcut.py
```
Optional overrides:
```bash
./venv/bin/python3 scripts/jumpcut.py --video input/ai_video_edit.mov --wav temp/audio_16k.wav --output temp/cut_video.mp4
```

## Transcription
After extracting `temp/voice_audio.wav`, run:
```bash
./venv/bin/python3 scripts/transcribe.py
```
Optional overrides:
```bash
./venv/bin/python3 scripts/transcribe.py --input temp/voice_audio.wav --output temp/whisper_result.json
```

## Subtitle segmentation
After transcription, run:
```bash
./venv/bin/python3 scripts/segment_subtitles.py
```
Optional overrides:
```bash
./venv/bin/python3 scripts/segment_subtitles.py --input temp/whisper_result.json --output temp/subtitles.json
```

## Remotion preparation
After jumpcut and subtitle segmentation, run:
```bash
./venv/bin/python3 scripts/prepare_remotion.py
```
Optional overrides:
```bash
./venv/bin/python3 scripts/prepare_remotion.py --video temp/cut_video.mp4 --subtitles temp/subtitles.json --src-dir remotion-project/src
```

## Project Layout
- `input/`
- `output/`
- `temp/`
- `docs/`
- `scripts/`
- `config/`
- `remotion-project/public/`
- `remotion-project/src/`

<!-- tiny test change -->
