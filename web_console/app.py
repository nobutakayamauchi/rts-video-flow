#!/usr/bin/env python3
"""Mobile-first web console for assembling and rendering lightweight Vlogs."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
PROJECTS_DIR = ROOT / "projects"
OUTPUT_DIR = ROOT / "output"
ALLOWED_ROLES = {"opening", "ending", "camera", "screen", "screenshot"}
AUDIO_MODES = {"source", "narration", "mute"}
AUDIO_EXTENSIONS = {".m4a", ".wav", ".ogg", ".webm", ".mp4"}
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024

app = FastAPI(title="RTS Vlog Web Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def safe_project_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid project name")
    return cleaned[:80]


def extension_for(content_type: str | None, filename: str | None = None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {
        ".mp4",
        ".mov",
        ".m4v",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".m4a",
        ".wav",
        ".ogg",
    }:
        return suffix
    return {
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "audio/mp4": ".m4a",
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
    }.get((content_type or "").lower(), ".bin")


def project_dir(name: str) -> Path:
    return PROJECTS_DIR / safe_project_name(name)


def plan_path(project_path: Path) -> Path:
    return project_path / "vlog-plan.json"


def default_plan(name: str) -> dict[str, Any]:
    return {
        "version": 5,
        "project": name,
        "policy": {
            "screenRecording": "short-demo-only",
            "defaultEvidence": "screenshots",
            "privacyReviewRequired": True,
        },
        "timeline": [],
    }


def load_plan(project_path: Path) -> dict[str, Any]:
    path = plan_path(project_path)
    if not path.is_file():
        return default_plan(project_path.name)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid project plan: {exc}") from exc
    if not isinstance(plan, dict) or not isinstance(plan.get("timeline"), list):
        raise HTTPException(status_code=500, detail="Invalid project plan structure")
    return plan


def save_plan(project_path: Path, plan: dict[str, Any]) -> None:
    project_path.mkdir(parents=True, exist_ok=True)
    plan["version"] = max(5, int(plan.get("version", 1)))
    plan_path(project_path).write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def invalidate_output(project_path: Path) -> None:
    shutil.rmtree(OUTPUT_DIR / project_path.name, ignore_errors=True)


def target_folder(project_path: Path, role: str) -> Path:
    if role in {"opening", "ending", "camera"}:
        return project_path / "camera"
    if role == "screen":
        return project_path / "screen"
    return project_path / "screenshots"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


async def stream_upload_to_disk(upload: UploadFile, target: Path) -> int:
    """Write an upload incrementally so large iPhone videos do not fill RAM."""
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Media is too large (maximum 1 GB)",
                    )
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty media")
    return total


def resolve_project_file(project_path: Path, relative_value: object) -> Path | None:
    """Resolve a plan file reference without allowing paths outside the project."""
    if not isinstance(relative_value, str) or not relative_value.strip():
        return None
    root = project_path.resolve()
    target = (project_path / relative_value).resolve()
    if target == root or root not in target.parents:
        raise HTTPException(status_code=400, detail="Unsafe project file path")
    return target


def move_path_to_trash(project_path: Path, target: Path) -> str | None:
    if not target.is_file():
        return None
    trash_dir = project_path / ".trash" / timestamp()
    trash_dir.mkdir(parents=True, exist_ok=True)
    destination = trash_dir / target.name
    counter = 1
    while destination.exists():
        destination = trash_dir / f"{target.stem}-{counter}{target.suffix}"
        counter += 1
    target.replace(destination)
    return str(destination.relative_to(project_path))


def move_item_files_to_trash(project_path: Path, item: dict[str, Any]) -> list[str]:
    """Soft-delete source, whole narration, and range narration files."""
    moved: list[str] = []
    references: list[object] = [item.get("source"), item.get("narration")]
    segments = item.get("narrationSegments")
    if isinstance(segments, list):
        references.extend(
            segment.get("narration")
            for segment in segments
            if isinstance(segment, dict)
        )
    for reference in references:
        target = resolve_project_file(project_path, reference)
        if target is None:
            continue
        destination = move_path_to_trash(project_path, target)
        if destination:
            moved.append(destination)
    return moved


def find_item(plan: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = next(
        (value for value in plan["timeline"] if value.get("id") == item_id),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    return item


def ranges_overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> bool:
    return start_a < end_b and start_b < end_a


def probe_duration(path: Path) -> float:
    try:
        process = subprocess.run(
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
            timeout=60,
        )
        return max(0.1, float(process.stdout.strip()))
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Could not read media duration: {exc}"
        ) from exc


def narration_segments(item: dict[str, Any]) -> list[dict[str, Any]]:
    value = item.get("narrationSegments")
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
        raise HTTPException(status_code=500, detail="Invalid narration segment data")
    return value


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/project/{project_name}")
def project_status(project_name: str) -> dict[str, Any]:
    project_path = project_dir(project_name)
    plan = load_plan(project_path)
    return {
        "project": project_path.name,
        "timeline": plan["timeline"],
        "outputExists": (OUTPUT_DIR / project_path.name / "vlog.mp4").is_file(),
    }


@app.post("/api/material")
async def save_material(
    project: str = Form(...),
    role: str = Form(...),
    description: str = Form(""),
    media: UploadFile = File(...),
) -> dict[str, Any]:
    project_path = project_dir(project)
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Unsupported role")

    plan = load_plan(project_path)
    folder = target_folder(project_path, role)
    extension = extension_for(media.content_type, media.filename)
    order = len(plan["timeline"]) + 1
    target = folder / f"{order:02d}-{role}-{timestamp()}{extension}"
    size_bytes = await stream_upload_to_disk(media, target)

    asset_type = "image" if role == "screenshot" else "video"
    audio_mode = "mute" if asset_type == "image" else "source"
    item: dict[str, Any] = {
        "id": f"item-{timestamp()}-{order}",
        "type": asset_type,
        "source": str(target.relative_to(project_path)),
        "role": role,
        "sizeBytes": size_bytes,
        "audioMode": audio_mode,
        "subtitleMode": "none" if audio_mode == "mute" else "auto",
    }
    if description.strip():
        item["explanation"] = description.strip()
    if role == "screenshot":
        item.update({"durationSeconds": 5.0, "motion": "slow-pan"})

    plan["timeline"].append(item)
    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {"status": "saved", "item": item, "timeline": plan["timeline"]}


@app.delete("/api/material")
def delete_material(
    project: str = Form(...), item_id: str = Form(...)
) -> dict[str, Any]:
    """Remove one timeline item and soft-delete its files into .trash."""
    project_path = project_dir(project)
    plan = load_plan(project_path)
    index = next(
        (i for i, item in enumerate(plan["timeline"]) if item.get("id") == item_id),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Timeline item not found")

    item = plan["timeline"].pop(index)
    moved = move_item_files_to_trash(project_path, item)
    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {
        "status": "deleted",
        "item": item,
        "movedToTrash": moved,
        "timeline": plan["timeline"],
    }


@app.post("/api/narration")
async def save_narration(
    project: str = Form(...),
    item_id: str = Form(...),
    transcript_hint: str = Form(""),
    media: UploadFile = File(...),
) -> dict[str, Any]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    item = find_item(plan, item_id)
    if narration_segments(item):
        raise HTTPException(
            status_code=400,
            detail="Remove range narrations before selecting whole-asset narration",
        )

    extension = extension_for(media.content_type, media.filename)
    if extension not in AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported narration audio format")

    folder = project_path / "narration"
    target = folder / f"{item_id}-{timestamp()}{extension}"
    size_bytes = await stream_upload_to_disk(media, target)

    old_narration = resolve_project_file(project_path, item.get("narration"))
    moved_old = None
    if old_narration is not None and old_narration != target:
        moved_old = move_path_to_trash(project_path, old_narration)

    item["narration"] = str(target.relative_to(project_path))
    item["narrationSizeBytes"] = size_bytes
    item["audioMode"] = "narration"
    item["subtitleMode"] = "auto"
    if transcript_hint.strip():
        item["transcriptHint"] = transcript_hint.strip()
    else:
        item.pop("transcriptHint", None)

    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {
        "status": "saved",
        "item": item,
        "replacedNarration": moved_old,
    }


@app.post("/api/narration-segment")
async def save_narration_segment(
    project: str = Form(...),
    item_id: str = Form(...),
    start_seconds: float = Form(...),
    end_seconds: float = Form(...),
    transcript_hint: str = Form(""),
    media: UploadFile = File(...),
) -> dict[str, Any]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    item = find_item(plan, item_id)
    if item.get("type") != "video":
        raise HTTPException(
            status_code=400, detail="Range narration is only supported for video assets"
        )
    if item.get("audioMode") == "narration":
        raise HTTPException(
            status_code=400,
            detail="Switch away from whole-asset narration before adding a range narration",
        )

    start = round(float(start_seconds), 3)
    end = round(float(end_seconds), 3)
    if start < 0 or end <= start:
        raise HTTPException(status_code=400, detail="Invalid narration range")
    source = resolve_project_file(project_path, item.get("source"))
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Source video not found")
    duration = probe_duration(source)
    if end > duration + 0.05:
        raise HTTPException(
            status_code=400,
            detail=f"Range ends after the source video ({duration:.3f}s)",
        )

    segments = narration_segments(item)
    for existing in segments:
        if ranges_overlap(
            start,
            end,
            float(existing.get("startSeconds", 0.0)),
            float(existing.get("endSeconds", 0.0)),
        ):
            raise HTTPException(
                status_code=400,
                detail="The selected range overlaps an existing narration range",
            )

    extension = extension_for(media.content_type, media.filename)
    if extension not in AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported narration audio format")
    folder = project_path / "narration" / "segments"
    segment_id = f"segment-{timestamp()}"
    target = folder / f"{item_id}-{segment_id}{extension}"
    size_bytes = await stream_upload_to_disk(media, target)

    segment: dict[str, Any] = {
        "id": segment_id,
        "startSeconds": start,
        "endSeconds": end,
        "mode": "replace",
        "subtitleMode": "auto",
        "narration": str(target.relative_to(project_path)),
        "narrationSizeBytes": size_bytes,
    }
    if transcript_hint.strip():
        segment["transcriptHint"] = transcript_hint.strip()
    segments.append(segment)
    segments.sort(key=lambda value: float(value.get("startSeconds", 0.0)))
    item["narrationSegments"] = segments

    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {"status": "saved", "segment": segment, "item": item, "timeline": plan["timeline"]}


@app.delete("/api/narration-segment")
def delete_narration_segment(
    project: str = Form(...),
    item_id: str = Form(...),
    segment_id: str = Form(...),
) -> dict[str, Any]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    item = find_item(plan, item_id)
    segments = narration_segments(item)
    index = next(
        (i for i, segment in enumerate(segments) if segment.get("id") == segment_id),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Narration segment not found")
    segment = segments.pop(index)
    target = resolve_project_file(project_path, segment.get("narration"))
    moved = move_path_to_trash(project_path, target) if target is not None else None
    if segments:
        item["narrationSegments"] = segments
    else:
        item.pop("narrationSegments", None)
    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {
        "status": "deleted",
        "segment": segment,
        "movedToTrash": moved,
        "item": item,
        "timeline": plan["timeline"],
    }


@app.post("/api/audio-mode")
def set_audio_mode(
    project: str = Form(...),
    item_id: str = Form(...),
    audio_mode: str = Form(...),
) -> dict[str, Any]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    item = find_item(plan, item_id)

    if audio_mode not in AUDIO_MODES:
        raise HTTPException(status_code=400, detail="Unsupported audio mode")
    if item.get("type") == "image" and audio_mode == "source":
        raise HTTPException(status_code=400, detail="Images cannot use source audio")
    if audio_mode == "narration" and not item.get("narration"):
        raise HTTPException(
            status_code=400,
            detail="Narration audio must be uploaded before narration mode can be selected",
        )
    if audio_mode == "narration" and narration_segments(item):
        raise HTTPException(
            status_code=400,
            detail="Remove range narrations before selecting whole-asset narration",
        )

    item["audioMode"] = audio_mode
    item["subtitleMode"] = "none" if audio_mode == "mute" else "auto"
    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {"status": "saved", "item": item, "timeline": plan["timeline"]}


@app.post("/api/reorder")
def reorder(
    project: str = Form(...), ordered_ids: str = Form(...)
) -> dict[str, Any]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    ids = [value for value in ordered_ids.split(",") if value]
    by_id = {str(item.get("id")): item for item in plan["timeline"]}
    if set(ids) != set(by_id):
        raise HTTPException(
            status_code=400, detail="Order does not match timeline items"
        )
    plan["timeline"] = [by_id[item_id] for item_id in ids]
    save_plan(project_path, plan)
    invalidate_output(project_path)
    return {"status": "saved", "timeline": plan["timeline"]}


@app.post("/api/compile")
def compile_vlog(
    project: str = Form(...), render: bool = Form(True)
) -> dict[str, str]:
    project_path = project_dir(project)
    plan = load_plan(project_path)
    roles = [item.get("role") for item in plan["timeline"]]
    if "opening" not in roles:
        raise HTTPException(status_code=400, detail="Opening video is required")
    if "ending" not in roles:
        raise HTTPException(status_code=400, detail="Ending video is required")

    try:
        process = subprocess.run(
            ["bash", str(ROOT / "scripts" / "process_vlog.sh"), str(project_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        render_log = ""
        if render:
            rendered = subprocess.run(
                [
                    "bash",
                    str(ROOT / "scripts" / "render_vlog.sh"),
                    project_path.name,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                timeout=3600,
            )
            render_log = rendered.stdout[-4000:]
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Compilation timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=(exc.stderr or exc.stdout or str(exc))[-4000:],
        ) from exc

    output = OUTPUT_DIR / project_path.name / "vlog.mp4"
    return {
        "status": "rendered" if render else "prepared",
        "output": str(output.relative_to(ROOT)) if output.is_file() else "",
        "processLog": process.stdout[-4000:],
        "renderLog": render_log,
    }


@app.get("/api/download/{project_name}")
def download(project_name: str) -> FileResponse:
    name = safe_project_name(project_name)
    target = OUTPUT_DIR / name / "vlog.mp4"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Rendered video not found")
    return FileResponse(target, media_type="video/mp4", filename=f"{name}.mp4")
