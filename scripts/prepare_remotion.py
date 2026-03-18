#!/usr/bin/env python3
"""Prepare Remotion source files from cut video and subtitles."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_VIDEO = Path("temp/cut_video.mp4")
DEFAULT_SUBTITLES = Path("temp/subtitles.json")
DEFAULT_SRC_DIR = Path("remotion-project/src")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Remotion source files from processed video + subtitles."
    )
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO, help=f"Input video (default: {DEFAULT_VIDEO})")
    parser.add_argument(
        "--subtitles",
        type=Path,
        default=DEFAULT_SUBTITLES,
        help=f"Input subtitle JSON (default: {DEFAULT_SUBTITLES})",
    )
    parser.add_argument(
        "--src-dir",
        type=Path,
        default=DEFAULT_SRC_DIR,
        help=f"Remotion src directory (default: {DEFAULT_SRC_DIR})",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def probe_video(video_path: Path) -> tuple[int, int, float]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        fail("ffprobe not found. Install ffmpeg first.")
    except subprocess.CalledProcessError as exc:
        fail(f"ffprobe failed: {exc.stderr.strip() or exc}")

    try:
        payload = json.loads(result.stdout)
        width = int(payload["streams"][0]["width"])
        height = int(payload["streams"][0]["height"])
        duration = float(payload["format"]["duration"])
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        fail(f"Failed to parse ffprobe output: {exc}")

    return width, height, duration


def validate_subtitles(path: Path) -> None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Subtitle JSON is malformed: {exc}")
    if not isinstance(data, list):
        fail("Subtitle JSON must be a list.")


def build_root_tsx(width: int, height: int, duration_in_frames: int) -> str:
    return f'''import React from "react";
import {{Composition}} from "remotion";
import {{MainVideo}} from "./MainVideo";

export const RemotionRoot: React.FC = () => {{
  return (
    <>
      <Composition
        id="MainVideo"
        component={{MainVideo}}
        fps={{30}}
        width={{{width}}}
        height={{{height}}}
        durationInFrames={{{duration_in_frames}}}
      />
    </>
  );
}};
'''


def build_subtitle_tsx() -> str:
    return '''import React from "react";
import {AbsoluteFill} from "remotion";
import {loadFont} from "@remotion/google-fonts/NotoSansJP";

type SubtitleProps = {
  lines: string[];
  fontSize: number;
};

const {fontFamily} = loadFont();

export const Subtitle: React.FC<SubtitleProps> = ({lines, fontSize}) => {
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        bottom: 40,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          fontFamily,
          fontSize,
          color: "#ffffff",
          textShadow: "0 2px 10px rgba(0,0,0,0.75)",
          textAlign: "center",
          lineHeight: 1.25,
          whiteSpace: "pre-line",
          padding: "0 48px 28px",
        }}
      >
        {lines.join("\\n")}
      </div>
    </AbsoluteFill>
  );
};
'''


def build_main_video_tsx() -> str:
    return '''import React from "react";
import {
  AbsoluteFill,
  Audio,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";
import {Subtitle} from "./Subtitle";

type SubtitleItem = {
  id: number;
  start: number;
  end: number;
  lines: string[];
  fontSize: number;
  color: "main";
};

const subtitles = require("../../public/subtitles.json") as SubtitleItem[];
const FPS = 30;

export const MainVideo: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      <OffthreadVideo src={staticFile("cut_video.mp4")} />
      <Audio src={staticFile("cut_video.mp4")} />
      {subtitles.map((subtitle) => {
        const from = Math.round(subtitle.start * FPS);
        const durationInFrames = Math.max(1, Math.round((subtitle.end - subtitle.start) * FPS));
        const inRange = frame >= from && frame < from + durationInFrames;

        if (!inRange) {
          return null;
        }

        return (
          <Sequence key={subtitle.id} from={from} durationInFrames={durationInFrames}>
            <Subtitle lines={subtitle.lines} fontSize={subtitle.fontSize} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
'''


def write_sources(src_dir: Path, width: int, height: int, duration_in_frames: int) -> list[Path]:
    src_dir.mkdir(parents=True, exist_ok=True)

    root_path = src_dir / "Root.tsx"
    main_video_path = src_dir / "MainVideo.tsx"
    subtitle_path = src_dir / "Subtitle.tsx"

    root_path.write_text(build_root_tsx(width, height, duration_in_frames), encoding="utf-8")
    main_video_path.write_text(build_main_video_tsx(), encoding="utf-8")
    subtitle_path.write_text(build_subtitle_tsx(), encoding="utf-8")

    return [root_path, main_video_path, subtitle_path]


def main() -> None:
    args = parse_args()

    if not args.video.is_file():
        fail(f"Input video not found: {args.video}. Run jumpcut.py first or pass --video.")
    if not args.subtitles.is_file():
        fail(
            f"Input subtitle JSON not found: {args.subtitles}. "
            "Run segment_subtitles.py first or pass --subtitles."
        )

    validate_subtitles(args.subtitles)
    width, height, duration = probe_video(args.video)
    duration_in_frames = round(duration * 30)

    generated_paths = write_sources(args.src_dir, width, height, duration_in_frames)

    print(f"Detected width: {width}")
    print(f"Detected height: {height}")
    print(f"Duration seconds: {duration:.3f}")
    print(f"durationInFrames: {duration_in_frames}")
    print("Generated files:")
    for path in generated_paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
