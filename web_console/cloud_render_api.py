#!/usr/bin/env python3
"""HTTP API for governed Vlog cloud-render handoff."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Form, HTTPException

from web_console.app import ROOT
from web_console.cloud_render_executor import dispatch
from web_console.cloud_render_handoff import (
    HandoffError,
    HandoffStore,
    RenderPolicy,
    SecurityBinding,
    normalize_hashes,
)
from web_console.cloud_render_project import prepare_project
from web_console.cloud_render_reconcile import reconcile_active_record

router = APIRouter(prefix="/api/cloud-render", tags=["cloud-render-handoff"])
STORE_ROOT = ROOT / "state" / "cloud-render-handoff"


def handoff_store() -> HandoffStore:
    return HandoffStore(STORE_ROOT)


def _parse_hashes(raw: str) -> tuple[str, ...]:
    value = raw.strip()
    if not value:
        raise HandoffError("input hashes are required")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = [part.strip() for part in value.split(",") if part.strip()]
    if not isinstance(parsed, list):
        raise HandoffError("input hashes must be a JSON array or comma-separated list")
    return normalize_hashes(str(item) for item in parsed)


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": record["request_id"],
        "status": record["status"],
        "project": record["project"],
        "mode": record["mode"],
        "confirmation": record["confirmation"],
        "issued_at": record["issued_at"],
        "expires_at": record["expires_at"],
        "consumed_at": record.get("consumed_at"),
        "single_use": record["single_use"],
        "estimated_max_yen": record["policy"]["estimated_max_yen"],
        "execution": record.get("execution"),
        "output_uri": record["output_uri"],
        "error": record.get("error"),
        "security": {
            "policy": record["security"]["policy"],
            "fingerprint": record["security"]["fingerprint"],
            "files": record["security"]["files"],
        },
    }


@router.post("/prepare", status_code=201)
def prepare_cloud_render(
    project: str = Form(...),
    mode: str = Form("preview"),
    manifest_uri: str = Form(...),
    output_uri: str = Form(...),
    security_policy: str = Form(...),
    security_fingerprint: str = Form(...),
    input_hashes: str = Form(...),
    files: int = Form(..., ge=1),
) -> dict[str, Any]:
    try:
        hashes = _parse_hashes(input_hashes)
        security = SecurityBinding(
            policy=security_policy.strip(),
            fingerprint=security_fingerprint.strip().lower(),
            input_hashes=hashes,
            files=files,
        )
        record = handoff_store().create_pending(
            project=project,
            mode=mode,
            manifest_uri=manifest_uri,
            output_uri=output_uri,
            security=security,
            policy=RenderPolicy(),
        )
    except HandoffError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _public_record(record)


@router.post("/prepare-project", status_code=201)
def prepare_cloud_render_project(
    project: str = Form(...),
    mode: str = Form("preview"),
) -> dict[str, Any]:
    """Inspect project sources, upload bounded inputs, and create approval state.

    This endpoint does not consume approval and does not start Cloud Run.
    """
    try:
        prepared = prepare_project(handoff_store(), project, mode)
    except HandoffError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    response = _public_record(prepared.record)
    response["staging"] = str(prepared.staging_dir)
    response["manifest_uri"] = prepared.record["manifest_uri"]
    return response


@router.post("/approve")
def approve_cloud_render(
    request_id: str = Form(...),
    confirmation: str = Form(...),
) -> dict[str, Any]:
    try:
        record = handoff_store().consume(request_id, confirmation=confirmation)
    except HandoffError as error:
        detail = str(error)
        status = 404 if detail == "render request not found" else 409
        raise HTTPException(status_code=status, detail=detail) from error
    return _public_record(record)


@router.post("/dispatch")
def dispatch_cloud_render(request_id: str = Form(...)) -> dict[str, Any]:
    store = handoff_store()
    try:
        result = dispatch(store, request_id)
        record = store.read(request_id)
    except HandoffError as error:
        detail = str(error)
        status = 404 if detail == "render request not found" else 409
        raise HTTPException(status_code=status, detail=detail) from error
    response = _public_record(record)
    response["execution"] = result.execution
    return response


@router.get("/status/{request_id}")
def cloud_render_status(request_id: str) -> dict[str, Any]:
    store = handoff_store()
    try:
        record = store.read(request_id)
        record = reconcile_active_record(store, record)
    except HandoffError as error:
        detail = str(error)
        status = 404 if detail == "render request not found" else 409
        raise HTTPException(status_code=status, detail=detail) from error
    return _public_record(record)
