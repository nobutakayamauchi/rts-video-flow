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
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

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
        "version": 3,
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
    plan_path(project_path).write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def target_folder(project_path: Path, role: str) -> Path:
    if role in {"opening", "ending", "camera"}:
        return project_path / "camera"
    if role == "screen":
        return project_path / "screen"
    return project_path / "screenshots"


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def resolve_project_file(project_path: Path, relative_value: object) -> Path | None:
    """Resolve a plan file reference without allowing paths outside the project."""
    if not isinstance(relative_value, str) or not relative_value.strip():
        return None
    root = project_path.resolve()
    target = (project_path / relative_value).resolve()
    if target == root or root not in target.parents:
        raise HTTPException(status_code=400, detail="Unsafe project file path")
    return target


def move_item_files_to_trash(project_path: Path, item: dict[str, Any]) -> list[str]:
    """Soft-delete source and narration files so mistakes remain recoverable."""
    trash_dir = project_path / ".trash" / timestamp()
    moved: list[str] = []
    for key in ("source", "narration"):
        target = resolve_project_file(project_path, item.get(key))
        if target is None or not target.is_file():
            continue
        trash_dir.mkdir(parents=True, exist_ok=True)
        destination = trash_dir / target.name
        counter = 1
        while destination.exists():
            destination = trash_dir / f"{target.stem}-{counter}{target.suffix}"
            counter += 1
        target.replace(destination)
        moved.append(str(destination.relative_to(project_path)))
    return moved


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
    data = await media.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty media")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Media is too large")

    plan = load_plan(project_path)
    folder = target_folder(project_path, role)
    folder.mkdir(parents=True, exist_ok=True)
    extension = extension_for(media.content_type, media.filename)
    order = len(plan["timeline"]) + 1
    target = folder / f"{order:02d}-{role}-{timestamp()}{extension}"
    target.write_bytes(data)

    item: dict[str, Any] = {
        "id": f"item-{timestamp()}-{order}",
        "type": "image" if role == "screenshot" else "video",
        "source": str(target.relative_to(project_path)),
        "role": role,
    }
    if description.strip():
        item["explanation"] = description.strip()
    if role == "screenshot":
        item.update({"durationSeconds": 5.0, "motion": "slow-pan"})

    plan["timeline"].append(item)
    save_plan(project_path, plan)
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

    # A previously rendered video is now stale and must not be mistaken for the new plan.
    shutil.rmtree(OUTPUT_DIR / project_path.name, ignore_errors=True)
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
    item = next(
        (value for value in plan["timeline"] if value.get("id") == item_id), None
    )
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    if item.get("type") != "image":
        raise HTTPException(
            status_code=400,
            detail="Narration recording is only supported for screenshots",
        )

    data = await media.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty narration")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Narration is too large")

    folder = project_path / "narration"
    folder.mkdir(parents=True, exist_ok=True)
    extension = extension_for(media.content_type, media.filename)
    target = folder / f"{item_id}-{timestamp()}{extension}"
    target.write_bytes(data)
    item["narration"] = str(target.relative_to(project_path))
    if transcript_hint.strip():
        item["transcriptHint"] = transcript_hint.strip()
    save_plan(project_path, plan)
    return {"status": "saved", "item": item}


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
