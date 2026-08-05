#!/usr/bin/env python3
"""Dispatch approved Vlog render requests to Cloud Run Jobs.

The executor never creates approval. It only accepts integrity-checked records
that have already consumed explicit single-use approval and are in QUEUED.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Sequence

from web_console.cloud_render_handoff import HandoffError, HandoffStore


@dataclass(frozen=True)
class DispatchResult:
    execution: str
    command: tuple[str, ...]


def build_execute_command(record: dict[str, Any]) -> tuple[str, ...]:
    """Build the bounded Cloud Run command for one approved request."""
    if record.get("status") != "QUEUED":
        raise HandoffError("render request is not queued")
    if record.get("consumed_at") is None:
        raise HandoffError("render approval has not been consumed")

    policy = record.get("policy") or {}
    project_id = str(policy.get("project_id") or "").strip()
    region = str(policy.get("region") or "").strip()
    job = str(policy.get("job") or "").strip()
    manifest_uri = str(record.get("manifest_uri") or "").strip()
    request_id = str(record.get("request_id") or "").strip()
    task_count = int(policy.get("task_count") or 0)
    timeout_seconds = int(policy.get("timeout_seconds") or 0)

    if not project_id or not region or not job or not request_id:
        raise HandoffError("render execution policy is incomplete")
    if not manifest_uri.startswith("gs://"):
        raise HandoffError("render manifest URI is invalid")
    if task_count != 1:
        raise HandoffError("only one render task is permitted")
    if not 1 <= timeout_seconds <= 3600:
        raise HandoffError("render timeout is outside the approved limit")

    timeout_minutes = max(1, (timeout_seconds + 59) // 60)
    env_vars = f"RENDER_MANIFEST_URI={manifest_uri},COST_APPROVAL_ID={request_id}"
    return (
        "gcloud",
        "run",
        "jobs",
        "execute",
        job,
        f"--project={project_id}",
        f"--region={region}",
        f"--update-env-vars={env_vars}",
        "--tasks=1",
        f"--task-timeout={timeout_minutes}m",
        "--async",
        "--format=value(metadata.name)",
    )


def parse_execution_name(stdout: str) -> str:
    """Accept either a full resource name or the short execution name."""
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise HandoffError("Cloud Run did not return an execution name")
    value = lines[-1]
    execution = value.rsplit("/", 1)[-1]
    if not execution or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in execution):
        raise HandoffError("Cloud Run returned an invalid execution name")
    return execution


def dispatch(
    store: HandoffStore,
    request_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DispatchResult:
    """Submit one QUEUED request and persist its RUNNING execution name."""
    record = store.read(request_id)
    command = build_execute_command(record)
    try:
        completed = runner(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        store.finish(request_id, success=False, error="Cloud Run dispatch timed out")
        raise HandoffError("Cloud Run dispatch timed out") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "Cloud Run dispatch failed").strip()
        store.finish(request_id, success=False, error=detail)
        raise HandoffError("Cloud Run dispatch failed") from error

    execution = parse_execution_name(completed.stdout)
    store.mark_execution(request_id, execution)
    return DispatchResult(execution=execution, command=command)
