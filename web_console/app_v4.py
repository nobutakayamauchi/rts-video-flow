#!/usr/bin/env python3
"""Symlink-aware entry point for the Vlog composition console.

Oracle keeps ``projects`` and ``output`` as symlinks to persistent production
storage. This layer keeps the v3 implementation intact while fixing storage path
identity, providing a correctly rooted new-project wizard, allowing safe Unicode
project names, and adding duration-aware post narration.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from web_console import app as base
from web_console import app_v3 as legacy
from web_console.app import ROOT, STATIC_DIR


def safe_project_name(value: str) -> str:
    """Keep Japanese and other Unicode names while rejecting path separators."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    cleaned = re.sub(r"[^\w.\-]+", "-", normalized, flags=re.UNICODE).strip("-.")
    if not cleaned:
        raise HTTPException(status_code=400, detail="プロジェクト名を入力してください")
    return cleaned[:80]


def relative_to_root(path: Path) -> str:
    """Return a stable logical path across symlinked storage roots."""
    resolved = path.resolve()
    candidates = (
        ((ROOT / "projects").resolve(), Path("projects")),
        ((ROOT / "output").resolve(), Path("output")),
        (ROOT.resolve(), Path()),
    )
    for physical_root, logical_prefix in candidates:
        if legacy.path_is_within(resolved, physical_root):
            relative = resolved.relative_to(physical_root)
            return str(logical_prefix / relative) if logical_prefix.parts else str(relative)
    raise HTTPException(status_code=400, detail="Path is outside the Vlog storage roots")


def project_fingerprint(
    project_path: Path, plan: dict[str, Any] | None = None
) -> str:
    """Hash plan and source metadata using the resolved shared project root."""
    plan = plan or legacy.load_plan(project_path)
    digest = hashlib.sha256()
    digest.update(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    resolved_project = project_path.resolve()
    for path in sorted(
        legacy.referenced_project_files(project_path, plan), key=lambda value: str(value)
    ):
        resolved = path.resolve()
        stat = resolved.stat()
        digest.update(str(resolved.relative_to(resolved_project)).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return "sha256:" + digest.hexdigest()


def map_project_reference(
    value: object, project_path: Path, restored_paths: dict[str, str]
) -> object:
    """Map restored files back to project-relative references safely."""
    if not isinstance(value, str):
        return value
    original_root_path = relative_to_root(project_path / value)
    restored_root_path = restored_paths.get(original_root_path)
    if not restored_root_path:
        return value
    restored_absolute = ROOT / restored_root_path
    if legacy.path_is_within(restored_absolute, project_path):
        return str(restored_absolute.resolve().relative_to(project_path.resolve()))
    return value


# Patch the shared helpers used by both the base and v3 route functions.
base.safe_project_name = safe_project_name
legacy.safe_project_name = safe_project_name
legacy.relative_to_root = relative_to_root
legacy.project_fingerprint = project_fingerprint
legacy.map_project_reference = map_project_reference

app = legacy.app


@app.middleware("http")
async def redirect_static_wizard(request: Request, call_next):
    """Open the old static wizard URL at a root where relative API paths work."""
    if request.method == "GET" and request.url.path == "/static/index.html":
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(url=f"../new{query}", status_code=307)
    return await call_next(request)


@app.get("/new", include_in_schema=False)
def new_project_wizard() -> FileResponse:
    return FileResponse(STATIC_DIR / "new-vlog.html")


@app.post("/api/project")
def create_project(project: str = Form(...)) -> dict[str, Any]:
    """Create one empty Vlog project without overwriting existing work."""
    safe_name = safe_project_name(project)
    project_path = base.project_dir(safe_name)
    plan_file = project_path / "vlog-plan.json"
    if plan_file.exists() or (project_path.exists() and any(project_path.iterdir())):
        raise HTTPException(status_code=409, detail="同じ名前のプロジェクトが既にあります")

    plan = base.default_plan(safe_name)
    base.save_plan(project_path, plan)
    return {
        "status": "created",
        "project": safe_name,
        "timeline": plan["timeline"],
        "nextUrl": f"/?project={safe_name}",
        "materialUrl": f"/new?project={safe_name}",
    }


def find_timeline_item(
    project_name: str, item_id: str
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    project_path = base.project_dir(project_name)
    plan = base.load_plan(project_path)
    item = next(
        (entry for entry in plan["timeline"] if str(entry.get("id")) == item_id),
        None,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="素材が見つかりません")
    return project_path, plan, item


def source_duration(project_path: Path, item: dict[str, Any]) -> float:
    if item.get("type") == "image":
        return max(0.5, float(item.get("durationSeconds", 5.0)))
    source = base.resolve_project_file(project_path, item.get("source"))
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="元動画が見つかりません")
    return round(base.probe_duration(source), 3)


def narration_fit(raw_duration: float, target_duration: float) -> str:
    delta = raw_duration - target_duration
    if delta > 0.05:
        return "trim-tail"
    if delta < -0.05:
        return "pad-silence"
    return "exact"


def render_narration_audio(source: Path, target: Path, duration: float) -> None:
    """Trim or silence-pad narration to one exact visual duration."""
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-af",
                "apad",
                "-t",
                f"{duration:.3f}",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(target),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="ffmpegが見つかりません") from exc
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=504, detail="音声整形がタイムアウトしました") from exc
    except subprocess.CalledProcessError as exc:
        target.unlink(missing_ok=True)
        detail = (exc.stderr or exc.stdout or str(exc))[-2000:]
        raise HTTPException(status_code=500, detail=f"音声整形に失敗しました: {detail}") from exc


