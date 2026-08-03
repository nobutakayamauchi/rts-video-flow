#!/usr/bin/env python3
"""Prepare a manifest-driven Remotion project for the lightweight Vlog flow."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_FPS = 30
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--subtitles", type=Path, required=True)
    parser.add_argument("--remotion-dir", type=Path, default=Path("remotion-project"))
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)
    return parser.parse_args()


def probe(path: Path) -> float:
    try:
        result = subprocess.run(
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
            check=True,
            capture_output=True,
            text=True,
        )
        return max(0.1, float(result.stdout.strip()))
    except Exception as exc:
        fail(f"Could not read duration for {path}: {exc}")


def load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"Could not read {path}: {exc}")


def safe(index: int, path: Path) -> str:
    return f"{index:03d}-{path.stem[:48]}{path.suffix.lower() or '.bin'}"


def copy_narration(project: Path, public: Path, value: str, name: str) -> str:
    narration_path = project / value
    if not narration_path.is_file():
        fail(f"Missing narration: {narration_path}")
    suffix = narration_path.suffix.lower() or ".webm"
    output_name = f"{name}{suffix}"
    shutil.copy2(narration_path, public / output_name)
    return output_name


def build(project: Path, manifest: dict[str, Any], public: Path) -> tuple[list[dict[str, Any]], float]:
    raw = manifest.get("timeline")
    if not isinstance(raw, list) or not raw:
        fail("Manifest timeline is empty")

    public.mkdir(parents=True, exist_ok=True)
    output: list[dict[str, Any]] = []
    cursor = 0.0

    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        source_value = item.get("source")
        asset_type = item.get("type")
        if not isinstance(source_value, str) or asset_type not in {"video", "image"}:
            continue

        source = project / source_value
        if not source.is_file():
            fail(f"Missing asset: {source}")

        name = safe(index, source)
        shutil.copy2(source, public / name)
        resolved_duration = item.get("resolvedDuration")
        if resolved_duration is not None:
            duration = float(resolved_duration)
        elif item.get("durationSeconds") is not None:
            duration = float(item["durationSeconds"])
        else:
            duration = probe(source) if asset_type == "video" else 5.0

        narration_name: str | None = None
        narration_value = item.get("narration")
        if isinstance(narration_value, str) and narration_value:
            narration_name = copy_narration(
                project,
                public,
                narration_value,
                f"narration-{index:03d}",
            )

        audio_mode = str(
            item.get(
                "audioMode",
                "narration" if narration_name else ("source" if asset_type == "video" else "mute"),
            )
        )
        if audio_mode not in {"source", "narration", "mute"}:
            fail(f"Invalid audio mode for timeline item {index}: {audio_mode}")
        if asset_type == "image" and audio_mode == "source":
            audio_mode = "mute"
        if audio_mode == "narration" and narration_name is None:
            fail(f"Narration mode is missing narration audio for timeline item {index}")

        raw_segments = item.get("narrationSegments", [])
        if not isinstance(raw_segments, list):
            fail(f"Invalid narrationSegments for timeline item {index}")
        segments: list[dict[str, Any]] = []
        for segment_index, raw_segment in enumerate(raw_segments):
            if not isinstance(raw_segment, dict):
                fail(f"Invalid narration segment {segment_index} for timeline item {index}")
            narration = raw_segment.get("narration")
            if not isinstance(narration, str) or not narration:
                fail(f"Missing narration path for segment {segment_index}")
            start = float(raw_segment.get("startSeconds", 0.0))
            end = float(raw_segment.get("endSeconds", 0.0))
            if start < 0 or end <= start or end > duration + 0.05:
                fail(f"Invalid narration segment range for timeline item {index}")
            segment_name = copy_narration(
                project,
                public,
                narration,
                f"segment-{index:03d}-{segment_index:03d}",
            )
            segments.append(
                {
                    "id": str(
                        raw_segment.get("id")
                        or f"{item.get('id', index)}-segment-{segment_index + 1:03d}"
                    ),
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "duration": round(end - start, 3),
                    "narration": segment_name,
                    "mode": str(raw_segment.get("mode", "replace")),
                }
            )

        output.append(
            {
                "id": str(item.get("id") or index),
                "type": asset_type,
                "role": str(item.get("role", "asset")),
                "src": name,
                "start": round(cursor, 3),
                "duration": round(duration, 3),
                "motion": str(item.get("motion", "none")),
                "narration": narration_name,
                "audioMode": audio_mode,
                "narrationSegments": segments,
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )
        cursor += duration

    if not output:
        fail("No valid assets")
    return output, cursor


def root_tsx(width: int, height: int, duration_frames: int, fps: int) -> str:
    return f'''import React from "react";
import {{Composition}} from "remotion";
import {{VlogVideo}} from "./VlogVideo";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="VlogVideo"
    component={{VlogVideo}}
    fps={{{fps}}}
    width={{{width}}}
    height={{{height}}}
    durationInFrames={{{duration_frames}}}
  />
);
'''


def vlog_tsx(fps: int) -> str:
    return f'''import React from "react";
import {{AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame}} from "remotion";
import timeline from "../public/vlog/timeline.json";
import subtitles from "../public/vlog/subtitles.json";

type N = {{id:string;start:number;end:number;duration:number;narration:string;mode:"replace"}};
type T = {{id:string;type:"video"|"image";role:string;src:string;start:number;duration:number;motion:string;narration:string|null;audioMode:"source"|"narration"|"mute";narrationSegments:N[];explanation:string}};
type S = {{id:number;start:number;end:number;lines:string[];fontSize:number}};

const FPS = {fps};
const media = timeline as T[];
const captions = subtitles as S[];

const Still: React.FC<{{item:T}}> = ({{item}}) => {{
  const frame = useCurrentFrame();
  const duration = Math.max(1, Math.round(item.duration * FPS));
  const scale = item.motion === "slow-pan"
    ? interpolate(frame, [0, duration], [1, 1.06], {{extrapolateRight: "clamp"}})
    : 1;

  return (
    <AbsoluteFill style={{{{backgroundColor:"#05070a",overflow:"hidden",display:"flex",flexDirection:"row"}}}}>
      <div style={{{{width:item.explanation?"72%":"100%",height:"100%",display:"flex",alignItems:"center",justifyContent:"center"}}}}>
        <Img src={{staticFile(`vlog/assets/${{item.src}}`)}} style={{{{width:"100%",height:"100%",objectFit:"contain",transform:`scale(${{scale}})`}}}} />
      </div>
      {{item.explanation && (
        <div style={{{{width:"28%",padding:42,boxSizing:"border-box",background:"#111923",color:"white",display:"flex",alignItems:"center",fontSize:34,fontWeight:700,lineHeight:1.5}}}}>
          {{item.explanation}}
        </div>
      )}}
    </AbsoluteFill>
  );
}};

const sourceVolume = (item:T, localFrame:number):number => {{
  if (item.audioMode !== "source") return 0;
  const second = localFrame / FPS;
  const replaced = item.narrationSegments.some((segment) =>
    second >= segment.start && second < segment.end
  );
  return replaced ? 0 : 1;
}};

export const VlogVideo: React.FC = () => {{
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{{{backgroundColor:"black"}}}}>
      {{media.map((item) => {{
        const from = Math.round(item.start * FPS);
        const duration = Math.max(1, Math.round(item.duration * FPS));
        return (
          <Sequence key={{item.id}} from={{from}} durationInFrames={{duration}}>
            {{item.type === "video" ? (
              <OffthreadVideo
                src={{staticFile(`vlog/assets/${{item.src}}`)}}
                muted={{item.audioMode === "narration" || item.audioMode === "mute"}}
                volume={{(localFrame) => sourceVolume(item, localFrame)}}
                style={{{{width:"100%",height:"100%",objectFit:"contain"}}}}
              />
            ) : (
              <Still item={{item}} />
            )}}
            {{item.audioMode === "narration" && item.narration && (
              <Audio src={{staticFile(`vlog/assets/${{item.narration}}`)}} />
            )}}
            {{item.narrationSegments.map((segment) => (
              <Sequence
                key={{segment.id}}
                from={{Math.round(segment.start * FPS)}}
                durationInFrames={{Math.max(1, Math.round(segment.duration * FPS))}}
              >
                <Audio src={{staticFile(`vlog/assets/${{segment.narration}}`)}} />
              </Sequence>
            ))}}
          </Sequence>
        );
      }})}}

      {{captions.map((caption) => {{
        const from = Math.round(caption.start * FPS);
        const duration = Math.max(1, Math.round((caption.end - caption.start) * FPS));
        if (frame < from || frame >= from + duration) return null;
        return (
          <Sequence key={{caption.id}} from={{from}} durationInFrames={{duration}}>
            <AbsoluteFill style={{{{justifyContent:"flex-end",alignItems:"center",paddingBottom:54}}}}>
              <div style={{{{maxWidth:"88%",padding:"12px 22px",borderRadius:14,backgroundColor:"rgba(0,0,0,.72)",color:"white",fontSize:Math.min(caption.fontSize,56),fontWeight:800,lineHeight:1.25,textAlign:"center",whiteSpace:"pre-line",textShadow:"0 2px 8px rgba(0,0,0,.9)"}}}}>
                {{caption.lines.join("\\n")}}
              </div>
            </AbsoluteFill>
          </Sequence>
        );
      }})}}
    </AbsoluteFill>
  );
}};
'''


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0 or args.fps <= 0:
        fail("width, height and fps must be positive")

    project = args.project.resolve()
    manifest = load(args.manifest.resolve())
    subtitles = load(args.subtitles.resolve())
    remotion_dir = args.remotion_dir.resolve()

    if not isinstance(manifest, dict) or not isinstance(subtitles, list):
        fail("Invalid manifest or subtitles")

    public = remotion_dir / "public" / "vlog"
    assets = public / "assets"
    if assets.exists():
        shutil.rmtree(assets)

    timeline, total = build(project, manifest, assets)
    public.mkdir(parents=True, exist_ok=True)
    (public / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (public / "subtitles.json").write_text(
        json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    src = remotion_dir / "src"
    src.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(total * args.fps))
    (src / "Root.tsx").write_text(
        root_tsx(args.width, args.height, frames, args.fps), encoding="utf-8"
    )
    (src / "VlogVideo.tsx").write_text(vlog_tsx(args.fps), encoding="utf-8")
    (src / "index.ts").write_text(
        'import {registerRoot} from "remotion";\nimport {RemotionRoot} from "./Root";\nregisterRoot(RemotionRoot);\n',
        encoding="utf-8",
    )

    print(f"Prepared {len(timeline)} timeline items")
    print(f"Total duration: {total:.3f} sec")
    print(f"Video: {args.width}x{args.height} @ {args.fps} fps")
    print(f"Frames: {frames}")


if __name__ == "__main__":
    main()
