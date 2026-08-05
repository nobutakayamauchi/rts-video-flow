from __future__ import annotations

import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web_console import cloud_render_api


def client_for(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(cloud_render_api, "STORE_ROOT", tmp_path / "handoff")
    app = FastAPI()
    app.include_router(cloud_render_api.router)
    return TestClient(app)


def valid_prepare() -> dict[str, str]:
    digest = hashlib.sha256(b"input").hexdigest()
    return {
        "project": "01-segment-smoke-v3",
        "mode": "preview",
        "manifest_uri": "gs://rts-vlog-render-files-20260805/manifests/test.json",
        "output_uri": "gs://rts-vlog-render-files-20260805/outputs/test/output.mp4",
        "security_policy": "rts-media-security-gate-v1",
        "security_fingerprint": hashlib.sha256(b"security").hexdigest(),
        "input_hashes": json.dumps([digest]),
        "files": "1",
    }


def test_prepare_approve_and_status_are_governed(tmp_path, monkeypatch) -> None:
    client = client_for(tmp_path, monkeypatch)
    prepared = client.post("/api/cloud-render/prepare", data=valid_prepare())
    assert prepared.status_code == 201
    pending = prepared.json()
    assert pending["status"] == "AWAITING_APPROVAL"
    assert pending["estimated_max_yen"] == 3
    assert pending["confirmation"] == "3円上限で1回だけ実行"

    approved = client.post(
        "/api/cloud-render/approve",
        data={"request_id": pending["request_id"], "confirmation": pending["confirmation"]},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "QUEUED"

    duplicate = client.post(
        "/api/cloud-render/approve",
        data={"request_id": pending["request_id"], "confirmation": pending["confirmation"]},
    )
    assert duplicate.status_code == 409

    status = client.get(f"/api/cloud-render/status/{pending['request_id']}")
    assert status.status_code == 200
    assert status.json()["status"] == "QUEUED"
    assert status.json()["security"]["files"] == 1


def test_prepare_rejects_security_file_count_mismatch(tmp_path, monkeypatch) -> None:
    client = client_for(tmp_path, monkeypatch)
    data = valid_prepare()
    data["files"] = "2"
    response = client.post("/api/cloud-render/prepare", data=data)
    assert response.status_code == 400
    assert "security binding" in response.json()["detail"]


def test_status_rejects_unknown_request(tmp_path, monkeypatch) -> None:
    client = client_for(tmp_path, monkeypatch)
    response = client.get("/api/cloud-render/status/not-found")
    assert response.status_code == 404