@app.get("/api/timed-narration/{project_name}/{item_id}")
def timed_narration_info(project_name: str, item_id: str) -> dict[str, Any]:
    project_path, _, item = find_timeline_item(project_name, item_id)
    target_duration = source_duration(project_path, item)
    raw_duration = item.get("narrationDurationSeconds")
    try:
        raw_duration_value = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        raw_duration_value = None
    return {
        "project": project_path.name,
        "itemId": item_id,
        "role": item.get("role"),
        "type": item.get("type"),
        "source": item.get("source"),
        "targetDurationSeconds": round(target_duration, 3),
        "rawNarrationDurationSeconds": raw_duration_value,
        "narrationFit": item.get("narrationFit"),
        "hasNarration": bool(item.get("narration")),
        "audioMode": item.get("audioMode"),
        "sourceAudioWillBeMuted": item.get("audioMode") == "narration",
        "sourceUrl": f"/api/source/{project_path.name}/{item_id}",
        "narrationUrl": (
            f"/api/timed-narration-file/{project_path.name}/{item_id}"
            if item.get("narration")
            else None
        ),
    }


@app.get("/api/timed-narration-file/{project_name}/{item_id}")
def timed_narration_file(project_name: str, item_id: str) -> FileResponse:
    project_path, _, item = find_timeline_item(project_name, item_id)
    value = item.get("narrationOriginal") or item.get("narration")
    target = base.resolve_project_file(project_path, value)
    if target is None or not target.is_file():
        raise HTTPException(status_code=404, detail="後入れ音声が見つかりません")
    return FileResponse(target)


@app.post("/api/timed-narration")
async def save_timed_narration(
    project: str = Form(...),
    item_id: str = Form(...),
    target_duration_seconds: float | None = Form(None),
    transcript_hint: str = Form(""),
    media: UploadFile = File(...),
) -> dict[str, Any]:
    project_path, plan, item = find_timeline_item(project, item_id)
    item_type = str(item.get("type"))
    visual_duration = source_duration(project_path, item)
    if item_type == "image" and target_duration_seconds is not None:
        visual_duration = round(float(target_duration_seconds), 3)
    if visual_duration < 0.5 or visual_duration > 3600:
        raise HTTPException(status_code=400, detail="表示時間は0.5〜3600秒で指定してください")

    extension = base.extension_for(media.content_type, media.filename)
    if extension not in base.AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="対応していない音声形式です")

    folder = project_path / "narration" / item_id
    raw_path = folder / f"raw-{base.timestamp()}{extension}"
    size_bytes = await base.stream_upload_to_disk(media, raw_path)
    raw_duration = round(base.probe_duration(raw_path), 3)
    rendered_path = folder / f"render-{base.timestamp()}.m4a"
    try:
        render_narration_audio(raw_path, rendered_path, visual_duration)
    except Exception:
        raw_path.unlink(missing_ok=True)
        raise

    for old_value in (item.get("narration"), item.get("narrationOriginal")):
        old_path = base.resolve_project_file(project_path, old_value)
        if old_path is not None and old_path not in {raw_path, rendered_path}:
            base.move_path_to_trash(project_path, old_path)

    fit = narration_fit(raw_duration, visual_duration)
    item["narration"] = str(rendered_path.relative_to(project_path))
    item["narrationOriginal"] = str(raw_path.relative_to(project_path))
    item["narrationSizeBytes"] = size_bytes
    item["narrationDurationSeconds"] = raw_duration
    item["narrationRenderedDurationSeconds"] = visual_duration
    item["narrationTargetDurationSeconds"] = visual_duration
    item["narrationDeltaSeconds"] = round(raw_duration - visual_duration, 3)
    item["narrationFit"] = fit
    item["audioMode"] = "narration"
    item["subtitleMode"] = "auto"
    item["sourceAudioMuted"] = True
    if item_type == "image":
        item["durationSeconds"] = visual_duration
    else:
        item["sourceDurationSeconds"] = visual_duration
    if transcript_hint.strip():
        item["transcriptHint"] = transcript_hint.strip()
    else:
        item.pop("transcriptHint", None)

    base.save_plan(project_path, plan)
    legacy.mark_output_state(project_path, "STALE", reason="timed narration saved")
    return {
        "status": "saved",
        "item": item,
        "targetDurationSeconds": visual_duration,
        "rawNarrationDurationSeconds": raw_duration,
        "deltaSeconds": round(raw_duration - visual_duration, 3),
        "fit": fit,
        "sourceAudioMuted": True,
    }
