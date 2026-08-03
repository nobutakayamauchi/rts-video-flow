#!/usr/bin/env python3
"""Resolve per-asset audio, narration, timings, subtitles, and transcript.

This is the unified successor to screenshot-only narration processing.

Supported audio modes:
- source: use the original video's audio
- narration: mute the source video and use the attached narration
- mute: do not use or transcribe audio

Images cannot use source audio. A narrated image is displayed for the narration
duration. A narrated video keeps the source-video duration; narration longer
than the source is rejected so speech is not silently truncated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

AUDIO_MODES = {"source", "narration", "mute"}
SUBTITLE_MODES = {"auto", "none"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare all Vlog asset audio, narration, subtitles, and transcript."
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--output-subtitles", type=Path, required=True)
    parser.add_argument("--output-transcript", type=Path, required=True)
    parser.add_argument(
        "--skip-transcription",
        action="store_true",
        help="Resolve timings and audio modes without running Whisper.",
    )
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"Malformed JSON in {path}: {exc}")


def run_checked(command: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except FileNotFoundError as exc:
        fail(f"Command not found: {command[0]} ({exc})")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        fail(f"Command failed: {' '.join(command)}\n{detail}")


def probe_duration(path: Path) -> float:
    result = run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
    )
    try:
        return max(0.1, float(result.stdout.strip()))
    except ValueError:
        fail(f"Could not read duration for {path}")


def has_audio_stream(path: Path) -> bool:
    result = run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
    )
    return bool(result.stdout.strip())


def extract_audio(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output),
        ]
    )


def run_transcription(python: Path, audio: Path, output: Path, root: Path) -> None:
    run_checked(
        [
            str(python),
            str(root / "scripts" / "transcribe.py"),
            "--input",
            str(audio),
            "--output",
            str(output),
        ]
    )


def run_segmentation(python: Path, source: Path, output: Path, root: Path) -> None:
    run_checked(
        [
            str(python),
            str(root / "scripts" / "segment_subtitles.py"),
            "--input",
            str(source),
            "--output",
            str(output),
        ]
    )


def default_audio_mode(item: dict[str, Any], asset_type: str) -> str:
    value = item.get("audioMode")
    if isinstance(value, str) and value in AUDIO_MODES:
        return value
    narration = item.get("narration")
    if isinstance(narration, str) and narration.strip():
        return "narration"
    return "source" if asset_type == "video" else "mute"


def default_subtitle_mode(item: dict[str, Any], audio_mode: str) -> str:
    value = item.get("subtitleMode")
    if isinstance(value, str) and value in SUBTITLE_MODES:
        return value
    return "auto" if audio_mode != "mute" else "none"


def append_shifted_subtitles(
    merged: list[dict[str, Any]],
    local_subtitles: Any,
    *,
    cursor: float,
    asset_id: str,
    source_role: str,
) -> None:
    if not isinstance(local_subtitles, list):
        return
    for local in local_subtitles:
        if not isinstance(local, dict):
            continue
        shifted = dict(local)
        shifted["id"] = len(merged)
        shifted["start"] = round(cursor + float(local.get("start", 0.0)), 3)
        shifted["end"] = round(cursor + float(local.get("end", 0.0)), 3)
        shifted["assetId"] = asset_id
        shifted["sourceRole"] = source_role
        merged.append(shifted)


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    root = Path(__file__).resolve().parent.parent
    manifest = load_json(args.manifest)

    if not project.is_dir():
        fail(f"Project folder not found: {project}")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("timeline"), list):
        fail("Manifest must contain a timeline list")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    enriched: list[dict[str, Any]] = []
    merged_subtitles: list[dict[str, Any]] = []
    transcript_sections: list[str] = []
    warnings: list[dict[str, str]] = []
    cursor = 0.0

    for index, raw in enumerate(manifest["timeline"]):
        if not isinstance(raw, dict):
            continue

        item = dict(raw)
        asset_type = item.get("type")
        source_value = item.get("source")
        if asset_type not in {"video", "image"} or not isinstance(source_value, str):
            continue

        source = project / source_value
        if not source.is_file():
            fail(f"Missing timeline asset: {source}")

        asset_id = str(item.get("id") or f"asset-{index + 1:03d}")
        item["id"] = asset_id
        role = str(item.get("role", "asset"))
        audio_mode = default_audio_mode(item, asset_type)
        subtitle_mode = default_subtitle_mode(item, audio_mode)
        item["audioMode"] = audio_mode
        item["subtitleMode"] = subtitle_mode

        source_duration = probe_duration(source) if asset_type == "video" else None
        narration_path: Path | None = None
        narration_duration: float | None = None
        narration_value = item.get("narration")
        if isinstance(narration_value, str) and narration_value.strip():
            narration_path = project / narration_value
            if not narration_path.is_file():
                fail(f"Missing narration audio: {narration_path}")
            narration_duration = probe_duration(narration_path)
            item["narrationDuration"] = round(narration_duration, 3)

        audio_for_transcription: Path | None = None
        item_warnings: list[str] = []

        if asset_type == "image":
            if audio_mode == "source":
                audio_mode = "mute"
                subtitle_mode = "none"
                item["audioMode"] = audio_mode
                item["subtitleMode"] = subtitle_mode
                item_warnings.append("Images cannot use source audio; changed to mute.")

            if audio_mode == "narration":
                if narration_path is None or narration_duration is None:
                    fail(f"Narration mode requires narration audio: {asset_id}")
                duration = narration_duration
                item["durationSeconds"] = round(duration, 3)
                audio_for_transcription = narration_path
            else:
                duration = max(0.5, float(item.get("durationSeconds", 5.0)))
        else:
            assert source_duration is not None
            duration = source_duration
            item["sourceDuration"] = round(source_duration, 3)

            if audio_mode == "narration":
                if narration_path is None or narration_duration is None:
                    fail(f"Narration mode requires narration audio: {asset_id}")
                if narration_duration > source_duration + 0.25:
                    fail(
                        "Narration is longer than its video and would be truncated: "
                        f"{asset_id} narration={narration_duration:.3f}s "
                        f"video={source_duration:.3f}s"
                    )
                if narration_duration + 0.75 < source_duration:
                    item_warnings.append(
                        "Narration ends before the video; the remaining tail will be silent."
                    )
                audio_for_transcription = narration_path
            elif audio_mode == "source":
                if has_audio_stream(source):
                    extracted = args.work_dir / f"asset-{index:03d}-source.wav"
                    extract_audio(source, extracted)
                    audio_for_transcription = extracted
                else:
                    item_warnings.append(
                        "Source audio mode selected, but the video has no audio stream."
                    )
            elif audio_mode == "mute":
                audio_for_transcription = None

        item["timelineStart"] = round(cursor, 3)
        item["resolvedDuration"] = round(duration, 3)

        if item_warnings:
            item["audioWarnings"] = item_warnings
            for message in item_warnings:
                warnings.append({"assetId": asset_id, "message": message})

        if (
            audio_for_transcription is not None
            and subtitle_mode == "auto"
            and not args.skip_transcription
        ):
            prefix = args.work_dir / f"asset-{index:03d}"
            whisper_json = prefix.with_suffix(".whisper.json")
            subtitle_json = prefix.with_suffix(".subtitles.json")
            run_transcription(args.python, audio_for_transcription, whisper_json, root)
            run_segmentation(args.python, whisper_json, subtitle_json, root)

            whisper_payload = load_json(whisper_json)
            local_subtitles = load_json(subtitle_json)
            append_shifted_subtitles(
                merged_subtitles,
                local_subtitles,
                cursor=cursor,
                asset_id=asset_id,
                source_role=f"{role}-{audio_mode}",
            )

            text = ""
            if isinstance(whisper_payload, dict):
                text = str(whisper_payload.get("text", "")).strip()
            transcript_sections.append(
                f"## {index + 1}. {role} ({asset_id})\n\n{text or '_No speech detected._'}\n"
            )

        enriched.append(item)
        cursor += duration

    manifest["version"] = max(2, int(manifest.get("version", 1)))
    manifest["timeline"] = enriched
    manifest["totalDurationSeconds"] = round(cursor, 3)
    manifest["transcriptionSkipped"] = bool(args.skip_transcription)
    manifest["audioWarnings"] = warnings

    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    args.output_subtitles.parent.mkdir(parents=True, exist_ok=True)
    args.output_subtitles.write_text(
        json.dumps(merged_subtitles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.skip_transcription:
        transcript_body = "# Transcript\n\nPreview mode: transcription was skipped.\n"
    else:
        transcript_body = "# Transcript\n\n"
        transcript_body += "\n".join(transcript_sections) or "_No transcribable audio found._\n"
    args.output_transcript.parent.mkdir(parents=True, exist_ok=True)
    args.output_transcript.write_text(transcript_body, encoding="utf-8")

    print(f"Prepared timeline items: {len(enriched)}")
    print(f"Subtitles: {len(merged_subtitles)}")
    print(f"Audio warnings: {len(warnings)}")
    print(f"Transcription skipped: {args.skip_transcription}")
    print(f"Total duration: {cursor:.3f} sec")
    print(f"Saved manifest: {args.output_manifest}")
    print(f"Saved subtitles: {args.output_subtitles}")
    print(f"Saved transcript: {args.output_transcript}")


if __name__ == "__main__":
    main()
