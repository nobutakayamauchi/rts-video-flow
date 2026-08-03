#!/usr/bin/env python3
"""Fail a smoke render unless the baked narration tone is present in the final MP4."""

from __future__ import annotations

import argparse
import array
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    print(f"[error] {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--expected-frequency", type=float, default=880.0)
    parser.add_argument("--tolerance", type=float, default=0.18)
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"Manifest not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"Malformed manifest: {exc}")


def find_smoke_range(manifest: Any) -> tuple[float, float]:
    if not isinstance(manifest, dict):
        fail("Manifest root must be an object")
    timeline = manifest.get("timeline")
    if not isinstance(timeline, list):
        fail("Manifest timeline is missing")

    for item in timeline:
        if not isinstance(item, dict):
            continue
        timeline_start = float(item.get("timelineStart", item.get("start", 0.0)))
        segments = item.get("appliedNarrationSegments") or item.get("narrationSegments")
        if not isinstance(segments, list):
            continue
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            if str(segment.get("id", "")).startswith("segment-smoke"):
                start = timeline_start + float(segment["startSeconds"])
                end = timeline_start + float(segment["endSeconds"])
                if end <= start:
                    fail("Smoke segment has an invalid range")
                return start, end
    fail("Smoke narration segment was not found in the processed manifest")


def decode_samples(video: Path, *, start: float, duration: float) -> array.array[int]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.6f}",
        "-t",
        f"{duration:.6f}",
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError as exc:
        fail(f"ffmpeg is not available: {exc}")
    except subprocess.CalledProcessError as exc:
        fail((exc.stderr or b"ffmpeg failed").decode("utf-8", errors="replace"))

    samples = array.array("h")
    samples.frombytes(result.stdout)
    if not samples:
        fail("No audio samples were decoded from the smoke range")
    return samples


def estimate_frequency(samples: array.array[int], duration: float) -> float:
    crossings = 0
    previous = samples[0]
    for current in samples[1:]:
        if (previous < 0 <= current) or (previous >= 0 > current):
            crossings += 1
        previous = current
    return crossings / (2.0 * duration)


def main() -> None:
    args = parse_args()
    manifest = load_json(args.manifest.resolve())
    video = args.video.resolve()
    if not video.is_file() or video.stat().st_size == 0:
        fail(f"Rendered video is missing: {video}")

    start, end = find_smoke_range(manifest)
    range_duration = end - start
    sample_duration = min(0.75, max(0.25, range_duration * 0.45))
    sample_start = start + max(0.05, (range_duration - sample_duration) / 2.0)
    samples = decode_samples(video, start=sample_start, duration=sample_duration)
    measured = estimate_frequency(samples, sample_duration)
    lower = args.expected_frequency * (1.0 - args.tolerance)
    upper = args.expected_frequency * (1.0 + args.tolerance)
    print(
        "[smoke] "
        f"range={start:.3f}-{end:.3f}s "
        f"expected={args.expected_frequency:.1f}Hz measured={measured:.1f}Hz"
    )
    if not lower <= measured <= upper:
        fail(
            "Range narration was not present in the final encoded audio: "
            f"expected {lower:.1f}-{upper:.1f}Hz, measured {measured:.1f}Hz"
        )
    print("[ok] Final MP4 contains the narration patch inside the selected range")


if __name__ == "__main__":
    main()
