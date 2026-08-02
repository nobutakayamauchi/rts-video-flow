#!/usr/bin/env python3
"""Transcribe Japanese speech with Whisper and save full JSON output."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import whisper


DEFAULT_INPUT = Path("temp/voice_audio.wav")
DEFAULT_OUTPUT = Path("temp/whisper_result.json")
DEFAULT_MODELS = "large-v3,medium"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe audio with Whisper using an ordered model fallback list."
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
    parser.add_argument(
        "--models",
        default=os.environ.get("WHISPER_MODELS", DEFAULT_MODELS),
        help=(
            "Comma-separated models to try in order. "
            "Defaults to WHISPER_MODELS or large-v3,medium. "
            "For a low-memory test render, use small,base."
        ),
    )
    return parser.parse_args()


def run_transcription(model_name: str, audio_path: Path) -> dict[str, Any]:
    model = whisper.load_model(model_name)
    return model.transcribe(
        str(audio_path),
        language="ja",
        word_timestamps=True,
        fp16=False,
    )


def count_words(result: dict[str, Any]) -> int:
    total_words = 0
    for segment in result.get("segments", []):
        words = segment.get("words")
        if isinstance(words, list):
            total_words += len(words)
    return total_words


def parse_models(raw: str) -> list[str]:
    models = [part.strip() for part in raw.split(",") if part.strip()]
    if not models:
        raise ValueError("At least one Whisper model is required")
    return models


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

    try:
        models = parse_models(args.models)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)

    result: dict[str, Any] | None = None
    selected_model = ""
    failures: list[str] = []

    for index, model_name in enumerate(models):
        print(
            f"Whisper attempt {index + 1}/{len(models)}: {model_name}",
            file=sys.stderr,
            flush=True,
        )
        try:
            result = run_transcription(model_name, input_audio)
            selected_model = model_name
            break
        except Exception as exc:  # Retry every normal model/runtime failure.
            detail = f"{type(exc).__name__}: {exc!r}"
            failures.append(f"{model_name}: {detail}")
            print(
                f"WARN: Whisper model {model_name} failed: {detail}",
                file=sys.stderr,
                flush=True,
            )
            traceback.print_exc(file=sys.stderr)

    if result is None:
        print("ERROR: all Whisper transcription attempts failed.", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
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
