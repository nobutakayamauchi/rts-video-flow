#!/usr/bin/env python3
"""Composition, output-management, and recoverable-trash layer for the Vlog console.

This layer keeps the existing recording and rendering implementation intact while
adding:

- an opening/body/ending composition overview;
- explicit preview/final render controls;
- generated-output inventory and recoverable deletion;
- project-scoped trash records, undo, restore, and explicit purge;
- conflict-safe restore without silent overwrite.

It does not publish or upload video.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web_console.app import (
    OUTPUT_DIR,
    ROOT,
    STATIC_DIR,
    load_plan,
    project_dir,
    resolve_project_file,
    safe_project_name,
    save_plan,
)
from web_console.app_v2 import app as base_app

app = FastAPI(title="RTS Vlog Composition Console v3")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static-v3")

TRASH_SCHEMA_VERSION = 1
TRASH_FOLDER = ".trash-v2"
OUTPUT_STATE_FILE = ".output-state.json"
ALLOWED_RESTORE_POLICIES = {"rename", "keep"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def compact_timestamp() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%S%fZ")


def path_is_within(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


def require_project_path(project_name: str) -> Path:
    path = project_dir(project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(project_name: str) -> Path:
    return OUTPUT_DIR / safe_project_name(project_name)


def trash_root(project_path: Path) -> Path:
    return project_path / TRASH_FOLDER


def trash_records_dir(project_path: Path) -> Path:
    return trash_root(project_path) / "records"


def trash_items_dir(project_path: Path) -> Path:
    return trash_root(project_path) / "items"


def output_state_path(project_path: Path) -> Path:
    return project_path / OUTPUT_STATE_FILE


def load_output_state(project_path: Path) -> dict[str, Any]:
    path = output_state_path(project_path)
    if not path.is_file():
        return {"schemaVersion": 1, "outputs": {}, "state": "MISSING"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schemaVersion": 1, "outputs": {}, "state": "FAILED"}
    if not isinstance(value, dict):
        return {"schemaVersion": 1, "outputs": {}, "state": "FAILED"}
    value.setdefault("schemaVersion", 1)
    value.setdefault("outputs", {})
    return value


def save_output_state(project_path: Path, value: dict[str, Any]) -> None:
    value["schemaVersion"] = 1
    output_state_path(project_path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def mark_output_state(
    project_path: Path,
    state: str,
    *,
    reason: str,
    trash_id: str | None = None,
) -> None:
    payload = load_output_state(project_path)
    payload["state"] = state
    payload["updatedAt"] = iso_now()
    payload["reason"] = reason
    if trash_id:
        payload["trashId"] = trash_id
    save_output_state(project_path, payload)


def referenced_project_files(project_path: Path, plan: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for item in plan.get("timeline", []):
        if not isinstance(item, dict):
            continue
        references: list[object] = [item.get("source"), item.get("narration")]
        segments = item.get("narrationSegments")
        if isinstance(segments, list):
            references.extend(
                segment.get("narration")
                for segment in segments
                if isinstance(segment, dict)
            )
        for reference in references:
            try:
                target = resolve_project_file(project_path, reference)
            except HTTPException:
                continue
            if target is not None and target.is_file():
                paths.append(target)
    return paths


def project_fingerprint(project_path: Path, plan: dict[str, Any] | None = None) -> str:
    plan = plan or load_plan(project_path)
    digest = hashlib.sha256()
    digest.update(json.dumps(plan, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    for path in sorted(referenced_project_files(project_path, plan), key=lambda p: str(p)):
        stat = path.stat()
        digest.update(str(path.relative_to(project_path)).encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return "sha256:" + digest.hexdigest()


def relative_to_root(path: Path) -> str:
    resolved = path.resolve()
    if not path_is_within(resolved, ROOT):
        raise HTTPException(status_code=400, detail="Path is outside the Vlog root")
    return str(resolved.relative_to(ROOT.resolve()))


def file_summary(path: Path) -> dict[str, Any]:
    return {
        "path": relative_to_root(path),
        "name": path.name,
        "sizeBytes": path.stat().st_size,
        "modifiedAt": datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
    }


def iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: str(p))


def remove_empty_parents(path: Path, stop: Path) -> None:
    current = path.parent
    stop = stop.resolve()
    while path_is_within(current, stop) and current.resolve() != stop:
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def allowed_delete_path(path: Path, project_path: Path) -> bool:
    return path_is_within(path, project_path) or path_is_within(
        path, output_dir(project_path.name)
    )


def new_trash_id() -> str:
    return f"trash-{compact_timestamp()}"


def record_path(project_path: Path, trash_id: str) -> Path:
    return trash_records_dir(project_path) / f"{trash_id}.json"


def write_trash_record(project_path: Path, record: dict[str, Any]) -> None:
    trash_records_dir(project_path).mkdir(parents=True, exist_ok=True)
    record_path(project_path, str(record["trashId"])).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_trash_record(project_path: Path, trash_id: str) -> dict[str, Any]:
    path = record_path(project_path, trash_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Trash record not found")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid trash record: {exc}") from exc
    if not isinstance(record, dict):
        raise HTTPException(status_code=500, detail="Invalid trash record")
    return record


def active_trash_records(project_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    directory = trash_records_dir(project_path)
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(record, dict) and record.get("status") == "TRASHED":
            records.append(record)
    return records


def create_trash_group(
    *,
    project_path: Path,
    kind: str,
    label: str,
    paths: Iterable[Path],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        path = raw.resolve()
        if path in seen or not path.is_file():
            continue
        if not allowed_delete_path(path, project_path):
            raise HTTPException(status_code=400, detail=f"Unsafe delete path: {path}")
        seen.add(path)
        unique.append(path)

    trash_id = new_trash_id()
    item_root = trash_items_dir(project_path) / trash_id
    moved: list[dict[str, Any]] = []
    total = 0

    try:
        for source in unique:
            original = relative_to_root(source)
            destination = item_root / original
            destination.parent.mkdir(parents=True, exist_ok=True)
            size = source.stat().st_size
            shutil.move(str(source), str(destination))
            moved.append(
                {
                    "originalPath": original,
                    "trashPath": str(destination.relative_to(project_path)),
                    "sizeBytes": size,
                }
            )
            total += size
            stop = project_path if path_is_within(source, project_path) else output_dir(project_path.name)
            remove_empty_parents(source, stop)
    except Exception:
        for item in reversed(moved):
            source = project_path / str(item["trashPath"])
            destination = ROOT / str(item["originalPath"])
            if source.is_file() and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
        shutil.rmtree(item_root, ignore_errors=True)
        raise

    record = {
        "schemaVersion": TRASH_SCHEMA_VERSION,
        "trashId": trash_id,
        "project": project_path.name,
        "kind": kind,
        "groupLabel": label,
        "deletedAt": iso_now(),
        "retentionUntil": (utc_now() + timedelta(days=30)).isoformat(),
        "status": "TRASHED",
        "restorable": True,
        "sizeBytes": total,
        "items": moved,
        "metadata": metadata or {},
    }
    write_trash_record(project_path, record)
    return record


def restored_name(path: Path) -> Path:
    marker = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.stem}-restored-{marker}{path.suffix}")


def map_project_reference(
    value: object, project_path: Path, restored_paths: dict[str, str]
) -> object:
    if not isinstance(value, str):
        return value
    original_root_path = str((project_path / value).resolve().relative_to(ROOT.resolve()))
    restored_root_path = restored_paths.get(original_root_path)
    if not restored_root_path:
        return value
    restored_absolute = ROOT / restored_root_path
    if path_is_within(restored_absolute, project_path):
        return str(restored_absolute.relative_to(project_path))
    return value


def restore_metadata(
    project_path: Path,
    record: dict[str, Any],
    restored_paths: dict[str, str],
) -> None:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        return
    kind = record.get("kind")

    if kind == "source-material":
        raw_item = metadata.get("timelineItem")
        if not isinstance(raw_item, dict):
            return
        item = json.loads(json.dumps(raw_item, ensure_ascii=False))
        item["source"] = map_project_reference(item.get("source"), project_path, restored_paths)
        item["narration"] = map_project_reference(
            item.get("narration"), project_path, restored_paths
        )
        segments = item.get("narrationSegments")
        if isinstance(segments, list):
            for segment in segments:
                if isinstance(segment, dict):
                    segment["narration"] = map_project_reference(
                        segment.get("narration"), project_path, restored_paths
                    )
        plan = load_plan(project_path)
        item_id = item.get("id")
        if not any(existing.get("id") == item_id for existing in plan["timeline"]):
            index = max(0, min(int(metadata.get("timelineIndex", len(plan["timeline"]))), len(plan["timeline"])))
            plan["timeline"].insert(index, item)
            save_plan(project_path, plan)

    if kind == "narration-segment":
        item_id = str(metadata.get("itemId", ""))
        raw_segment = metadata.get("segment")
        if not item_id or not isinstance(raw_segment, dict):
            return
        segment = json.loads(json.dumps(raw_segment, ensure_ascii=False))
        segment["narration"] = map_project_reference(
            segment.get("narration"), project_path, restored_paths
        )
        plan = load_plan(project_path)
        item = next(
            (entry for entry in plan["timeline"] if str(entry.get("id")) == item_id),
            None,
        )
        if not item:
            return
        segments = item.setdefault("narrationSegments", [])
        if not isinstance(segments, list):
            segments = []
            item["narrationSegments"] = segments
        segment_id = segment.get("id")
        if not any(existing.get("id") == segment_id for existing in segments if isinstance(existing, dict)):
            index = max(0, min(int(metadata.get("segmentIndex", len(segments))), len(segments)))
            segments.insert(index, segment)
            save_plan(project_path, plan)


def restore_trash_group(
    project_path: Path,
    trash_id: str,
    *,
    conflict_policy: str = "rename",
) -> dict[str, Any]:
    if conflict_policy not in ALLOWED_RESTORE_POLICIES:
        raise HTTPException(status_code=400, detail="Unsupported conflict policy")
    record = read_trash_record(project_path, trash_id)
    if record.get("status") != "TRASHED":
        raise HTTPException(status_code=409, detail="Trash group is not restorable")

    restored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    restored_paths: dict[str, str] = {}

    for item in record.get("items", []):
        if not isinstance(item, dict):
            continue
        source = project_path / str(item.get("trashPath", ""))
        original = ROOT / str(item.get("originalPath", ""))
        if not source.is_file():
            skipped.append({**item, "reason": "trash-file-missing"})
            continue
        destination = original
        if destination.exists():
            if conflict_policy == "keep":
                skipped.append({**item, "reason": "destination-exists"})
                continue
            destination = restored_name(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        original_rel = str(item.get("originalPath"))
        restored_rel = relative_to_root(destination)
        restored_paths[original_rel] = restored_rel
        restored.append({**item, "restoredPath": restored_rel})

    restore_metadata(project_path, record, restored_paths)
    record["status"] = "RESTORED" if not skipped else "PARTIALLY_RESTORED"
    record["restoredAt"] = iso_now()
    record["restoredItems"] = restored
    record["skippedItems"] = skipped
    record["restorable"] = False
    write_trash_record(project_path, record)
    mark_output_state(
        project_path,
        "RESTORED_UNVERIFIED",
        reason="trash group restored",
        trash_id=trash_id,
    )
    return record


def purge_trash_group(project_path: Path, trash_id: str) -> dict[str, Any]:
    record = read_trash_record(project_path, trash_id)
    if record.get("status") != "TRASHED":
        raise HTTPException(status_code=409, detail="Only active trash can be purged")
    shutil.rmtree(trash_items_dir(project_path) / trash_id, ignore_errors=True)
    record["status"] = "PURGED"
    record["purgedAt"] = iso_now()
    record["restorable"] = False
    write_trash_record(project_path, record)
    return record


def render_state_for_file(
    project_path: Path,
    state: dict[str, Any],
    mode: str,
    path: Path,
    fingerprint: str,
) -> str:
    if not path.is_file():
        return "MISSING"
    output_record = state.get("outputs", {}).get(mode, {})
    if not isinstance(output_record, dict):
        return "STALE"
    if output_record.get("fingerprint") == fingerprint:
        return "CURRENT"
    if state.get("state") == "RESTORED_UNVERIFIED":
        return "RESTORED_UNVERIFIED"
    return "STALE"


def output_inventory(project_name: str) -> dict[str, Any]:
    project_path = require_project_path(project_name)
    project_output = output_dir(project_name)
    fingerprint = project_fingerprint(project_path)
    state = load_output_state(project_path)
    final = project_output / "vlog.mp4"
    preview = project_output / "preview.mp4"
    cut_root = project_output / "render-assets"
    cuts = [
        {
            **file_summary(path),
            "relativePath": str(path.relative_to(project_output)),
            "state": "CURRENT"
            if state.get("outputs", {}).get("final", {}).get("fingerprint") == fingerprint
            or state.get("outputs", {}).get("preview", {}).get("fingerprint") == fingerprint
            else "STALE",
        }
        for path in iter_files(cut_root)
    ]
    all_files = iter_files(project_output)
    return {
        "project": project_path.name,
        "fingerprint": fingerprint,
        "state": state.get("state", "MISSING"),
        "final": {
            **(file_summary(final) if final.is_file() else {"path": "", "name": "vlog.mp4", "sizeBytes": 0}),
            "exists": final.is_file(),
            "state": render_state_for_file(project_path, state, "final", final, fingerprint),
            "downloadUrl": f"api/download/{project_path.name}",
        },
        "preview": {
            **(file_summary(preview) if preview.is_file() else {"path": "", "name": "preview.mp4", "sizeBytes": 0}),
            "exists": preview.is_file(),
            "state": render_state_for_file(project_path, state, "preview", preview, fingerprint),
            "downloadUrl": f"api/output-file/{project_path.name}/preview.mp4",
        },
        "cuts": cuts,
        "artifactCount": len(all_files),
        "totalSizeBytes": sum(path.stat().st_size for path in all_files),
        "updatedAt": state.get("updatedAt"),
        "reason": state.get("reason", ""),
    }


def ensure_required_roles(plan: dict[str, Any]) -> None:
    roles = [item.get("role") for item in plan.get("timeline", []) if isinstance(item, dict)]
    if "opening" not in roles:
        raise HTTPException(status_code=400, detail="Opening video is required")
    if "ending" not in roles:
        raise HTTPException(status_code=400, detail="Ending video is required")


def run_render(project_name: str, mode: str) -> dict[str, Any]:
    if mode not in {"preview", "final"}:
        raise HTTPException(status_code=400, detail="mode must be preview or final")
    project_path = require_project_path(project_name)
    plan = load_plan(project_path)
    ensure_required_roles(plan)
    project_output = output_dir(project_name)
    project_output.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if mode == "preview":
        env.setdefault("VLOG_SKIP_TRANSCRIPTION", "1")
        env.setdefault("VIDEO_WIDTH", "960")
        env.setdefault("VIDEO_HEIGHT", "540")
        env.setdefault("VIDEO_FPS", "24")

    final_path = project_output / "vlog.mp4"
    backup_path = project_output / ".vlog-final-before-preview.mp4"
    had_final = final_path.is_file()
    if mode == "preview" and had_final:
        shutil.copy2(final_path, backup_path)

    mark_output_state(project_path, "RENDERING", reason=f"{mode} render started")
    try:
        process = subprocess.run(
            ["bash", str(ROOT / "scripts" / "process_vlog.sh"), str(project_path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
            env=env,
        )
        rendered = subprocess.run(
            ["bash", str(ROOT / "scripts" / "render_vlog.sh"), project_path.name],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
            env=env,
        )
        if not final_path.is_file():
            raise HTTPException(status_code=500, detail="Rendered video was not created")
        if mode == "preview":
            preview_path = project_output / "preview.mp4"
            final_path.replace(preview_path)
            if backup_path.is_file():
                backup_path.replace(final_path)
        fingerprint = project_fingerprint(project_path)
        state = load_output_state(project_path)
        outputs = state.setdefault("outputs", {})
        output_path = project_output / ("preview.mp4" if mode == "preview" else "vlog.mp4")
        outputs[mode] = {
            "fingerprint": fingerprint,
            "renderedAt": iso_now(),
            "path": relative_to_root(output_path),
            "sizeBytes": output_path.stat().st_size,
        }
        state["state"] = "CURRENT"
        state["updatedAt"] = iso_now()
        state["reason"] = f"{mode} render completed"
        save_output_state(project_path, state)
        return {
            "status": "rendered",
            "mode": mode,
            "output": relative_to_root(output_path),
            "processLog": process.stdout[-4000:],
            "renderLog": rendered.stdout[-4000:],
            "fingerprint": fingerprint,
        }
    except subprocess.TimeoutExpired as exc:
        mark_output_state(project_path, "FAILED", reason=f"{mode} render timed out")
        raise HTTPException(status_code=504, detail="Compilation timed out") from exc
    except subprocess.CalledProcessError as exc:
        mark_output_state(project_path, "FAILED", reason=f"{mode} render failed")
        raise HTTPException(
            status_code=500,
            detail=(exc.stderr or exc.stdout or str(exc))[-4000:],
        ) from exc
    finally:
        if mode == "preview" and backup_path.is_file() and not final_path.is_file():
            backup_path.replace(final_path)


@app.get("/")
def composition_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "compose.html")


@app.get("/api/source/{project_name}/{item_id}")
def source_media(project_name: str, item_id: str) -> FileResponse:
    project_path = require_project_path(project_name)
    plan = load_plan(project_path)
    item = next(
        (entry for entry in plan["timeline"] if str(entry.get("id")) == item_id),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    source = resolve_project_file(project_path, item.get("source"))
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Source media not found")
    suffix = source.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
    }.get(suffix, "video/mp4" if item.get("type") == "video" else "application/octet-stream")
    return FileResponse(source, media_type=media_type)


@app.get("/api/output/{project_name}")
def get_output(project_name: str) -> dict[str, Any]:
    return output_inventory(project_name)


@app.post("/api/output/render")
def render_output(
    project: str = Form(...),
    mode: str = Form("preview"),
) -> dict[str, Any]:
    return run_render(project, mode)


@app.post("/api/compile")
def compile_compat(
    project: str = Form(...),
    render: bool = Form(True),
) -> dict[str, Any]:
    if not render:
        raise HTTPException(status_code=400, detail="Preparation-only mode is not exposed here")
    return run_render(project, "final")


@app.get("/api/output-file/{project_name}/{filename}")
def output_file(project_name: str, filename: str) -> FileResponse:
    if filename not in {"preview.mp4", "vlog.mp4"}:
        raise HTTPException(status_code=400, detail="Unsupported output filename")
    target = output_dir(project_name) / filename
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(target, media_type="video/mp4", filename=f"{safe_project_name(project_name)}-{filename}")


@app.delete("/api/output/cut")
def delete_output_cut(
    project: str = Form(...),
    relative_path: str = Form(...),
) -> dict[str, Any]:
    project_path = require_project_path(project)
    project_output = output_dir(project)
    target = (project_output / relative_path).resolve()
    cut_root = (project_output / "render-assets").resolve()
    if not path_is_within(target, cut_root) or not target.is_file():
        raise HTTPException(status_code=404, detail="Generated cut not found")
    record = create_trash_group(
        project_path=project_path,
        kind="generated-cut",
        label=f"{target.name} の生成物",
        paths=[target],
        metadata={"relativePath": relative_path},
    )
    mark_output_state(project_path, "STALE", reason="generated cut deleted", trash_id=record["trashId"])
    return {
        "status": "trashed",
        "trash": record,
        "undoAvailableSeconds": 60,
        "outputState": "STALE",
    }


@app.delete("/api/output/all")
def delete_all_output(project: str = Form(...)) -> dict[str, Any]:
    project_path = require_project_path(project)
    files = iter_files(output_dir(project))
    if not files:
        return {
            "status": "empty",
            "trash": None,
            "undoAvailableSeconds": 0,
            "outputState": "MISSING",
        }
    record = create_trash_group(
        project_path=project_path,
        kind="generated-output-all",
        label="書き出し生成物一式",
        paths=files,
        metadata={"artifactCount": len(files)},
    )
    mark_output_state(project_path, "MISSING", reason="all generated output deleted", trash_id=record["trashId"])
    return {
        "status": "trashed",
        "trash": record,
        "undoAvailableSeconds": 60,
        "outputState": "MISSING",
    }


@app.get("/api/trash/{project_name}")
def list_trash(project_name: str) -> dict[str, Any]:
    project_path = require_project_path(project_name)
    records = active_trash_records(project_path)
    return {
        "project": project_path.name,
        "records": records,
        "count": len(records),
        "totalSizeBytes": sum(int(record.get("sizeBytes", 0)) for record in records),
    }


@app.post("/api/trash/restore")
def restore_trash(
    project: str = Form(...),
    trash_id: str = Form(...),
    conflict_policy: str = Form("rename"),
) -> dict[str, Any]:
    project_path = require_project_path(project)
    record = restore_trash_group(
        project_path,
        trash_id,
        conflict_policy=conflict_policy,
    )
    return {"status": record["status"].lower(), "trash": record, "outputState": "RESTORED_UNVERIFIED"}


@app.post("/api/trash/restore-all")
def restore_all_trash(
    project: str = Form(...),
    conflict_policy: str = Form("rename"),
) -> dict[str, Any]:
    project_path = require_project_path(project)
    results = [
        restore_trash_group(project_path, str(record["trashId"]), conflict_policy=conflict_policy)
        for record in active_trash_records(project_path)
    ]
    return {"status": "restored", "records": results, "count": len(results)}


@app.delete("/api/trash/purge")
def purge_trash(
    project: str = Form(...),
    trash_id: str = Form(...),
    confirmation: str = Form(...),
) -> dict[str, Any]:
    if confirmation != "完全削除":
        raise HTTPException(status_code=400, detail="Permanent deletion confirmation is required")
    project_path = require_project_path(project)
    record = purge_trash_group(project_path, trash_id)
    return {"status": "purged", "trash": record}


@app.delete("/api/trash/purge-all")
def purge_all_trash(
    project: str = Form(...),
    confirmation: str = Form(...),
) -> dict[str, Any]:
    if confirmation != "ゴミ箱を空にする":
        raise HTTPException(status_code=400, detail="Empty-trash confirmation is required")
    project_path = require_project_path(project)
    records = [
        purge_trash_group(project_path, str(record["trashId"]))
        for record in active_trash_records(project_path)
    ]
    return {"status": "purged", "records": records, "count": len(records)}


@app.delete("/api/material")
def delete_material_v3(
    project: str = Form(...),
    item_id: str = Form(...),
) -> dict[str, Any]:
    project_path = require_project_path(project)
    plan = load_plan(project_path)
    index = next(
        (position for position, item in enumerate(plan["timeline"]) if str(item.get("id")) == item_id),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    item = plan["timeline"][index]
    references: list[Path] = []
    for value in [item.get("source"), item.get("narration")]:
        target = resolve_project_file(project_path, value)
        if target is not None and target.is_file():
            references.append(target)
    segments = item.get("narrationSegments")
    if isinstance(segments, list):
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            target = resolve_project_file(project_path, segment.get("narration"))
            if target is not None and target.is_file():
                references.append(target)

    record = create_trash_group(
        project_path=project_path,
        kind="source-material",
        label=f"{item.get('role', '素材')} を構成から削除",
        paths=references,
        metadata={"timelineIndex": index, "timelineItem": item},
    )
    plan["timeline"].pop(index)
    save_plan(project_path, plan)
    mark_output_state(project_path, "STALE", reason="source material deleted", trash_id=record["trashId"])
    return {
        "status": "deleted",
        "item": item,
        "timeline": plan["timeline"],
        "trash": record,
        "undoAvailableSeconds": 60,
    }


@app.delete("/api/narration-segment")
def delete_narration_segment_v3(
    project: str = Form(...),
    item_id: str = Form(...),
    segment_id: str = Form(...),
) -> dict[str, Any]:
    project_path = require_project_path(project)
    plan = load_plan(project_path)
    item = next(
        (entry for entry in plan["timeline"] if str(entry.get("id")) == item_id),
        None,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Timeline item not found")
    segments = item.get("narrationSegments")
    if not isinstance(segments, list):
        raise HTTPException(status_code=404, detail="Narration segment not found")
    index = next(
        (position for position, segment in enumerate(segments) if str(segment.get("id")) == segment_id),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Narration segment not found")
    segment = segments[index]
    target = resolve_project_file(project_path, segment.get("narration"))
    paths = [target] if target is not None and target.is_file() else []
    record = create_trash_group(
        project_path=project_path,
        kind="narration-segment",
        label=f"{segment.get('startSeconds', 0)}〜{segment.get('endSeconds', 0)}秒の範囲音声",
        paths=paths,
        metadata={
            "itemId": item_id,
            "segmentIndex": index,
            "segment": segment,
        },
    )
    segments.pop(index)
    if not segments:
        item.pop("narrationSegments", None)
    save_plan(project_path, plan)
    mark_output_state(project_path, "STALE", reason="range narration deleted", trash_id=record["trashId"])
    return {
        "status": "deleted",
        "segment": segment,
        "item": item,
        "timeline": plan["timeline"],
        "trash": record,
        "undoAvailableSeconds": 60,
    }


# Existing v2 recording, upload, audio-mode, reorder, health, and download routes
# remain available. v3 routes are registered first, so the explicit overrides
# above win for matching paths.
app.include_router(base_app.router)
