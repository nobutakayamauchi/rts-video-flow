#!/usr/bin/env python3
"""Apply automatic jump cuts only at the start and end of timeline assets.

A boundary is eligible when the selected voice track contains at least 0.1 s of
silence at the beginning or end. The cut keeps a 0.1 s handle on each side, so
two adjacent assets retain at most 0.2 s of intentional transition silence.

The project sources and vlog-plan.json are never modified. Generated render
assets are written under the output directory and the generated manifest plus
subtitle timings are rewritten in place.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SILENCE_MIN_SECONDS = 0.1
BOUNDARY_HANDLE_SECONDS = 0.1
SILENCE_NOISE_DB = -45.0
MIN_RENDER_DURATION_SECONDS = 0.2

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(
    r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)"
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--noise-db", type=float, default=SILENCE_NOISE_DB)
    parser.add_argument("--minimum-silence", type=float, default=SILENCE_MIN_SECONDS)
    parser.add_argument("--handle", type=float, default=BOUNDARY_HANDLE_SECONDS)
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


def resolve_path(project: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    path = candidate if candidate.is_absolute() else project / candidate
    return path.resolve() if path.is_file() else None


def parse_silence_intervals(
    stderr: str, *, duration: float
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    open_start: float | None = None
    for line in stderr.splitlines():
        start_match = SILENCE_START_RE.search(line)
        if start_match:
            open_start = max(0.0, float(start_match.group(1)))
        end_match = SILENCE_END_RE.search(line)
        if end_match:
            end = min(duration, float(end_match.group(1)))
            measured = max(0.0, float(end_match.group(2)))
            start = open_start if open_start is not None else max(0.0, end - measured)
            if end > start:
                intervals.append((start, end))
            open_start = None
    if open_start is not None and open_start < duration:
        intervals.append((open_start, duration))
    return intervals


def detect_silence_intervals(
    path: Path, *, duration: float, noise_db: float, minimum_silence: float
) -> list[tuple[float, float]]:
    result = run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={minimum_silence}",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
    )
    return parse_silence_intervals(result.stderr, duration=duration)


def compute_boundary_trim(
    duration: float,
    intervals: list[tuple[float, float]],
    *,
    handle: float = BOUNDARY_HANDLE_SECONDS,
    minimum_silence: float = SILENCE_MIN_SECONDS,
) -> tuple[float, float]:
    """Return [start, end] while preserving one handle around speech."""
    if duration <= MIN_RENDER_DURATION_SECONDS or not intervals:
        return 0.0, duration

    leading_end: float | None = None
    trailing_start: float | None = None

    first_start, first_end = intervals[0]
    if first_start <= 0.02 and first_end - first_start >= minimum_silence:
        leading_end = first_end

    last_start, last_end = intervals[-1]
    if duration - last_end <= 0.05 and last_end - last_start >= minimum_silence:
        trailing_start = last_start

    # A fully silent asset must not collapse to a tiny or zero-length clip.
    if (
        leading_end is not None
        and trailing_start is not None
        and leading_end >= duration - 0.05
        and trailing_start <= 0.05
    ):
        return 0.0, duration

    start = max(0.0, (leading_end - handle) if leading_end is not None else 0.0)
    end = min(
        duration,
        (trailing_start + handle) if trailing_start is not None else duration,
    )
    if end - start < MIN_RENDER_DURATION_SECONDS:
        return 0.0, duration
    return round(start, 3), round(end, 3)


def number(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def safe_name(value: object, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-.")
    return (cleaned or fallback)[:96]


def trim_audio(source: Path, output: Path, *, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            number(start),
            "-i",
            str(source),
            "-t",
            number(duration),
            "-vn",
            "-af",
            "asetpts=PTS-STARTPTS",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(output),
        ]
    )


def trim_video(source: Path, output: Path, *, start: float, duration: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    source_has_audio = has_audio_stream(source)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        number(start),
        "-i",
        str(source),
        "-t",
        number(duration),
        "-map",
        "0:v:0",
    ]
    if source_has_audio:
        command.extend(["-map", "0:a:0?"])
    command.extend(
        [
            "-vf",
            "setpts=PTS-STARTPTS",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if source_has_audio:
        command.extend(
            [
                "-af",
                "asetpts=PTS-STARTPTS",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-ac",
                "2",
            ]
        )
    command.extend(["-movflags", "+faststart", str(output)])
    run_checked(command)


def voice_track(project: Path, item: dict[str, Any]) -> Path | None:
    mode = str(item.get("audioMode", "source"))
    if mode == "narration":
        return resolve_path(project, item.get("narration"))
    if mode == "source":
        source = resolve_path(project, item.get("source"))
        return source if source is not None and has_audio_stream(source) else None
    return None


def shift_beep_ranges(
    raw: object, *, trim_start: float, new_duration: float
) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    shifted: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("startSeconds", 0.0)) - trim_start
            end = float(entry.get("endSeconds", 0.0)) - trim_start
        except (TypeError, ValueError):
            continue
        start = max(0.0, start)
        end = min(new_duration, end)
        if end <= start:
            continue
        shifted.append(
            {
                **entry,
                "startSeconds": round(start, 3),
                "endSeconds": round(end, 3),
            }
        )
    return shifted


def retime_subtitles(
    subtitles: list[dict[str, Any]],
    timing: dict[str, tuple[float, float, float, float]],
) -> list[dict[str, Any]]:
    """Shift captions using assetId -> old_start, new_start, trim_start, duration."""
    output: list[dict[str, Any]] = []
    for subtitle in subtitles:
        if not isinstance(subtitle, dict):
            continue
        asset_id = str(subtitle.get("assetId", ""))
        values = timing.get(asset_id)
        if values is None:
            output.append(dict(subtitle))
            continue
        old_start, new_start, trim_start, new_duration = values
        try:
            local_start = float(subtitle.get("start", old_start)) - old_start
            local_end = float(subtitle.get("end", old_start)) - old_start
        except (TypeError, ValueError):
            continue
        shifted_start = local_start - trim_start
        shifted_end = local_end - trim_start
        if shifted_end <= 0 or shifted_start >= new_duration:
            continue
        updated = dict(subtitle)
        updated["start"] = round(new_start + max(0.0, shifted_start), 3)
        updated["end"] = round(
            new_start + min(new_duration, shifted_end),
            3,
        )
        if updated["end"] > updated["start"]:
            updated["id"] = len(output)
            output.append(updated)
    return output


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    manifest_path = args.manifest.resolve()
    subtitles_path = args.subtitles.resolve()
    output_dir = args.output_dir.resolve()

    manifest = load_json(manifest_path)
    subtitles = load_json(subtitles_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("timeline"), list):
        fail("Manifest must contain a timeline list")
    if not isinstance(subtitles, list):
        fail("Subtitles must be a list")

    cursor = 0.0
    applied = 0
    skipped_silent = 0
    timing: dict[str, tuple[float, float, float, float]] = {}

    for index, raw in enumerate(manifest["timeline"]):
        if not isinstance(raw, dict):
            continue

        item_id = str(raw.get("id") or f"asset-{index + 1:03d}")
        old_start = float(raw.get("timelineStart", cursor))
        source = resolve_path(project, raw.get("source"))
        if source is None:
            fail(f"Missing timeline source: {raw.get('source')}")

        duration = float(
            raw.get("resolvedDuration")
            or raw.get("durationSeconds")
            or probe_duration(source)
        )
        track = voice_track(project, raw)
        trim_start = 0.0
        trim_end = duration

        if track is not None:
            track_duration = probe_duration(track)
            analysis_duration = min(duration, track_duration)
            intervals = detect_silence_intervals(
                track,
                duration=analysis_duration,
                noise_db=args.noise_db,
                minimum_silence=args.minimum_silence,
            )
            trim_start, trim_end = compute_boundary_trim(
                duration,
                intervals,
                handle=args.handle,
                minimum_silence=args.minimum_silence,
            )
            if intervals and trim_start == 0.0 and trim_end == duration:
                if (
                    intervals[0][0] <= 0.02
                    and intervals[-1][1] >= analysis_duration - 0.05
                    and intervals[0][1] >= analysis_duration - 0.05
                ):
                    skipped_silent += 1

        new_duration = round(trim_end - trim_start, 3)
        changed = trim_start > 0.001 or trim_end < duration - 0.001

        if changed:
            asset_name = safe_name(item_id, f"asset-{index + 1:03d}")
            if raw.get("type") == "video":
                trimmed_video = (
                    output_dir / f"{index:03d}-{asset_name}-boundary.mp4"
                ).resolve()
                trim_video(
                    source,
                    trimmed_video,
                    start=trim_start,
                    duration=new_duration,
                )
                raw["boundaryJumpCutOriginalSource"] = raw.get("source")
                raw["source"] = str(trimmed_video)

            if str(raw.get("audioMode")) == "narration":
                narration = resolve_path(project, raw.get("narration"))
                if narration is None:
                    fail(f"Narration is missing for {item_id}")
                trimmed_audio = (
                    output_dir / f"{index:03d}-{asset_name}-boundary.m4a"
                ).resolve()
                trim_audio(
                    narration,
                    trimmed_audio,
                    start=trim_start,
                    duration=new_duration,
                )
                raw["boundaryJumpCutOriginalNarration"] = raw.get("narration")
                raw["narration"] = str(trimmed_audio)
                raw["narrationDuration"] = new_duration
                raw["narrationRenderedDurationSeconds"] = new_duration
                raw["narrationTargetDurationSeconds"] = new_duration

            raw["boundaryJumpCut"] = {
                "enabled": True,
                "trimStartSeconds": trim_start,
                "trimEndSeconds": round(duration - trim_end, 3),
                "leadingHandleSeconds": args.handle,
                "trailingHandleSeconds": args.handle,
                "minimumSilenceSeconds": args.minimum_silence,
                "noiseThresholdDb": args.noise_db,
            }
            raw["beepRanges"] = shift_beep_ranges(
                raw.get("beepRanges"),
                trim_start=trim_start,
                new_duration=new_duration,
            )
            applied += 1
        else:
            raw["boundaryJumpCut"] = {
                "enabled": True,
                "trimStartSeconds": 0.0,
                "trimEndSeconds": 0.0,
                "leadingHandleSeconds": args.handle,
                "trailingHandleSeconds": args.handle,
                "minimumSilenceSeconds": args.minimum_silence,
                "noiseThresholdDb": args.noise_db,
            }

        raw["timelineStart"] = round(cursor, 3)
        raw["resolvedDuration"] = new_duration
        if raw.get("type") == "image":
            raw["durationSeconds"] = new_duration

        timing[item_id] = (
            old_start,
            cursor,
            trim_start,
            new_duration,
        )
        cursor += new_duration

    updated_subtitles = retime_subtitles(subtitles, timing)
    manifest["totalDurationSeconds"] = round(cursor, 3)
    manifest["boundaryJumpCutsApplied"] = applied
    manifest["boundaryJumpCutPolicy"] = {
        "scope": "asset-boundaries-only",
        "minimumSilenceSeconds": args.minimum_silence,
        "leadingHandleSeconds": args.handle,
        "trailingHandleSeconds": args.handle,
        "maximumTransitionSilenceSeconds": round(args.handle * 2, 3),
        "noiseThresholdDb": args.noise_db,
        "fullySilentAssetsPreserved": True,
        "internalPausesPreserved": True,
        "bgmExcludedFromDetection": True,
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subtitles_path.write_text(
        json.dumps(updated_subtitles, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Boundary jump cuts applied: {applied}")
    print(f"Fully silent assets preserved: {skipped_silent}")
    print(f"Total duration: {cursor:.3f} sec")
    print(f"Updated manifest: {manifest_path}")
    print(f"Updated subtitles: {subtitles_path}")


if __name__ == "__main__":
    main()
