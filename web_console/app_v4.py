#!/usr/bin/env python3
"""Symlink-aware entry point for the Vlog composition console.

Oracle keeps ``projects`` and ``output`` as symlinks to persistent production
storage. This layer keeps the v3 implementation intact while fixing storage path
identity, providing a correctly rooted new-project wizard, and allowing safe
Unicode project names.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from fastapi import Form, HTTPException, Request
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
    return FileResponse(STATIC_DIR / "index.html")


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
