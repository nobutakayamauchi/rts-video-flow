#!/usr/bin/env python3
"""Extended mobile Vlog console.

Adds post-recording narration for both videos and screenshots, media duration
probing, and a lightweight script suggestion endpoint while reusing the
existing project/material/compile API.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse

from web_console.app import app as base_app, project_dir, load_plan, save_plan, extension_for, timestamp, MAX_UPLOAD_BYTES

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="RTS Vlog Web Console v2")


@app.get("/")
def index_v2() -> FileResponse:
    return FileResponse(STATIC_DIR / "index-v2.html")


def media_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        return max(0.0, float(result.stdout.strip()))
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=f"Could not inspect media duration: {exc}") from exc


def find_item(project_name: str, item_id: str) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    project = project_dir(project_name)
    plan = load_plan(project)
    item = next((x for x in plan["timeline"] if str(x.get("id")) == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    return project, plan, item


@app.get("/api/media-info/{project_name}/{item_id}")
def get_media_info(project_name: str, item_id: str) -> dict[str, Any]:
    project, _, item = find_item(project_name, item_id)
    source = project / str(item.get("source", ""))
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Source media not found")
    duration = media_duration(source) if item.get("type") == "video" else float(item.get("durationSeconds", 5.0))
    return {
        "itemId": item_id,
        "role": item.get("role"),
        "type": item.get("type"),
        "durationSeconds": round(duration, 3),
        "recommendedNarrationSeconds": round(max(3.0, duration - 1.0), 1),
        "description": item.get("description", ""),
        "script": item.get("script", ""),
        "hasNarration": bool(item.get("narration")),
    }


@app.post("/api/script-suggestion")
def script_suggestion(
    project: str = Form(...),
    item_id: str = Form(...),
    purpose: str = Form(""),
) -> dict[str, str]:
    project_path, plan, item = find_item(project, item_id)
    source = project_path / str(item.get("source", ""))
    duration = media_duration(source) if item.get("type") == "video" and source.is_file() else float(item.get("durationSeconds", 5.0))
    role = str(item.get("role", "素材"))
    description = str(item.get("description", "")).strip()
    purpose = purpose.strip()

    subject = description or purpose or "この場面で行っている操作"
    if item.get("type") == "video":
        script = f"ここでは、{subject}を実際の操作画面で示しています。画面の流れを見ながら、どこを確認し、何を進めているのかを簡単に説明します。"
    else:
        script = f"この画像は、{subject}を示しています。重要なのは、画面に見えている結果だけでなく、ここまでの判断と作業の流れを残している点です。"
    if duration <= 8:
        script = f"ここでは、{subject}を示しています。"

    item["script"] = script
    item["recommendedNarrationSeconds"] = round(max(3.0, duration - 1.0), 1)
    save_plan(project_path, plan)
    return {"script": script, "recommendedSeconds": str(item["recommendedNarrationSeconds"]), "role": role}


@app.post("/api/post-narration")
async def save_post_narration(
    project: str = Form(...),
    item_id: str = Form(...),
    script: str = Form(""),
    replace_original_audio: bool = Form(False),
    media: UploadFile = File(...),
) -> dict[str, Any]:
    project_path, plan, item = find_item(project, item_id)
    data = await media.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty narration")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Narration is too large")

    folder = project_path / "narration"
    folder.mkdir(parents=True, exist_ok=True)
    ext = extension_for(media.content_type, media.filename)
    target = folder / f"{item_id}-post-{timestamp()}{ext}"
    target.write_bytes(data)

    item["narration"] = str(target.relative_to(project_path))
    item["narrationMode"] = "replace" if replace_original_audio else "overlay"
    if script.strip():
        item["script"] = script.strip()
        item["transcriptHint"] = script.strip()
    item["narrationDurationSeconds"] = round(media_duration(target), 3)
    if item.get("type") == "image":
        item["durationSeconds"] = item["narrationDurationSeconds"]
    save_plan(project_path, plan)
    return {"status": "saved", "item": item}


# Existing API routes are appended after the v2 routes, so v2 overrides win.
app.include_router(base_app.router)
