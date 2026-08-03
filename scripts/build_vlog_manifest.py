#!/usr/bin/env python3
"""Create a deterministic Vlog manifest from an iPhone project folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_MODES = {"source", "narration", "mute"}
SUBTITLE_MODES = {"auto", "none"}
SEGMENT_MODES = {"replace"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a Vlog asset manifest.")
    parser.add_argument("project", type=Path, help="Project folder containing camera/, screen/, screenshots/.")
    parser.add_argument("--output", type=Path, help="Manifest output path. Defaults to <project>/manifest.json")
    parser.add_argument("--image-seconds", type=float, default=5.0, help="Default duration per screenshot.")
    return parser.parse_args()


def collect(directory: Path, extensions: set[str]) -> list[str]:
    if not directory.exists():
        return []
    return [
        str(path.relative_to(directory.parent))
        for path in sorted(directory.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in extensions
    ]


def default_audio_mode(item: dict[str, Any], asset_type: str) -> str:
    value = item.get("audioMode")
    if isinstance(value, str) and value in AUDIO_MODES:
        return value
    narration = item.get("narration")
    if isinstance(narration, str) and narration.strip():
        return "narration"
    return "source" if asset_type == "video" else "mute"


def default_subtitle_mode(item: dict[str, Any], audio_mode: str) -> str:
    value = item.get("subtitleMode")
    if isinstance(value, str) and value in SUBTITLE_MODES:
        return value
    return "auto" if audio_mode != "mute" else "none"


def ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def normalize_segments(
    project: Path,
    raw_segments: object,
    *,
    asset_id: str,
    index: int,
) -> list[dict[str, Any]]:
    if raw_segments in (None, []):
        return []
    if not isinstance(raw_segments, list):
        raise ValueError(f"timeline[{index}].narrationSegments must be a list")

    segments: list[dict[str, Any]] = []
    for segment_index, raw in enumerate(raw_segments):
        if not isinstance(raw, dict):
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] must be an object"
            )
        narration = raw.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] requires narration"
            )
        if not (project / narration).is_file():
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] narration is missing: {narration}"
            )
        try:
            start = round(float(raw.get("startSeconds")), 3)
            end = round(float(raw.get("endSeconds")), 3)
        except (TypeError, ValueError):
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] requires numeric range"
            ) from None
        if start < 0 or end <= start:
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] has invalid range"
            )
        mode = str(raw.get("mode", "replace"))
        if mode not in SEGMENT_MODES:
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] has invalid mode"
            )
        subtitle_mode = str(raw.get("subtitleMode", "auto"))
        if subtitle_mode not in SUBTITLE_MODES:
            raise ValueError(
                f"timeline[{index}].narrationSegments[{segment_index}] has invalid subtitleMode"
            )
        segments.append(
            {
                **raw,
                "id": str(
                    raw.get("id") or f"{asset_id}-segment-{segment_index + 1:03d}"
                ),
                "startSeconds": start,
                "endSeconds": end,
                "mode": mode,
                "subtitleMode": subtitle_mode,
                "narration": narration.strip(),
            }
        )

    segments.sort(key=lambda value: (value["startSeconds"], value["endSeconds"]))
    seen_ids: set[str] = set()
    previous: dict[str, Any] | None = None
    for segment in segments:
        segment_id = str(segment["id"])
        if segment_id in seen_ids:
            raise ValueError(f"timeline[{index}] duplicates segment id: {segment_id}")
        seen_ids.add(segment_id)
        if previous and ranges_overlap(
            float(previous["startSeconds"]),
            float(previous["endSeconds"]),
            float(segment["startSeconds"]),
            float(segment["endSeconds"]),
        ):
            raise ValueError(f"timeline[{index}] has overlapping narration segments")
        previous = segment
    return segments


def normalize_item(project: Path, raw: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(raw)
    source = item.get("source")
    asset_type = item.get("type")
    if not isinstance(source, str) or asset_type not in {"video", "image"}:
        raise ValueError(f"timeline[{index}] has invalid type/source")
    if not (project / source).is_file():
        raise ValueError(f"timeline[{index}] source is missing: {source}")

    narration = item.get("narration")
    if narration is not None:
        if not isinstance(narration, str) or not narration.strip():
            item.pop("narration", None)
        elif not (project / narration).is_file():
            raise ValueError(f"timeline[{index}] narration is missing: {narration}")

    item["id"] = str(item.get("id") or f"asset-{index + 1:03d}")
    audio_mode = default_audio_mode(item, asset_type)
    if asset_type == "image" and audio_mode == "source":
        audio_mode = "mute"
    item["audioMode"] = audio_mode
    item["subtitleMode"] = default_subtitle_mode(item, audio_mode)

    segments = normalize_segments(
        project,
        item.get("narrationSegments"),
        asset_id=str(item["id"]),
        index=index,
    )
    if asset_type == "image" and segments:
        raise ValueError(f"timeline[{index}] range narration only supports video")
    if audio_mode == "narration" and segments:
        raise ValueError(
            f"timeline[{index}] cannot combine whole narration with range narration"
        )
    if segments:
        item["narrationSegments"] = segments
    else:
        item.pop("narrationSegments", None)

    if asset_type == "image":
        item["durationSeconds"] = max(0.5, float(item.get("durationSeconds", 5.0)))
        item.setdefault("motion", "slow-pan")

    return item


def validate_timeline(project: Path, timeline: object) -> list[dict[str, Any]]:
    if not isinstance(timeline, list) or not timeline:
        raise ValueError("timeline must be a non-empty list")
    validated: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(timeline):
        if not isinstance(raw, dict):
            raise ValueError(f"timeline[{index}] must be an object")
        item = normalize_item(project, raw, index)
        asset_id = str(item["id"])
        if asset_id in seen_ids:
            raise ValueError(f"timeline[{index}] duplicates asset id: {asset_id}")
        seen_ids.add(asset_id)
        validated.append(item)
    return validated


def main() -> None:
    args = parse_args()
    project = args.project.resolve()
    if not project.is_dir():
        print(f"ERROR: project folder not found: {project}", file=sys.stderr)
        raise SystemExit(1)

    output = args.output.resolve() if args.output else project / "manifest.json"
    camera = collect(project / "camera", VIDEO_EXTENSIONS)
    screen = collect(project / "screen", VIDEO_EXTENSIONS)
    screenshots = collect(project / "screenshots", IMAGE_EXTENSIONS)

    plan_path = project / "vlog-plan.json"
    if plan_path.is_file():
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            timeline = validate_timeline(project, plan.get("timeline"))
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR: invalid vlog-plan.json: {exc}", file=sys.stderr)
            raise SystemExit(1)
        policy = plan.get("policy") if isinstance(plan.get("policy"), dict) else {}
        source_mode = "vlog-plan.json"
    else:
        raw_timeline: list[dict[str, Any]] = []
        for asset in camera:
            raw_timeline.append({"type": "video", "source": asset, "role": "camera"})
        for asset in screenshots:
            raw_timeline.append(
                {
                    "type": "image",
                    "source": asset,
                    "role": "screenshot",
                    "durationSeconds": args.image_seconds,
                    "motion": "slow-pan",
                }
            )
        for asset in screen:
            raw_timeline.append({"type": "video", "source": asset, "role": "screen-demo"})
        if not raw_timeline:
            print("ERROR: no supported media found in project", file=sys.stderr)
            raise SystemExit(1)
        timeline = [
            normalize_item(project, raw, index)
            for index, raw in enumerate(raw_timeline)
        ]
        policy = {
            "screenRecording": "short-demo-only",
            "defaultEvidence": "screenshots",
            "privacyReviewRequired": True,
        }
        source_mode = "folder-default"

    payload = {
        "version": 3,
        "project": project.name,
        "sourceMode": source_mode,
        "policy": policy,
        "assets": {
            "camera": camera,
            "screen": screen,
            "screenshots": screenshots,
        },
        "timeline": timeline,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved manifest: {output}")
    print(f"Timeline source: {source_mode}")
    print(f"Timeline items: {len(timeline)}")
    print(f"Camera clips: {len(camera)}")
    print(f"Screen clips: {len(screen)}")
    print(f"Screenshots: {len(screenshots)}")


if __name__ == "__main__":
    main()
