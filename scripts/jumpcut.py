#!/usr/bin/env python3
"""Detect speech segments with Silero VAD and remove silent video parts."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

import torch
from silero_vad import get_speech_timestamps, load_silero_vad, read_audio


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def write_concat_list(files: Iterable[Path], list_path: Path) -> None:
    with list_path.open("w", encoding="utf-8") as f:
        for item in files:
            safe_path = str(item.resolve()).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")


def render_segment(input_video: Path, output_file: Path, start: float, end: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(input_video),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_file),
        ]
    )


def concat_videos(inputs: list[Path], output_file: Path, workspace: Path, label: str) -> None:
    list_file = workspace / f"concat_{label}.txt"
    write_concat_list(inputs, list_file)
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_file),
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Silence cutting via Silero VAD + ffmpeg")
    parser.add_argument("--video", default="input/ai_video_edit.mov", help="Input video path")
    parser.add_argument("--wav", default="temp/audio_16k.wav", help="Input WAV path (16kHz mono)")
    parser.add_argument("--output", default="temp/cut_video.mp4", help="Output video path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_video = Path(args.video)
    input_wav = Path(args.wav)
    output_video = Path(args.output)

    if not input_video.is_file():
        raise SystemExit(f"[ERROR] Input video not found: {input_video}")
    if not input_wav.is_file():
        raise SystemExit(
            f"[ERROR] Input wav not found: {input_wav}. Run ./scripts/extract_audio.sh first."
        )
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("[ERROR] ffmpeg/ffprobe are required but not found in PATH.")

    output_video.parent.mkdir(parents=True, exist_ok=True)

    torch.set_num_threads(1)
    model = load_silero_vad()
    wav = read_audio(str(input_wav), sampling_rate=16000)

    speech_timestamps = get_speech_timestamps(
        wav,
        model,
        threshold=0.5,
        min_silence_duration_ms=400,
        speech_pad_ms=150,
        min_speech_duration_ms=250,
        sampling_rate=16000,
    )

    if not speech_timestamps:
        raise SystemExit(
            "[ERROR] No speech segments detected. Check temp/audio_16k.wav quality or adjust VAD settings."
        )

    segments: list[tuple[float, float]] = []
    for ts in speech_timestamps:
        start = ts["start"] / 16000.0
        end = ts["end"] / 16000.0
        if end > start:
            segments.append((start, end))

    if not segments:
        raise SystemExit("[ERROR] VAD produced invalid segments with non-positive durations.")

    mode = "chunk" if len(segments) >= 50 else "direct"

    with tempfile.TemporaryDirectory(prefix="jumpcut_", dir=str(output_video.parent)) as tmp:
        workspace = Path(tmp)
        segment_files: list[Path] = []

        for i, (start, end) in enumerate(segments):
            seg_file = workspace / f"segment_{i:04d}.mp4"
            render_segment(input_video, seg_file, start, end)
            segment_files.append(seg_file)

        if mode == "direct":
            concat_videos(segment_files, output_video, workspace, "direct")
        else:
            chunk_files: list[Path] = []
            chunk_size = 10
            chunk_count = math.ceil(len(segment_files) / chunk_size)
            for ci in range(chunk_count):
                chunk_input = segment_files[ci * chunk_size : (ci + 1) * chunk_size]
                chunk_out = workspace / f"chunk_{ci:03d}.mp4"
                concat_videos(chunk_input, chunk_out, workspace, f"chunk_{ci:03d}")
                chunk_files.append(chunk_out)
            concat_videos(chunk_files, output_video, workspace, "final")

    original_duration = ffprobe_duration(input_video)
    cut_duration = ffprobe_duration(output_video)
    cut_ratio = (cut_duration / original_duration * 100.0) if original_duration > 0 else 0.0

    print(f"[jumpcut] original_duration_sec={original_duration:.3f}")
    print(f"[jumpcut] cut_duration_sec={cut_duration:.3f}")
    print(f"[jumpcut] cut_ratio_percent={cut_ratio:.2f}")
    print(f"[jumpcut] segments_detected={len(segments)}")
    print(f"[jumpcut] mode={mode}")
    print(f"[jumpcut] output={output_video}")


if __name__ == "__main__":
    main()
