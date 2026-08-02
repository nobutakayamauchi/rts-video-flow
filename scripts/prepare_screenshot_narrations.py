#!/usr/bin/env python3
"""Prepare screenshot narration audio, durations, and globally-timed subtitles.

Expected project structure:
  projects/<name>/vlog-plan.json
  projects/<name>/narration/<asset-id>.<audio extension>

Each screenshot timeline item may contain:
  assetId: stable identifier
  narration: relative path to narration audio
  explanation: optional short on-screen explanation

This script probes narration duration, optionally transcribes each narration,
converts the result into subtitle units, offsets subtitle timestamps to the
screenshot's position in the full timeline, and writes an enriched manifest
plus merged subtitle JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare screenshot narration metadata and subtitles.")
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-subtitles", type=Path, required=True)
    parser.add_argument(
        "--skip-transcription",
        action="store_true",
        help="Keep narration audio and timing but do not run Whisper or create narration subtitles.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"Malformed JSON in {path}: {exc}")


def probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return max(0.1, float(result.stdout.strip()))
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError) as exc:
        fail(f"Could not read duration for {path}: {exc}")


def video_duration(path: Path) -> float:
    return probe_duration(path)


def run_transcription(python: Path, audio: Path, output: Path, root: Path) -> None:
    subprocess.run(
        [str(python), str(root / "scripts" / "transcribe.py"), "--input", str(audio), "--output", str(output)],
        check=True,
    )


def run_segmentation(python: Path, source: Path, output: Path, root: Path) -> None:
    subprocess.run(
        [str(python), str(root / "scripts" / "segment_subtitles.py"), "--input", str(source), "--output", str(output)],
        check=True,
    )


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    root = Path(__file__).resolve().parent.parent
    manifest = load_json(args.manifest)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("timeline"), list):
        fail("Manifest must contain a timeline list")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    enriched: list[dict[str, Any]] = []
    merged_subtitles: list[dict[str, Any]] = []
    cursor = 0.0

    for index, raw in enumerate(manifest["timeline"]):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        asset_type = item.get("type")
        source_value = item.get("source")
        if not isinstance(source_value, str):
            continue
        source = project / source_value
        if not source.is_file():
            fail(f"Missing timeline asset: {source}")

        if asset_type == "video":
            duration = video_duration(source)
        elif asset_type == "image":
            narration_value = item.get("narration")
            if isinstance(narration_value, str) and narration_value:
                narration_path = project / narration_value
                if not narration_path.is_file():
                    fail(f"Missing narration audio: {narration_path}")
                duration = probe_duration(narration_path)
                item["durationSeconds"] = round(duration, 3)
                item["narrationDuration"] = round(duration, 3)

                if not args.skip_transcription:
                    work_prefix = args.work_dir / f"narration-{index:03d}"
                    whisper_json = work_prefix.with_suffix(".whisper.json")
                    subtitle_json = work_prefix.with_suffix(".subtitles.json")
                    run_transcription(args.python, narration_path, whisper_json, root)
                    run_segmentation(args.python, whisper_json, subtitle_json, root)
                    local_subtitles = load_json(subtitle_json)
                    if isinstance(local_subtitles, list):
                        for local in local_subtitles:
                            if not isinstance(local, dict):
                                continue
                            shifted = dict(local)
                            shifted["id"] = len(merged_subtitles)
                            shifted["start"] = round(cursor + float(local.get("start", 0.0)), 3)
                            shifted["end"] = round(cursor + float(local.get("end", 0.0)), 3)
                            shifted["sourceRole"] = "screenshot-narration"
                            merged_subtitles.append(shifted)
            else:
                duration = max(0.5, float(item.get("durationSeconds", 5.0)))
        else:
            continue

        item["timelineStart"] = round(cursor, 3)
        item["resolvedDuration"] = round(duration, 3)
        enriched.append(item)
        cursor += duration

    manifest["timeline"] = enriched
    manifest["totalDurationSeconds"] = round(cursor, 3)
    manifest["transcriptionSkipped"] = bool(args.skip_transcription)
    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_subtitles.parent.mkdir(parents=True, exist_ok=True)
    args.output_subtitles.write_text(json.dumps(merged_subtitles, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Prepared timeline items: {len(enriched)}")
    print(f"Narration subtitles: {len(merged_subtitles)}")
    print(f"Transcription skipped: {args.skip_transcription}")
    print(f"Total duration: {cursor:.3f} sec")
    print(f"Saved manifest: {args.output_manifest}")
    print(f"Saved narration subtitles: {args.output_subtitles}")


if __name__ == "__main__":
    main()
