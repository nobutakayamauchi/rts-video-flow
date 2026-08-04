#!/usr/bin/env python3
"""Audit a rendered Vlog for loud, persistent, narrow-band high-frequency tones.

The audit is intentionally conservative. It does not modify audio. It scans the
final mixed output in short windows, compares narrow high-frequency bands with
the full-band RMS level, and reports only sustained, dominant candidates.

Exit codes:
- 0: audit completed and no candidate was detected (or the file has no audio)
- 1: the audit could not be completed
- 2: one or more high-confidence candidates were detected
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

WINDOW_SECONDS = 0.1
MIN_RUN_SECONDS = 0.3
DEFAULT_MIN_RMS_DB = -24.0
DEFAULT_DOMINANCE_DB = 6.0
DEFAULT_BAND_WIDTH_HZ = 400
DEFAULT_CENTERS_HZ = tuple(range(15000, 19501, 500))

PTS_RE = re.compile(r"pts_time:([-+0-9.eE]+)")
RMS_RE = re.compile(
    r"lavfi\.astats\.Overall\.RMS_level=(-?inf|nan|[-+0-9.eE]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WindowLevel:
    time_seconds: float
    rms_db: float


@dataclass(frozen=True)
class Candidate:
    center_hz: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    peak_band_rms_db: float
    strongest_dominance_db: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--min-rms-db", type=float, default=DEFAULT_MIN_RMS_DB)
    parser.add_argument("--dominance-db", type=float, default=DEFAULT_DOMINANCE_DB)
    parser.add_argument("--min-run-seconds", type=float, default=MIN_RUN_SECONDS)
    return parser.parse_args()


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Command timed out: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc))[-4000:]
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{detail}") from exc


def probe_audio(input_path: Path) -> tuple[bool, int]:
    result = run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "json",
            str(input_path),
        ]
    )
    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams")
    if not isinstance(streams, list) or not streams:
        return False, 0
    try:
        return True, int(streams[0].get("sample_rate") or 0)
    except (TypeError, ValueError):
        return True, 0


def parse_astats(text: str) -> list[WindowLevel]:
    values: list[WindowLevel] = []
    current_time: float | None = None
    fallback_index = 0
    for line in text.splitlines():
        time_match = PTS_RE.search(line)
        if time_match:
            try:
                current_time = float(time_match.group(1))
            except ValueError:
                current_time = None
            continue
        rms_match = RMS_RE.search(line)
        if not rms_match:
            continue
        raw = rms_match.group(1).lower()
        if raw in {"-inf", "inf", "nan"}:
            rms = -math.inf
        else:
            try:
                rms = float(raw)
            except ValueError:
                rms = -math.inf
        time_seconds = (
            current_time
            if current_time is not None
            else fallback_index * WINDOW_SECONDS
        )
        values.append(WindowLevel(round(time_seconds, 6), rms))
        fallback_index += 1
        current_time = None
    return values


def scan_levels(input_path: Path, *, center_hz: int | None = None) -> list[WindowLevel]:
    filters = ["aresample=48000"]
    if center_hz is not None:
        filters.append(
            f"bandpass=f={center_hz}:width_type=h:width={DEFAULT_BAND_WIDTH_HZ}"
        )
    filters.extend(
        [
            f"asetnsamples=n={round(48000 * WINDOW_SECONDS)}:p=1",
            "astats=metadata=1:reset=1",
            "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
        ]
    )
    result = run_checked(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(input_path),
            "-vn",
            "-af",
            ",".join(filters),
            "-f",
            "null",
            "-",
        ]
    )
    parsed = parse_astats((result.stdout or "") + "\n" + (result.stderr or ""))
    if not parsed:
        raise RuntimeError("ffmpeg did not return per-window RMS metadata")
    return parsed


def _finite(value: float) -> bool:
    return math.isfinite(value)


def detect_candidates(
    full_levels: Iterable[WindowLevel],
    band_levels: Iterable[WindowLevel],
    *,
    center_hz: int,
    min_rms_db: float,
    dominance_db: float,
    min_run_seconds: float,
) -> list[Candidate]:
    full = list(full_levels)
    band = list(band_levels)
    count = min(len(full), len(band))
    required_windows = max(1, math.ceil(min_run_seconds / WINDOW_SECONDS))
    candidates: list[Candidate] = []
    run_start: int | None = None

    def qualifying(index: int) -> bool:
        full_rms = full[index].rms_db
        band_rms = band[index].rms_db
        return (
            _finite(full_rms)
            and _finite(band_rms)
            and band_rms >= min_rms_db
            and band_rms >= full_rms - dominance_db
        )

    def finish(end_index: int) -> None:
        nonlocal run_start
        if run_start is None:
            return
        run_length = end_index - run_start
        if run_length >= required_windows:
            indexes = range(run_start, end_index)
            peak = max(band[i].rms_db for i in indexes)
            dominance = max(band[i].rms_db - full[i].rms_db for i in indexes)
            start = band[run_start].time_seconds
            end = band[end_index - 1].time_seconds + WINDOW_SECONDS
            candidates.append(
                Candidate(
                    center_hz=center_hz,
                    start_seconds=round(start, 3),
                    end_seconds=round(end, 3),
                    duration_seconds=round(end - start, 3),
                    peak_band_rms_db=round(peak, 2),
                    strongest_dominance_db=round(dominance, 2),
                )
            )
        run_start = None

    for index in range(count):
        if qualifying(index):
            if run_start is None:
                run_start = index
        else:
            finish(index)
    finish(count)
    return candidates


def merge_overlapping(candidates: list[Candidate]) -> list[Candidate]:
    """Keep the strongest candidate when neighbouring scan bands describe one tone."""
    ordered = sorted(
        candidates,
        key=lambda item: (item.start_seconds, item.end_seconds, item.center_hz),
    )
    merged: list[Candidate] = []
    for candidate in ordered:
        match_index: int | None = None
        for index, existing in enumerate(merged):
            overlaps = (
                candidate.start_seconds < existing.end_seconds
                and existing.start_seconds < candidate.end_seconds
            )
            neighbouring_band = abs(candidate.center_hz - existing.center_hz) <= 500
            if overlaps and neighbouring_band:
                match_index = index
                break
        if match_index is None:
            merged.append(candidate)
            continue
        existing = merged[match_index]
        stronger = (
            candidate
            if candidate.peak_band_rms_db > existing.peak_band_rms_db
            else existing
        )
        merged[match_index] = Candidate(
            center_hz=stronger.center_hz,
            start_seconds=round(
                min(existing.start_seconds, candidate.start_seconds), 3
            ),
            end_seconds=round(max(existing.end_seconds, candidate.end_seconds), 3),
            duration_seconds=round(
                max(existing.end_seconds, candidate.end_seconds)
                - min(existing.start_seconds, candidate.start_seconds),
                3,
            ),
            peak_band_rms_db=max(
                existing.peak_band_rms_db, candidate.peak_band_rms_db
            ),
            strongest_dominance_db=max(
                existing.strongest_dominance_db,
                candidate.strongest_dominance_db,
            ),
        )
    return merged


def write_reports(
    *,
    input_path: Path,
    json_path: Path,
    markdown_path: Path,
    has_audio: bool,
    sample_rate: int,
    scanned_centers: list[int],
    candidates: list[Candidate],
    error: str | None = None,
) -> None:
    status = "ERROR" if error else ("WARNING" if candidates else "PASS")
    payload = {
        "version": 1,
        "status": status,
        "input": str(input_path),
        "hasAudio": has_audio,
        "sampleRate": sample_rate,
        "policy": {
            "minimumFrequencyHz": 15000,
            "windowSeconds": WINDOW_SECONDS,
            "minimumRunSeconds": MIN_RUN_SECONDS,
            "minimumBandRmsDb": DEFAULT_MIN_RMS_DB,
            "maximumDistanceFromFullBandDb": DEFAULT_DOMINANCE_DB,
            "action": "warn-only",
            "automaticNotch": False,
        },
        "scannedCentersHz": scanned_centers,
        "candidates": [asdict(candidate) for candidate in candidates],
        "error": error,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# Audio safety audit",
        "",
        f"Status: **{status}**",
        f"Input: `{input_path}`",
        f"Audio stream: {'yes' if has_audio else 'no'}",
        f"Sample rate: {sample_rate or 'unknown'} Hz",
        "",
        "Policy:",
        "- final mixed output only",
        "- scans narrow bands from 15 kHz upward",
        "- requires a loud, dominant tone for at least 0.3 seconds",
        "- warning and record only; no automatic destructive filtering in v1",
        "",
    ]
    if error:
        lines.extend(["## Audit error", "", error, ""])
    elif not candidates:
        lines.extend(["No high-confidence high-frequency tone was detected.", ""])
    else:
        lines.extend(["## Review required", ""])
        for candidate in candidates:
            lines.append(
                "- "
                f"{candidate.center_hz} Hz around "
                f"{candidate.start_seconds:.3f}–{candidate.end_seconds:.3f}s "
                f"({candidate.duration_seconds:.3f}s), "
                f"peak {candidate.peak_band_rms_db:.2f} dBFS"
            )
        lines.extend(
            [
                "",
                "Listen at a low device volume before publishing. If confirmed as an "
                "unwanted tone, apply a narrow notch to an output copy and re-run this audit.",
                "",
            ]
        )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    input_path = args.input.resolve()
    json_path = args.json.resolve()
    markdown_path = args.markdown.resolve()
    if not input_path.is_file():
        print(f"Audio safety audit input not found: {input_path}", file=sys.stderr)
        return 1

    has_audio = False
    sample_rate = 0
    scanned_centers: list[int] = []
    candidates: list[Candidate] = []
    try:
        has_audio, sample_rate = probe_audio(input_path)
        if not has_audio:
            write_reports(
                input_path=input_path,
                json_path=json_path,
                markdown_path=markdown_path,
                has_audio=False,
                sample_rate=sample_rate,
                scanned_centers=[],
                candidates=[],
            )
            return 0

        nyquist = sample_rate / 2 if sample_rate else 24000
        scanned_centers = [
            center for center in DEFAULT_CENTERS_HZ if center + 300 < nyquist
        ]
        if not scanned_centers:
            write_reports(
                input_path=input_path,
                json_path=json_path,
                markdown_path=markdown_path,
                has_audio=True,
                sample_rate=sample_rate,
                scanned_centers=[],
                candidates=[],
            )
            return 0

        full_levels = scan_levels(input_path)
        raw_candidates: list[Candidate] = []
        for center in scanned_centers:
            band_levels = scan_levels(input_path, center_hz=center)
            raw_candidates.extend(
                detect_candidates(
                    full_levels,
                    band_levels,
                    center_hz=center,
                    min_rms_db=args.min_rms_db,
                    dominance_db=args.dominance_db,
                    min_run_seconds=args.min_run_seconds,
                )
            )
        candidates = merge_overlapping(raw_candidates)
        write_reports(
            input_path=input_path,
            json_path=json_path,
            markdown_path=markdown_path,
            has_audio=True,
            sample_rate=sample_rate,
            scanned_centers=scanned_centers,
            candidates=candidates,
        )
        if candidates:
            print(
                f"Audio safety warning: {len(candidates)} high-frequency candidate(s). "
                f"Review {markdown_path}",
                file=sys.stderr,
            )
            return 2
        print(f"Audio safety audit passed: {markdown_path}")
        return 0
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        write_reports(
            input_path=input_path,
            json_path=json_path,
            markdown_path=markdown_path,
            has_audio=has_audio,
            sample_rate=sample_rate,
            scanned_centers=scanned_centers,
            candidates=candidates,
            error=str(exc),
        )
        print(f"Audio safety audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
