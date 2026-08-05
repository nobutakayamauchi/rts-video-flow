#!/usr/bin/env python3
"""Prepare one Vlog project for governed Cloud Run rendering.

This module performs bounded local inspection and GCS upload only. It never
consumes approval and never starts Cloud Run. The returned handoff remains in
AWAITING_APPROVAL until the separate approval endpoint is called.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scripts.media_security_gate import create_security_pass
from web_console.app import ROOT, load_plan, resolve_project_file, safe_project_name
from web_console.app_v3 import ensure_required_roles, require_project_path
from web_console.cloud_render_handoff import HandoffError, HandoffStore, RenderPolicy, SecurityBinding

STAGING_ROOT = ROOT / "state" / "cloud-render-staging"


@dataclass(frozen=True)
class PreparedProject:
    record: dict[str, Any]
    security_pass: dict[str, Any]
    manifest: dict[str, Any]
    staging_dir: Path


def collect_timeline_sources(project_name: str) -> tuple[Path, list[Path]]:
    project_path = require_project_path(project_name)
    plan = load_plan(project_path)
    ensure_required_roles(plan)
    sources: list[Path] = []
    seen: set[Path] = set()
    for item in plan.get("timeline", []):
        if not isinstance(item, dict):
            continue
        source = resolve_project_file(project_path, item.get("source"))
        if source is None or not source.is_file():
            raise HandoffError(f"timeline source is missing: {item.get('id', 'unknown')}")
        resolved = source.resolve()
        if resolved not in seen:
            seen.add(resolved)
            sources.append(resolved)
    if not sources:
        raise HandoffError("project has no renderable timeline sources")
    if len(sources) > 32:
        raise HandoffError("project contains more than 32 render inputs")
    return project_path, sources


def stage_ascii_inputs(project_name: str, sources: list[Path], run_id: str) -> tuple[Path, list[Path]]:
    stage = STAGING_ROOT / safe_project_name(project_name) / run_id
    inputs_dir = stage / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=False)
    staged: list[Path] = []
    for index, source in enumerate(sources, start=1):
        target = inputs_dir / f"input-{index:03d}{source.suffix.lower()}"
        shutil.copy2(source, target)
        staged.append(target)
    return stage, staged


def _run(command: list[str], *, runner: Callable[..., subprocess.CompletedProcess[str]]) -> None:
    try:
        runner(command, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as error:
        raise HandoffError("GCS upload timed out") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "GCS upload failed").strip()
        raise HandoffError(detail[-2000:]) from error


def prepare_project(
    store: HandoffStore,
    project_name: str,
    mode: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now: int | None = None,
) -> PreparedProject:
    policy = RenderPolicy()
    current = int(time.time() if now is None else now)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(current)) + f"-{safe_project_name(project_name)}"
    _, sources = collect_timeline_sources(project_name)
    stage, staged = stage_ascii_inputs(project_name, sources, run_id)

    try:
        security_pass = create_security_pass(staged)
        files = security_pass.get("files") or []
        hashes = tuple(str(item["sha256"]) for item in files)
        fingerprint = str(security_pass["security_fingerprint"])
        input_uris = [
            f"gs://{policy.bucket}/inputs/{run_id}/{path.name}"
            for path in staged
        ]
        manifest_uri = f"gs://{policy.bucket}/manifests/{run_id}.json"
        output_uri = f"gs://{policy.bucket}/outputs/{run_id}/output.mp4"

        for path, uri in zip(staged, input_uris, strict=True):
            _run(["gcloud", "storage", "cp", str(path), uri, "--quiet"], runner=runner)

        record = store.create_pending(
            project=project_name,
            mode=mode,
            manifest_uri=manifest_uri,
            output_uri=output_uri,
            security=SecurityBinding(
                policy=str(security_pass["policy"]),
                fingerprint=fingerprint,
                input_hashes=hashes,
                files=len(hashes),
            ),
            policy=policy,
            now=current,
        )
        manifest = {
            "version": 1,
            "approval_id": record["request_id"],
            "project": project_name,
            "mode": mode,
            "task_count": 1,
            "inputs": input_uris,
            "input_hashes": list(hashes),
            "security_policy": security_pass["policy"],
            "security_fingerprint": fingerprint,
            "output_uri": output_uri,
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            _run(["gcloud", "storage", "cp", str(manifest_path), manifest_uri, "--quiet"], runner=runner)
        except Exception:
            store.path_for(record["request_id"]).unlink(missing_ok=True)
            raise
        (stage / "SECURITY_PASS.json").write_text(
            json.dumps(security_pass, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return PreparedProject(record=record, security_pass=security_pass, manifest=manifest, staging_dir=stage)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
