#!/usr/bin/env python3
"""Resolve per-asset audio, narration patches, timings, subtitles, and transcript.

Supported whole-asset audio modes:
- source: use the original video's audio
- narration: mute the source video and use one attached narration
- mute: do not use the source audio

Video items may also contain ``narrationSegments``. Each segment replaces only
its selected source-audio interval with separate narration audio. Segment
ranges are relative to the start of that source video and may not overlap.
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
SEGMENT_MODES = {"replace"}


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


def run_checked(
    command: list[str], *, capture_output: bool = False
) -> subprocess.CompletedProcess[str]:
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


def ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def normalize_narration_segments(
    raw_segments: object,
    *,
    asset_id: str,
    duration: float,
) -> list[dict[str, Any]]:
    if raw_segments in (None, []):
        return []
    if not isinstance(raw_segments, list):
        raise ValueError("narrationSegments must be a list")

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_segments):
        if not isinstance(raw, dict):
            raise ValueError(f"narrationSegments[{index}] must be an object")
        narration = raw.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(f"narrationSegments[{index}] requires narration")
        try:
            start = round(float(raw.get("startSeconds")), 3)
            end = round(float(raw.get("endSeconds")), 3)
        except (TypeError, ValueError):
            raise ValueError(
                f"narrationSegments[{index}] requires numeric startSeconds/endSeconds"
            ) from None
        if start < 0 or end <= start:
            raise ValueError(f"narrationSegments[{index}] has an invalid range")
        if end > duration + 0.05:
            raise ValueError(
                f"narrationSegments[{index}] ends after the video: {end:.3f} > {duration:.3f}"
            )
        mode = str(raw.get("mode", "replace"))
        if mode not in SEGMENT_MODES:
            raise ValueError(f"narrationSegments[{index}] has unsupported mode: {mode}")
        subtitle_mode = str(raw.get("subtitleMode", "auto"))
        if subtitle_mode not in SUBTITLE_MODES:
            raise ValueError(
                f"narrationSegments[{index}] has unsupported subtitleMode: {subtitle_mode}"
            )
        normalized.append(
            {
                **raw,
                "id": str(raw.get("id") or f"{asset_id}-segment-{index + 1:03d}"),
                "startSeconds": start,
                "endSeconds": end,
                "mode": mode,
                "subtitleMode": subtitle_mode,
                "narration": narration.strip(),
            }
        )

    normalized.sort(key=lambda segment: (segment["startSeconds"], segment["endSeconds"]))
    seen_ids: set[str] = set()
    previous: dict[str, Any] | None = None
    for segment in normalized:
        segment_id = str(segment["id"])
        if segment_id in seen_ids:
            raise ValueError(f"Duplicate narration segment id: {segment_id}")
        seen_ids.add(segment_id)
        if previous and ranges_overlap(
            float(previous["startSeconds"]),
            float(previous["endSeconds"]),
            float(segment["startSeconds"]),
            float(segment["endSeconds"]),
        ):
            raise ValueError(
                "Narration segments may not overlap: "
                f"{previous['id']} and {segment['id']}"
            )
        previous = segment
    return normalized


def subtitle_overlaps_ranges(
    subtitle: dict[str, Any], ranges: list[dict[str, Any]]
) -> bool:
    try:
        start = float(subtitle.get("start", 0.0))
        end = float(subtitle.get("end", start))
    except (TypeError, ValueError):
        return False
    return any(
        ranges_overlap(
            start,
            end,
            float(segment["startSeconds"]),
            float(segment["endSeconds"]),
        )
        for segment in ranges
    )


def append_shifted_subtitles(
    merged: list[dict[str, Any]],
    local_subtitles: Any,
    *,
    cursor: float,
    asset_id: str,
    source_role: str,
    local_offset: float = 0.0,
    excluded_ranges: list[dict[str, Any]] | None = None,
) -> None:
    if not isinstance(local_subtitles, list):
        return
    for local in local_subtitles:
        if not isinstance(local, dict):
            continue
        if excluded_ranges and subtitle_overlaps_ranges(local, excluded_ranges):
            continue
        shifted = dict(local)
        shifted["id"] = len(merged)
        shifted["start"] = round(
            cursor + local_offset + float(local.get("start", 0.0)), 3
        )
        shifted["end"] = round(
            cursor + local_offset + float(local.get("end", 0.0)), 3
        )
        shifted["assetId"] = asset_id
        shifted["sourceRole"] = source_role
        merged.append(shifted)


def transcribe_audio(
    *,
    python: Path,
    audio: Path,
    prefix: Path,
    root: Path,
) -> tuple[Any, Any]:
    whisper_json = prefix.with_suffix(".whisper.json")
    subtitle_json = prefix.with_suffix(".subtitles.json")
    run_transcription(python, audio, whisper_json, root)
    run_segmentation(python, whisper_json, subtitle_json, root)
    return load_json(whisper_json), load_json(subtitle_json)


def transcript_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("text", "")).strip()


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
        duration = (
            source_duration
            if source_duration is not None
            else max(0.5, float(item.get("durationSeconds", 5.0)))
        )
        if source_duration is not None:
            item["sourceDuration"] = round(source_duration, 3)

        narration_path: Path | None = None
        narration_duration: float | None = None
        narration_value = item.get("narration")
        if isinstance(narration_value, str) and narration_value.strip():
            narration_path = project / narration_value
            if not narration_path.is_file():
                fail(f"Missing narration audio: {narration_path}")
            narration_duration = probe_duration(narration_path)
            item["narrationDuration"] = round(narration_duration, 3)

        try:
            segments = normalize_narration_segments(
                item.get("narrationSegments"),
                asset_id=asset_id,
                duration=duration,
            )
        except ValueError as exc:
            fail(f"Invalid narration segments for {asset_id}: {exc}")
        if asset_type == "image" and segments:
            fail(f"Range narration is only supported for video assets: {asset_id}")
        if audio_mode == "narration" and segments:
            fail(
                f"Whole-asset narration and range narration cannot be combined: {asset_id}"
            )

        item_warnings: list[str] = []
        prepared_segments: list[dict[str, Any]] = []
        for segment_index, segment in enumerate(segments):
            segment_item = dict(segment)
            segment_path = project / str(segment_item["narration"])
            if not segment_path.is_file():
                fail(f"Missing segment narration audio: {segment_path}")
            segment_duration = probe_duration(segment_path)
            range_duration = float(segment_item["endSeconds"]) - float(
                segment_item["startSeconds"]
            )
            if segment_duration > range_duration + 0.25:
                fail(
                    "Segment narration is longer than its selected range: "
                    f"{segment_item['id']} narration={segment_duration:.3f}s "
                    f"range={range_duration:.3f}s"
                )
            segment_item["narrationDuration"] = round(segment_duration, 3)
            if segment_duration + 0.75 < range_duration:
                message = (
                    "Segment narration ends before its selected range; the remaining "
                    "part of that range will be silent."
                )
                segment_item["audioWarnings"] = [message]
                item_warnings.append(f"{segment_item['id']}: {message}")
            prepared_segments.append(segment_item)

        if prepared_segments:
            item["narrationSegments"] = prepared_segments
        else:
            item.pop("narrationSegments", None)

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
        else:
            assert source_duration is not None
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
            elif audio_mode == "source" and not has_audio_stream(source):
                item_warnings.append(
                    "Source audio mode selected, but the video has no audio stream."
                )

        item["timelineStart"] = round(cursor, 3)
        item["resolvedDuration"] = round(duration, 3)

        if item_warnings:
            item["audioWarnings"] = item_warnings
            for message in item_warnings:
                warnings.append({"assetId": asset_id, "message": message})
        else:
            item.pop("audioWarnings", None)

        if not args.skip_transcription:
            if asset_type == "video" and audio_mode == "source" and has_audio_stream(source):
                extracted = args.work_dir / f"asset-{index:03d}-source.wav"
                extract_audio(source, extracted)
                whisper_payload, local_subtitles = transcribe_audio(
                    python=args.python,
                    audio=extracted,
                    prefix=args.work_dir / f"asset-{index:03d}-source",
                    root=root,
                )
                if subtitle_mode == "auto":
                    append_shifted_subtitles(
                        merged_subtitles,
                        local_subtitles,
                        cursor=cursor,
                        asset_id=asset_id,
                        source_role=f"{role}-source",
                        excluded_ranges=prepared_segments,
                    )
                transcript_sections.append(
                    f"## {index + 1}. {role} ({asset_id}) — source\n\n"
                    f"{transcript_text(whisper_payload) or '_No speech detected._'}\n"
                )
            elif audio_mode == "narration" and narration_path is not None:
                whisper_payload, local_subtitles = transcribe_audio(
                    python=args.python,
                    audio=narration_path,
                    prefix=args.work_dir / f"asset-{index:03d}-narration",
                    root=root,
                )
                if subtitle_mode == "auto":
                    append_shifted_subtitles(
                        merged_subtitles,
                        local_subtitles,
                        cursor=cursor,
                        asset_id=asset_id,
                        source_role=f"{role}-narration",
                    )
                transcript_sections.append(
                    f"## {index + 1}. {role} ({asset_id}) — narration\n\n"
                    f"{transcript_text(whisper_payload) or '_No speech detected._'}\n"
                )

            for segment_index, segment in enumerate(prepared_segments):
                segment_path = project / str(segment["narration"])
                whisper_payload, local_subtitles = transcribe_audio(
                    python=args.python,
                    audio=segment_path,
                    prefix=args.work_dir
                    / f"asset-{index:03d}-segment-{segment_index:03d}",
                    root=root,
                )
                if segment.get("subtitleMode", "auto") == "auto":
                    append_shifted_subtitles(
                        merged_subtitles,
                        local_subtitles,
                        cursor=cursor,
                        local_offset=float(segment["startSeconds"]),
                        asset_id=asset_id,
                        source_role=f"{role}-range-narration",
                    )
                transcript_sections.append(
                    f"### Range {segment['startSeconds']:.3f}–{segment['endSeconds']:.3f}s "
                    f"({segment['id']})\n\n"
                    f"{transcript_text(whisper_payload) or '_No speech detected._'}\n"
                )

        enriched.append(item)
        cursor += duration

    manifest["version"] = max(3, int(manifest.get("version", 1)))
    manifest["timeline"] = enriched
    manifest["totalDurationSeconds"] = round(cursor, 3)
    manifest["transcriptionSkipped"] = bool(args.skip_transcription)
    manifest["audioWarnings"] = warnings

    args.output_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args.output_subtitles.parent.mkdir(parents=True, exist_ok=True)
    args.output_subtitles.write_text(
        json.dumps(merged_subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if args.skip_transcription:
        transcript_body = "# Transcript\n\nPreview mode: transcription was skipped.\n"
    else:
        transcript_body = "# Transcript\n\n"
        transcript_body += (
            "\n".join(transcript_sections) or "_No transcribable audio found._\n"
        )
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
