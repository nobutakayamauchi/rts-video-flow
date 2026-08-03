#!/usr/bin/env python3
"""Materialize range narration patches into render-ready video files.

Remotion can render dynamic media volume curves, but range replacement must be
verified in the final encoded audio rather than only in the React timeline.
This step creates a temporary MP4 for each video that has narrationSegments:

- the original video stream is copied without re-encoding;
- source audio is muted inside each selected range;
- the narration file is delayed to the selected range start and mixed in;
- the output manifest points Remotion at the patched MP4.

The source project and vlog-plan.json are never modified. Only the generated
manifest is rewritten, and generated MP4 files live under the output folder.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bake narrationSegments into temporary render-source MP4 files."
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


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


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"File not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"Malformed JSON in {path}: {exc}")


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
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
    )
    return bool(result.stdout.strip())


def safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    return (cleaned or fallback)[:96]


def resolve_source(project: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        fail("Timeline video is missing source")
    candidate = Path(value)
    source = candidate if candidate.is_absolute() else project / candidate
    if not source.is_file():
        fail(f"Missing source video: {source}")
    return source.resolve()


def resolve_narration(project: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        fail("Narration segment is missing narration")
    candidate = Path(value)
    narration = candidate if candidate.is_absolute() else project / candidate
    if not narration.is_file():
        fail(f"Missing narration segment audio: {narration}")
    if not has_audio_stream(narration):
        fail(f"Narration segment has no audio stream: {narration}")
    return narration.resolve()


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def build_filter_graph(
    *,
    duration: float,
    base_input_index: int,
    segment_input_indexes: list[int],
    segments: list[dict[str, Any]],
) -> str:
    filters: list[str] = [
        f"[{base_input_index}:a:0]"
        "aresample=48000,"
        "aformat=sample_fmts=fltp:channel_layouts=stereo,"
        "asetpts=PTS-STARTPTS[base0]"
    ]

    base_label = "base0"
    segment_labels: list[str] = []
    for index, (input_index, segment) in enumerate(
        zip(segment_input_indexes, segments, strict=True)
    ):
        start = float(segment["startSeconds"])
        end = float(segment["endSeconds"])
        range_duration = end - start
        next_base = f"base{index + 1}"
        filters.append(
            f"[{base_label}]volume=0:enable='between(t,{number(start)},{number(end)})'"
            f"[{next_base}]"
        )
        base_label = next_base

        delay_ms = max(0, round(start * 1000))
        segment_label = f"segment{index}"
        filters.append(
            f"[{input_index}:a:0]"
            f"atrim=start=0:end={number(range_duration)},"
            "asetpts=PTS-STARTPTS,"
            "aresample=48000,"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[{segment_label}]"
        )
        segment_labels.append(segment_label)

    inputs = "".join(f"[{label}]" for label in [base_label, *segment_labels])
    filters.append(
        f"{inputs}amix=inputs={1 + len(segment_labels)}:"
        "duration=first:dropout_transition=0:normalize=0,"
        f"atrim=start=0:end={number(duration)},"
        "asetpts=PTS-STARTPTS[outa]"
    )
    return ";".join(filters)


def materialize_video(
    *,
    project: Path,
    item: dict[str, Any],
    index: int,
    output_dir: Path,
) -> Path | None:
    raw_segments = item.get("narrationSegments")
    if raw_segments in (None, []):
        return None
    if item.get("type") != "video":
        fail(f"Range narration only supports video: {item.get('id', index)}")
    if not isinstance(raw_segments, list):
        fail(f"narrationSegments must be a list: {item.get('id', index)}")

    source = resolve_source(project, item.get("source"))
    duration = float(item.get("resolvedDuration") or probe_duration(source))
    audio_mode = str(item.get("audioMode", "source"))
    if audio_mode == "narration":
        fail(
            "Whole-asset narration and range narration cannot be materialized together: "
            f"{item.get('id', index)}"
        )

    segments: list[dict[str, Any]] = []
    narration_paths: list[Path] = []
    previous_end = -1.0
    for segment_index, raw in enumerate(raw_segments):
        if not isinstance(raw, dict):
            fail(f"Invalid narration segment {segment_index}")
        try:
            start = float(raw["startSeconds"])
            end = float(raw["endSeconds"])
        except (KeyError, TypeError, ValueError):
            fail(f"Narration segment {segment_index} has invalid range")
        if start < 0 or end <= start or end > duration + 0.05:
            fail(
                f"Narration segment {segment_index} is outside the video: "
                f"{start:.3f}-{end:.3f}s / {duration:.3f}s"
            )
        if start < previous_end:
            fail("Narration segments may not overlap")
        previous_end = end
        segment = dict(raw)
        segment["startSeconds"] = start
        segment["endSeconds"] = end
        segments.append(segment)
        narration_paths.append(resolve_narration(project, segment.get("narration")))

    use_source_audio = audio_mode == "source" and has_audio_stream(source)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]

    if use_source_audio:
        base_input_index = 0
        next_input_index = 1
    else:
        command.extend(
            [
                "-f",
                "lavfi",
                "-t",
                number(duration),
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        base_input_index = 1
        next_input_index = 2

    segment_input_indexes: list[int] = []
    for narration in narration_paths:
        command.extend(["-i", str(narration)])
        segment_input_indexes.append(next_input_index)
        next_input_index += 1

    filter_graph = build_filter_graph(
        duration=duration,
        base_input_index=base_input_index,
        segment_input_indexes=segment_input_indexes,
        segments=segments,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    asset_id = safe_name(str(item.get("id") or f"asset-{index + 1:03d}"), f"asset-{index + 1:03d}")
    output = (output_dir / f"{index:03d}-{asset_id}-patched.mp4").resolve()
    command.extend(
        [
            "-filter_complex",
            filter_graph,
            "-map",
            "0:v:0",
            "-map",
            "[outa]",
            "-map_metadata",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-t",
            number(duration),
            str(output),
        ]
    )
    run_checked(command)

    if not output.is_file() or output.stat().st_size == 0:
        fail(f"Patched render source was not created: {output}")
    if not has_audio_stream(output):
        fail(f"Patched render source has no audio stream: {output}")
    return output


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    manifest_path = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    manifest = load_json(manifest_path)

    if not project.is_dir():
        fail(f"Project folder not found: {project}")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("timeline"), list):
        fail("Manifest must contain a timeline list")

    patched = 0
    for index, raw in enumerate(manifest["timeline"]):
        if not isinstance(raw, dict):
            continue
        output = materialize_video(
            project=project,
            item=raw,
            index=index,
            output_dir=output_dir,
        )
        if output is None:
            raw.pop("renderSourceOriginal", None)
            raw.pop("appliedNarrationSegments", None)
            continue

        original_source = raw.get("source")
        segments = raw.get("narrationSegments", [])
        raw["renderSourceOriginal"] = original_source
        raw["appliedNarrationSegments"] = segments
        raw["source"] = str(output)
        raw["audioMode"] = "source"
        raw["subtitleMode"] = str(raw.get("subtitleMode", "auto"))
        raw.pop("narrationSegments", None)
        raw.pop("narration", None)
        raw.pop("narrationDuration", None)
        patched += 1

    manifest["rangeNarrationMaterialized"] = patched
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Materialized range narration videos: {patched}")
    print(f"Updated manifest: {manifest_path}")


if __name__ == "__main__":
    main()
