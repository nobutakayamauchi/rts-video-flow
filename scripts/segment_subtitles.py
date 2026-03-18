#!/usr/bin/env python3
"""Segment Whisper Japanese text into subtitle units with deterministic rules."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import budoux


DEFAULT_INPUT = Path("temp/whisper_result.json")
DEFAULT_OUTPUT = Path("temp/subtitles.json")
MAX_UNIT_CHARS = 30
PUNCTUATION = "。！？!?、，,．.：:；;"


@dataclass
class TimedText:
    text: str
    start: float
    end: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Segment Whisper result JSON into subtitle JSON for Remotion."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input Whisper JSON (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output subtitle JSON (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def clean_text(text: str) -> str:
    return "".join(text.replace("\n", "").replace("\r", "").split())


def split_by_punctuation(text: str) -> list[str]:
    if not text:
        return []

    chunks: list[str] = []
    current = ""
    for ch in text:
        current += ch
        if ch in PUNCTUATION:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return [c for c in chunks if c]


def split_by_budoux(parser: Any, text: str, max_chars: int) -> list[str]:
    phrases = [p for p in parser.parse(text) if p]
    if not phrases:
        phrases = [text]

    units: list[str] = []
    current = ""
    for phrase in phrases:
        if len(phrase) > max_chars:
            if current:
                units.append(current)
                current = ""
            for i in range(0, len(phrase), max_chars):
                units.append(phrase[i : i + max_chars])
            continue

        candidate = current + phrase
        if not current or len(candidate) <= max_chars:
            current = candidate
        else:
            units.append(current)
            current = phrase

    if current:
        units.append(current)

    return units


def split_text_to_units(parser: Any, text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []

    if len(text) <= MAX_UNIT_CHARS:
        return [text]

    units: list[str] = []
    for punct_chunk in split_by_punctuation(text):
        if len(punct_chunk) <= MAX_UNIT_CHARS:
            units.append(punct_chunk)
        else:
            units.extend(split_by_budoux(parser, punct_chunk, MAX_UNIT_CHARS))

    validated: list[str] = []
    for unit in units:
        if len(unit) <= MAX_UNIT_CHARS:
            validated.append(unit)
        else:
            validated.extend(split_by_budoux(parser, unit, MAX_UNIT_CHARS))

    return [u for u in validated if u]


def split_two_lines(parser: Any, text: str) -> list[str]:
    phrases = [p for p in parser.parse(text) if p]
    if not phrases:
        phrases = [text]

    best_idx = 1
    total = len(text)
    best_score = float("inf")
    left_len = 0
    for idx in range(1, len(phrases)):
        left_len += len(phrases[idx - 1])
        right_len = total - left_len
        score = abs(left_len - right_len)
        if score < best_score:
            best_score = score
            best_idx = idx

    line1 = "".join(phrases[:best_idx])
    line2 = "".join(phrases[best_idx:])

    if not line1 or not line2:
        half = len(text) // 2
        line1, line2 = text[:half], text[half:]

    if len(line1) > MAX_UNIT_CHARS or len(line2) > MAX_UNIT_CHARS:
        midpoint = len(text) // 2
        line1, line2 = text[:midpoint], text[midpoint:]

    return [line1, line2]


def to_lines(parser: Any, text: str) -> list[str]:
    if len(text) <= 18:
        return [text]
    return split_two_lines(parser, text)


def font_size_for_lines(lines: list[str]) -> int:
    longest = max(len(line) for line in lines) if lines else 0
    if longest <= 8:
        return 72
    if longest <= 12:
        return 64
    if longest <= 18:
        return 56
    if longest <= 24:
        return 48
    return 42


def split_with_timing(texts: list[str], start: float, end: float) -> list[TimedText]:
    duration = max(0.0, end - start)
    total_chars = sum(len(t) for t in texts)
    if duration <= 0 or total_chars <= 0:
        return [TimedText(text=t, start=start, end=end) for t in texts]

    timed: list[TimedText] = []
    cursor = start
    for i, text in enumerate(texts):
        if i == len(texts) - 1:
            seg_end = end
        else:
            ratio = len(text) / total_chars
            seg_end = cursor + duration * ratio
        timed.append(TimedText(text=text, start=cursor, end=seg_end))
        cursor = seg_end
    return timed


def validate_lines(lines: list[str]) -> bool:
    return bool(lines) and len(lines) <= 2 and all(len(line) <= MAX_UNIT_CHARS for line in lines)


def load_segments(input_path: Path) -> list[dict[str, Any]]:
    if not input_path.is_file():
        print(
            f"ERROR: input JSON not found: {input_path}. "
            "Run transcribe.py first or pass --input.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: malformed JSON in {input_path}: {exc}. "
            "Regenerate Whisper output and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    segments = raw.get("segments")
    if not isinstance(segments, list):
        print(
            f"ERROR: '{input_path}' does not contain a valid 'segments' list.",
            file=sys.stderr,
        )
        sys.exit(1)

    return segments


def build_subtitles(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parser = budoux.load_default_japanese_parser()
    subtitles: list[dict[str, Any]] = []

    for segment in segments:
        text = clean_text(str(segment.get("text", "")))
        if not text:
            continue

        try:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start))
        except (TypeError, ValueError):
            continue

        units = split_text_to_units(parser, text)
        timed_units = split_with_timing(units, start, end)

        for unit in timed_units:
            lines = to_lines(parser, unit.text)

            if not validate_lines(lines):
                extra_units = split_text_to_units(parser, unit.text)
                extra_timed = split_with_timing(extra_units, unit.start, unit.end)
                for e in extra_timed:
                    e_lines = to_lines(parser, e.text)
                    if not validate_lines(e_lines):
                        fallback = [e.text[i : i + MAX_UNIT_CHARS] for i in range(0, len(e.text), MAX_UNIT_CHARS)]
                        for f in fallback:
                            f_lines = to_lines(parser, f)
                            subtitles.append(
                                {
                                    "id": len(subtitles),
                                    "start": round(e.start, 3),
                                    "end": round(e.end, 3),
                                    "lines": f_lines[:2],
                                    "fontSize": font_size_for_lines(f_lines[:2]),
                                    "color": "main",
                                }
                            )
                    else:
                        subtitles.append(
                            {
                                "id": len(subtitles),
                                "start": round(e.start, 3),
                                "end": round(e.end, 3),
                                "lines": e_lines,
                                "fontSize": font_size_for_lines(e_lines),
                                "color": "main",
                            }
                        )
                continue

            subtitles.append(
                {
                    "id": len(subtitles),
                    "start": round(unit.start, 3),
                    "end": round(unit.end, 3),
                    "lines": lines,
                    "fontSize": font_size_for_lines(lines),
                    "color": "main",
                }
            )

    repaired: list[dict[str, Any]] = []
    parser = budoux.load_default_japanese_parser()
    for sub in subtitles:
        if all(len(line) <= MAX_UNIT_CHARS for line in sub["lines"]):
            sub["id"] = len(repaired)
            repaired.append(sub)
            continue

        merged = "".join(sub["lines"])
        parts = split_text_to_units(parser, merged)
        timed_parts = split_with_timing(parts, float(sub["start"]), float(sub["end"]))
        for part in timed_parts:
            lines = to_lines(parser, part.text)
            repaired.append(
                {
                    "id": len(repaired),
                    "start": round(part.start, 3),
                    "end": round(part.end, 3),
                    "lines": lines,
                    "fontSize": font_size_for_lines(lines),
                    "color": "main",
                }
            )

    return repaired


def main() -> None:
    args = parse_args()
    segments = load_segments(args.input)
    subtitles = build_subtitles(segments)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(subtitles, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    subtitle_count = len(subtitles)
    avg_duration = (
        sum(max(0.0, float(s["end"]) - float(s["start"])) for s in subtitles) / subtitle_count
        if subtitle_count
        else 0.0
    )
    max_line_len = max((len(line) for s in subtitles for line in s["lines"]), default=0)

    print(f"Subtitle count: {subtitle_count}")
    print(f"Average subtitle duration: {avg_duration:.3f} sec")
    print(f"Maximum line length observed: {max_line_len}")
    print(f"Saved subtitle JSON: {args.output}")


if __name__ == "__main__":
    main()
