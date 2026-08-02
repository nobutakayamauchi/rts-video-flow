#!/usr/bin/env python3
"""Mobile-first web console for capturing Vlog opening/ending clips."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
INBOX_DIR = ROOT / "inbox"
ALLOWED_ROLES = {"opening", "ending", "camera"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024

app = FastAPI(title="RTS Vlog Web Console")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def safe_project_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Invalid project name")
    return cleaned[:80]


def extension_for(content_type: str | None) -> str:
    content_type = (content_type or "").lower()
    if "mp4" in content_type:
        return ".mp4"
    if "quicktime" in content_type:
        return ".mov"
    return ".webm"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/capture")
async def save_capture(
    project: str = Form(...),
    role: str = Form(...),
    media: UploadFile = File(...),
) -> dict[str, str]:
    project_name = safe_project_name(project)
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Unsupported role")

    data = await media.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty recording")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Recording is too large")

    target_dir = INBOX_DIR / project_name
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    extension = extension_for(media.content_type)
    target = target_dir / f"{role}-{timestamp}{extension}"
    target.write_bytes(data)

    return {
        "status": "saved",
        "project": project_name,
        "role": role,
        "path": str(target.relative_to(ROOT)),
    }
