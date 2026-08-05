#!/usr/bin/env python3
"""Reconcile durable cloud-render state with Cloud Run and GCS.

A request may remain RUNNING after the asynchronous Cloud Run execution has
already finished. This module turns the status read into a bounded, idempotent
self-healing check and materializes the completed artifact into the existing
local output contract.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from web_console.app import OUTPUT_DIR, safe_project_name
from web_console.cloud_render_handoff import HandoffStore

Runner = Callable[..., subprocess.CompletedProcess[str]]
COMPLETION_GRACE_SECONDS = 120


def _run_json(command: list[str], *, runner: Runner) -> dict[str, Any] | None:
    try:
        completed = runner(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        value = json.loads(completed.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def inspect_execution(record: dict[str, Any], *, runner: Runner = subprocess.run) -> dict[str, Any] | None:
    execution = str(record.get("execution") or "").strip()
    policy = record.get("policy") or {}
    project_id = str(policy.get("project_id") or "").strip()
    region = str(policy.get("region") or "").strip()
    if not execution or not project_id or not region:
        return None
    return _run_json(
        [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "describe",
            execution,
            f"--project={project_id}",
            f"--region={region}",
            "--format=json",
        ],
        runner=runner,
    )


def _execution_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the Cloud Run status object across gcloud output shapes."""
    status = payload.get("status")
    return status if isinstance(status, dict) else payload


def execution_outcome(payload: dict[str, Any]) -> str:
    """Return RUNNING, SUCCEEDED, or FAILED from a Cloud Run execution payload."""
    status = _execution_status(payload)
    if int(status.get("succeededCount") or 0) > 0:
        return "SUCCEEDED"
    if int(status.get("failedCount") or 0) > 0 or int(status.get("cancelledCount") or 0) > 0:
        return "FAILED"
    for condition in status.get("conditions") or []:
        if not isinstance(condition, dict) or condition.get("type") != "Completed":
            continue
        value = str(condition.get("status") or "").lower()
        if value == "true":
            return "SUCCEEDED"
        if value == "false":
            return "FAILED"
    return "RUNNING"


def artifact_exists(uri: str, *, runner: Runner = subprocess.run) -> bool:
    if not uri.startswith("gs://"):
        return False
    try:
        runner(
            ["gcloud", "storage", "ls", uri],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


def local_output_path(record: dict[str, Any]) -> Path:
    project = safe_project_name(str(record.get("project") or ""))
    filename = "preview.mp4" if record.get("mode") == "preview" else "vlog.mp4"
    return OUTPUT_DIR / project / filename


def materialize_artifact(
    record: dict[str, Any],
    *,
    runner: Runner = subprocess.run,
) -> Path | None:
    uri = str(record.get("output_uri") or "")
    target = local_output_path(record)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".cloud-download")
    temporary.unlink(missing_ok=True)
    try:
        runner(
            ["gcloud", "storage", "cp", uri, str(temporary)],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            temporary.unlink(missing_ok=True)
            return None
        temporary.replace(target)
    except (subprocess.SubprocessError, OSError):
        temporary.unlink(missing_ok=True)
        return None
    return target


def _timed_out(record: dict[str, Any], now: int) -> bool:
    policy = record.get("policy") or {}
    started = int(record.get("consumed_at") or record.get("issued_at") or now)
    limit = int(policy.get("timeout_seconds") or 600) + COMPLETION_GRACE_SECONDS
    return now > started + limit


def reconcile_active_record(
    store: HandoffStore,
    record: dict[str, Any],
    *,
    runner: Runner = subprocess.run,
    now: int | None = None,
) -> dict[str, Any]:
    """Idempotently reconcile one RUNNING request and return its latest record."""
    if record.get("status") != "RUNNING":
        return record

    payload = inspect_execution(record, runner=runner)
    if payload is None:
        return record

    outcome = execution_outcome(payload)
    execution_status = _execution_status(payload)
    request_id = str(record["request_id"])
    if outcome == "FAILED":
        message = "Cloud Run execution failed"
        for condition in execution_status.get("conditions") or []:
            if isinstance(condition, dict) and condition.get("type") == "Completed":
                message = str(condition.get("message") or message)
                break
        return store.finish(request_id, success=False, error=message)

    if outcome == "SUCCEEDED":
        uri = str(record.get("output_uri") or "")
        if artifact_exists(uri, runner=runner):
            target = materialize_artifact(record, runner=runner)
            if target is not None:
                return store.finish(request_id, success=True)
        if _timed_out(record, int(time.time() if now is None else now)):
            return store.finish(
                request_id,
                success=False,
                error="Cloud Run completed but the output artifact could not be recovered",
            )

    return record
