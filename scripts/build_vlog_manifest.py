#!/usr/bin/env python3
"""Create a deterministic Vlog manifest from an iPhone project folder."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


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


def validate_timeline(project: Path, timeline: object) -> list[dict[str, object]]:
    if not isinstance(timeline, list) or not timeline:
        raise ValueError("timeline must be a non-empty list")
    validated: list[dict[str, object]] = []
    for index, item in enumerate(timeline):
        if not isinstance(item, dict):
            raise ValueError(f"timeline[{index}] must be an object")
        source = item.get("source")
        asset_type = item.get("type")
        if not isinstance(source, str) or asset_type not in {"video", "image"}:
            raise ValueError(f"timeline[{index}] has invalid type/source")
        if not (project / source).is_file():
            raise ValueError(f"timeline[{index}] source is missing: {source}")
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
        timeline: list[dict[str, object]] = []
        for asset in camera:
            timeline.append({"type": "video", "source": asset, "role": "camera"})
        for asset in screenshots:
            timeline.append(
                {
                    "type": "image",
                    "source": asset,
                    "role": "screenshot",
                    "durationSeconds": args.image_seconds,
                    "motion": "slow-pan",
                }
            )
        for asset in screen:
            timeline.append({"type": "video", "source": asset, "role": "screen-demo"})
        policy = {
            "screenRecording": "short-demo-only",
            "defaultEvidence": "screenshots",
            "privacyReviewRequired": True,
        }
        source_mode = "folder-default"

    payload = {
        "version": 1,
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
