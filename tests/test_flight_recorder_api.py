from __future__ import annotations

import json

from fastapi.testclient import TestClient

from web_console.app_v5 import app
from web_console import flight_recorder_api


def event(session_id: str, sequence: int, **payload):
    return {
        "version": 1,
        "session_id": session_id,
        "event_id": f"evt-{sequence}",
        "sequence": sequence,
        "recorded_at": "2026-08-06T12:00:00Z",
        "type": "interaction",
        "page": {"path": "/", "query_keys": [], "visibility": "visible", "online": True},
        "payload": payload,
    }


def test_ingest_appends_and_summary_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(flight_recorder_api, "STORE_ROOT", tmp_path)
    client = TestClient(app)
    sid = "rts-fr-session-0001"
    response = client.post("/api/flight-recorder/events", json={"session_id": sid, "events": [event(sid, 1), event(sid, 2)]})
    assert response.status_code == 202
    assert response.json()["accepted"] == 2
    lines = (tmp_path / f"{sid}.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    summary = client.get(f"/api/flight-recorder/sessions/{sid}")
    assert summary.status_code == 200
    assert summary.json()["last_sequence"] == 2


def test_ingest_rejects_mixed_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(flight_recorder_api, "STORE_ROOT", tmp_path)
    client = TestClient(app)
    sid = "rts-fr-session-0002"
    response = client.post("/api/flight-recorder/events", json={"session_id": sid, "events": [event("rts-fr-other-0002", 1)]})
    assert response.status_code == 409


def test_ingest_rejects_reversed_or_duplicate_sequence(tmp_path, monkeypatch):
    monkeypatch.setattr(flight_recorder_api, "STORE_ROOT", tmp_path)
    client = TestClient(app)
    sid = "rts-fr-session-0003"
    response = client.post("/api/flight-recorder/events", json={"session_id": sid, "events": [event(sid, 2), event(sid, 2)]})
    assert response.status_code == 409


def test_ingest_redacts_sensitive_keys_server_side(tmp_path, monkeypatch):
    monkeypatch.setattr(flight_recorder_api, "STORE_ROOT", tmp_path)
    client = TestClient(app)
    sid = "rts-fr-session-0004"
    response = client.post("/api/flight-recorder/events", json={"session_id": sid, "events": [event(sid, 1, authorization="Bearer nope", nested={"api_key": "secret"})]})
    assert response.status_code == 202
    stored = json.loads((tmp_path / f"{sid}.jsonl").read_text(encoding="utf-8"))
    assert stored["payload"]["authorization"] == "[REDACTED]"
    assert stored["payload"]["nested"]["api_key"] == "[REDACTED]"


def test_ingest_rejects_invalid_session_path(tmp_path, monkeypatch):
    monkeypatch.setattr(flight_recorder_api, "STORE_ROOT", tmp_path)
    client = TestClient(app)
    response = client.post("/api/flight-recorder/events", json={"session_id": "../../escape", "events": []})
    assert response.status_code == 400
    assert not list(tmp_path.glob("*"))
