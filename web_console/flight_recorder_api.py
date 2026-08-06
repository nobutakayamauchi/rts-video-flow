#!/usr/bin/env python3
"""Bounded, append-only HTTP ingest for RTS Flight Recorder events."""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from web_console.app import ROOT

router = APIRouter(prefix="/api/flight-recorder", tags=["rts-flight-recorder"])
STORE_ROOT = ROOT / "state" / "flight-recorder"
MAX_EVENTS_PER_BATCH = 100
MAX_EVENT_BYTES = 32 * 1024
MAX_BATCH_BYTES = 256 * 1024
SESSION_RE = re.compile(r"^[A-Za-z0-9._-]{8,160}$")
SENSITIVE_KEY = re.compile(r"authorization|cookie|token|secret|password|passwd|api[-_]?key", re.I)
_WRITE_LOCK = threading.Lock()


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, list):
        return [_sanitize(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key)[:120]: ("[REDACTED]" if SENSITIVE_KEY.search(str(key)) else _sanitize(item, depth + 1))
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, str):
        return value[:4000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:1000]


def _validate_batch(payload: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="flight recorder payload must be an object")
    session_id = str(payload.get("session_id", ""))
    if not SESSION_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="invalid flight recorder session_id")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise HTTPException(status_code=400, detail="events must be a non-empty array")
    if len(events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(status_code=413, detail="too many flight recorder events")

    accepted: list[dict[str, Any]] = []
    previous_sequence = 0
    for raw in events:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="each flight recorder event must be an object")
        if raw.get("session_id") != session_id:
            raise HTTPException(status_code=409, detail="mixed flight recorder sessions are not allowed")
        sequence = raw.get("sequence")
        if not isinstance(sequence, int) or sequence <= previous_sequence:
            raise HTTPException(status_code=409, detail="event sequence must be strictly increasing")
        event = _sanitize(raw)
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_EVENT_BYTES:
            raise HTTPException(status_code=413, detail="flight recorder event is too large")
        accepted.append(event)
        previous_sequence = sequence
    return session_id, accepted


def _append_events(session_id: str, events: list[dict[str, Any]]) -> Path:
    STORE_ROOT.mkdir(parents=True, exist_ok=True)
    destination = STORE_ROOT / f"{session_id}.jsonl"
    lines = "".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events)
    with _WRITE_LOCK:
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(lines)
            handle.flush()
    return destination


@router.post("/events", status_code=202)
async def ingest_events(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > MAX_BATCH_BYTES:
        raise HTTPException(status_code=413, detail="flight recorder batch is too large")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="invalid flight recorder JSON") from error
    session_id, events = _validate_batch(payload)
    destination = _append_events(session_id, events)
    return {
        "accepted": len(events),
        "session_id": session_id,
        "last_sequence": events[-1]["sequence"],
        "stored": destination.name,
    }


@router.get("/sessions/{session_id}")
def session_summary(session_id: str) -> dict[str, Any]:
    if not SESSION_RE.fullmatch(session_id):
        raise HTTPException(status_code=400, detail="invalid flight recorder session_id")
    source = STORE_ROOT / f"{session_id}.jsonl"
    if not source.is_file():
        raise HTTPException(status_code=404, detail="flight recorder session not found")
    events = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {
        "session_id": session_id,
        "event_count": len(events),
        "first_sequence": events[0]["sequence"] if events else None,
        "last_sequence": events[-1]["sequence"] if events else None,
        "last_event_type": events[-1].get("type") if events else None,
    }
