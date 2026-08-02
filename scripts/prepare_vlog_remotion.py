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
        duration = float(
            item.get(
                "resolvedDuration",
                item.get(
                    "durationSeconds",
                    probe(source) if asset_type == "video" else 5.0,
                ),
            )
        )

        narration_name: str | None = None
        narration_value = item.get("narration")
        if isinstance(narration_value, str) and narration_value:
            narration_path = project / narration_value
            if not narration_path.is_file():
                fail(f"Missing narration: {narration_path}")
            narration_name = f"narration-{index:03d}{narration_path.suffix.lower() or '.webm'}"
            shutil.copy2(narration_path, public / narration_name)

        output.append(
            {
                "id": index,
                "type": asset_type,
                "role": str(item.get("role", "asset")),
                "src": name,
                "start": round(cursor, 3),
                "duration": round(duration, 3),
                "motion": str(item.get("motion", "none")),
                "narration": narration_name,
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

type T = {{id:number;type:"video"|"image";role:string;src:string;start:number;duration:number;motion:string;narration:string|null;explanation:string}};
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
              <OffthreadVideo src={{staticFile(`vlog/assets/${{item.src}}`)}} style={{{{width:"100%",height:"100%",objectFit:"contain"}}}} />
            ) : (
              <Still item={{item}} />
            )}}
            {{item.narration && <Audio src={{staticFile(`vlog/assets/${{item.narration}}`)}} />}}
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
