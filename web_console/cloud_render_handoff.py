#!/usr/bin/env python3
"""Governed state core for Vlog cloud-render handoff.

This module intentionally performs no cloud execution yet. It defines the
validated request model and durable state transitions used by the web API.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

ALLOWED_MODES = {"preview", "final"}
TERMINAL_STATES = {"COMPLETED", "FAILED", "REJECTED"}
DEFAULT_TTL_SECONDS = 15 * 60


class HandoffError(ValueError):
    """Raised when a governed handoff transition is invalid."""


@dataclass(frozen=True)
class RenderPolicy:
    project_id: str = "rts-vlog-render"
    region: str = "asia-northeast1"
    bucket: str = "rts-vlog-render-files-20260805"
    job: str = "rts-vlog-render"
    cpu: int = 1
    memory_gib: int = 1
    task_count: int = 1
    parallelism: int = 1
    max_retries: int = 0
    timeout_seconds: int = 600
    estimated_max_yen: int = 3


@dataclass(frozen=True)
class SecurityBinding:
    policy: str
    fingerprint: str
    input_hashes: tuple[str, ...]
    files: int


class HandoffStore:
    """Filesystem-backed request store using atomic replacement."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, request_id: str) -> Path:
        if not request_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in request_id):
            raise HandoffError("invalid request id")
        return self.root / f"{request_id}.json"

    def create_pending(
        self,
        *,
        project: str,
        mode: str,
        manifest_uri: str,
        output_uri: str,
        security: SecurityBinding,
        policy: RenderPolicy,
        now: int | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> dict[str, Any]:
        if mode not in ALLOWED_MODES:
            raise HandoffError("mode must be preview or final")
        if not project.strip():
            raise HandoffError("project is required")
        if not manifest_uri.startswith("gs://") or not output_uri.startswith("gs://"):
            raise HandoffError("cloud URIs must use gs://")
        if not security.input_hashes or security.files != len(security.input_hashes):
            raise HandoffError("security binding does not match input hashes")
        if len(security.fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in security.fingerprint):
            raise HandoffError("invalid security fingerprint")

        issued_at = int(time.time() if now is None else now)
        request_id = secrets.token_urlsafe(18).rstrip("=")
        confirmation = f"{policy.estimated_max_yen}円上限で1回だけ実行"
        record: dict[str, Any] = {
            "version": 1,
            "request_id": request_id,
            "status": "AWAITING_APPROVAL",
            "project": project.strip(),
            "mode": mode,
            "manifest_uri": manifest_uri,
            "output_uri": output_uri,
            "security": {
                "policy": security.policy,
                "fingerprint": security.fingerprint,
                "input_hashes": list(security.input_hashes),
                "files": security.files,
            },
            "policy": asdict(policy),
            "issued_at": issued_at,
            "expires_at": issued_at + int(ttl_seconds),
            "single_use": True,
            "consumed_at": None,
            "confirmation": confirmation,
            "execution": None,
            "error": None,
        }
        record["record_fingerprint"] = record_fingerprint(record)
        self._create_exclusive(self.path_for(request_id), record)
        return record

    def read(self, request_id: str) -> dict[str, Any]:
        path = self.path_for(request_id)
        if not path.is_file():
            raise HandoffError("render request not found")
        record = json.loads(path.read_text(encoding="utf-8"))
        expected = record.pop("record_fingerprint", "")
        actual = record_fingerprint(record)
        record["record_fingerprint"] = expected
        if expected != actual:
            raise HandoffError("render request integrity check failed")
        return record

    def consume(
        self,
        request_id: str,
        *,
        confirmation: str,
        now: int | None = None,
    ) -> dict[str, Any]:
        record = self.read(request_id)
        current = int(time.time() if now is None else now)
        if record["status"] != "AWAITING_APPROVAL":
            raise HandoffError("render request is not awaiting approval")
        if record.get("consumed_at") is not None:
            raise HandoffError("render request already consumed")
        if current > int(record["expires_at"]):
            raise HandoffError("render request expired")
        if not secrets.compare_digest(str(record["confirmation"]), confirmation):
            raise HandoffError("approval confirmation does not match")

        record["status"] = "QUEUED"
        record["consumed_at"] = current
        record["record_fingerprint"] = record_fingerprint(record)
        self._replace(self.path_for(request_id), record)
        return record

    def mark_execution(self, request_id: str, execution: str) -> dict[str, Any]:
        if not execution.strip():
            raise HandoffError("execution name is required")
        record = self.read(request_id)
        if record["status"] != "QUEUED" or record.get("execution"):
            raise HandoffError("execution cannot be attached in the current state")
        record["execution"] = execution.strip()
        record["status"] = "RUNNING"
        record["record_fingerprint"] = record_fingerprint(record)
        self._replace(self.path_for(request_id), record)
        return record

    def finish(self, request_id: str, *, success: bool, error: str | None = None) -> dict[str, Any]:
        record = self.read(request_id)
        if record["status"] not in {"QUEUED", "RUNNING"}:
            raise HandoffError("render request is not active")
        record["status"] = "COMPLETED" if success else "FAILED"
        record["error"] = None if success else (error or "cloud render failed")[:2000]
        record["record_fingerprint"] = record_fingerprint(record)
        self._replace(self.path_for(request_id), record)
        return record

    @staticmethod
    def _create_exclusive(path: Path, record: dict[str, Any]) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
        except Exception:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _replace(path: Path, record: dict[str, Any]) -> None:
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(path)


def record_fingerprint(record: dict[str, Any]) -> str:
    payload = {key: value for key, value in record.items() if key != "record_fingerprint"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_hashes(values: Iterable[str]) -> tuple[str, ...]:
    hashes = tuple(sorted(set(str(value).lower() for value in values)))
    for value in hashes:
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise HandoffError("invalid input hash")
    return hashes
