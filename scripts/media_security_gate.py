#!/usr/bin/env python3
"""Fail-closed security inspection for media before cost estimation or upload."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg"}
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_DURATION_SECONDS = 30 * 60
MAX_WIDTH = 7680
MAX_HEIGHT = 4320
MAX_STREAMS = 4
MAX_FRAME_RATE = 120.0
PROBE_TIMEOUT_SECONDS = 30
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class InspectedFile:
    path: str
    sha256: str
    size_bytes: int
    suffix: str
    duration_seconds: float
    width: int | None
    height: int | None
    stream_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_ffprobe(path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
            env={"PATH": os.environ.get("PATH", "")},
        )
    except FileNotFoundError as exc:
        raise ValueError("ffprobe is required") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("ffprobe timeout") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "ffprobe failed")[-1000:]
        raise ValueError(detail) from exc
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid ffprobe output") from exc


def parse_rate(value: object) -> float:
    text = str(value or "0/1")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        denominator_value = float(denominator)
        return float(numerator) / denominator_value if denominator_value else 0.0
    return float(text)


def inspect_file(path: Path) -> InspectedFile:
    if not path.is_file() or path.is_symlink():
        raise ValueError("input must be a regular non-symlink file")
    if not SAFE_NAME_RE.fullmatch(path.name):
        raise ValueError("unsafe file name; rename to an internal ASCII identifier")
    suffix = path.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("file type is not allowlisted")
    size = path.stat().st_size
    if not 0 < size <= MAX_FILE_BYTES:
        raise ValueError("file size exceeds security limit")

    probe = run_ffprobe(path)
    streams = probe.get("streams") or []
    if not 1 <= len(streams) <= MAX_STREAMS:
        raise ValueError("stream count outside security limit")
    if any(stream.get("codec_type") not in {"video", "audio"} for stream in streams):
        raise ValueError("attachment, data, subtitle, or unknown streams are not accepted")

    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if len(video_streams) != 1:
        raise ValueError("exactly one video/image stream is required")
    video = video_streams[0]
    width = int(video.get("width") or 0) or None
    height = int(video.get("height") or 0) or None
    if not width or not height or width > MAX_WIDTH or height > MAX_HEIGHT:
        raise ValueError("resolution outside security limit")
    frame_rate = parse_rate(video.get("avg_frame_rate"))
    if frame_rate < 0 or frame_rate > MAX_FRAME_RATE:
        raise ValueError("frame rate outside security limit")

    duration = float((probe.get("format") or {}).get("duration") or 0.0)
    if suffix not in {".png", ".jpg", ".jpeg"} and not 0 < duration <= MAX_DURATION_SECONDS:
        raise ValueError("duration outside security limit")

    return InspectedFile(
        path=str(path),
        sha256=sha256_file(path),
        size_bytes=size,
        suffix=suffix,
        duration_seconds=round(duration, 3),
        width=width,
        height=height,
        stream_count=len(streams),
    )


def create_security_pass(paths: list[Path]) -> dict[str, object]:
    inspected = [inspect_file(path) for path in paths]
    now = int(time.time())
    payload: dict[str, object] = {
        "status": "PASS",
        "policy": "rts-media-security-gate-v1",
        "inspected_at": now,
        "files": [asdict(item) for item in inspected],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload["security_fingerprint"] = hashlib.sha256(canonical).hexdigest()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect media and issue a hash-bound SECURITY_PASS.")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = create_security_pass(args.inputs)
    except ValueError as exc:
        print(json.dumps({"status": "REJECT", "reason": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
