#!/usr/bin/env python3
"""Transcribe Japanese speech with Whisper and save full JSON output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import whisper


DEFAULT_INPUT = Path("temp/voice_audio.wav")
DEFAULT_OUTPUT = Path("temp/whisper_result.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Whisper (large-v3 with medium fallback)."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input audio path (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args()


def is_resource_constraint_error(exc: Exception) -> bool:
    message = str(exc).lower()
    markers = [
        "out of memory",
        "memory",
        "cuda",
        "mps",
        "resource exhausted",
        "std::bad_alloc",
        "cublas",
        "killed",
    ]
    return any(marker in message for marker in markers)


def run_transcription(model_name: str, audio_path: Path) -> dict[str, Any]:
    model = whisper.load_model(model_name)
    return model.transcribe(str(audio_path), language="ja", word_timestamps=True)


def count_words(result: dict[str, Any]) -> int:
    total_words = 0
    for segment in result.get("segments", []):
        words = segment.get("words")
        if isinstance(words, list):
            total_words += len(words)
    return total_words


def main() -> None:
    args = parse_args()
    input_audio = args.input
    output_json = args.output

    if not input_audio.is_file():
        print(
            f"ERROR: input audio not found: {input_audio}. "
            "Run ./scripts/extract_audio.sh first or pass --input.",
            file=sys.stderr,
        )
        sys.exit(1)

    selected_model = "large-v3"
    try:
        result = run_transcription("large-v3", input_audio)
    except Exception as exc:
        if is_resource_constraint_error(exc):
            print(
                "WARN: large-v3 failed due to resource/runtime constraints; "
                "retrying with medium.",
                file=sys.stderr,
            )
            selected_model = "medium"
            try:
                result = run_transcription("medium", input_audio)
            except Exception as medium_exc:
                print(
                    "ERROR: medium fallback transcription failed: "
                    f"{medium_exc}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            print(f"ERROR: large-v3 transcription failed: {exc}", file=sys.stderr)
            sys.exit(1)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    with output_json.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    full_text = result.get("text", "")
    char_count = len(full_text)
    word_count = count_words(result)
    segment_count = len(result.get("segments", []))

    print(f"Selected model: {selected_model}")
    print(f"Total character count: {char_count}")
    print(f"Total word count: {word_count}")
    print(f"Number of segments: {segment_count}")
    print(f"Saved transcription JSON: {output_json}")


if __name__ == "__main__":
    main()
