#!/usr/bin/env python3
"""Convert Remotion subtitle JSON into a standard SRT subtitle file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert subtitle JSON to SRT.")
    parser.add_argument("--input", type=Path, default=Path("temp/subtitles.json"))
    parser.add_argument("--output", type=Path, default=Path("output/subtitles.srt"))
    return parser.parse_args()


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def load_items(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        print(f"ERROR: subtitle JSON not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: malformed subtitle JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(payload, list):
        print("ERROR: subtitle JSON must contain a list.", file=sys.stderr)
        raise SystemExit(1)
    return payload


def main() -> None:
    args = parse_args()
    items = load_items(args.input)
    blocks: list[str] = []

    for index, item in enumerate(items, start=1):
        try:
            start = float(item["start"])
            end = float(item["end"])
            lines = item["lines"]
        except (KeyError, TypeError, ValueError):
            continue
        if not isinstance(lines, list) or not lines:
            continue
        text = "\n".join(str(line).strip() for line in lines if str(line).strip())
        if not text:
            continue
        blocks.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{text}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    print(f"Saved SRT: {args.output}")
    print(f"Subtitle blocks: {len(blocks)}")


if __name__ == "__main__":
    main()
