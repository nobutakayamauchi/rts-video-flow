from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


security = load_module("media_security_gate", ROOT / "scripts" / "media_security_gate.py")
cost = load_module("cloud_cost_gate_security", ROOT / "scripts" / "cloud_cost_gate.py")
worker = load_module("cloud_render_worker", ROOT / "cloud_render" / "worker.py")


def valid_probe() -> dict[str, object]:
    return {
        "format": {"duration": "1.25"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "avg_frame_rate": "30/1",
            },
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }


def test_security_pass_is_hash_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    media = tmp_path / "input-001.mp4"
    media.write_bytes(b"safe-test-media")
    monkeypatch.setattr(security, "run_ffprobe", lambda _: valid_probe())
    result = security.create_security_pass([media])
    assert result["status"] == "PASS"
    assert len(result["security_fingerprint"]) == 64
    assert result["files"][0]["sha256"] == security.sha256_file(media)


def test_unsafe_filename_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    media = tmp_path / "$(touch-pwned).mp4"
    media.write_bytes(b"x")
    monkeypatch.setattr(security, "run_ffprobe", lambda _: valid_probe())
    with pytest.raises(ValueError, match="unsafe file name"):
        security.inspect_file(media)


def test_cost_gate_requires_matching_security_size(tmp_path: Path) -> None:
    media = tmp_path / "input-001.mp4"
    media.write_bytes(b"0123456789")
    security_pass = {
        "status": "PASS",
        "policy": "rts-media-security-gate-v1",
        "inspected_at": int(time.time()),
        "security_fingerprint": "a" * 64,
        "files": [
            {
                "path": str(media),
                "sha256": cost.sha256_file(media),
                "size_bytes": media.stat().st_size,
            }
        ],
    }
    path = tmp_path / "security-pass.json"
    path.write_text(json.dumps(security_pass), encoding="utf-8")
    with pytest.raises(SystemExit, match="input size mismatch"):
        cost.load_security_pass(path, 11)
    assert cost.load_security_pass(path, 10)["security_fingerprint"] == "a" * 64


def test_worker_rejects_unapproved_bucket() -> None:
    with pytest.raises(ValueError, match="outside the approved boundary"):
        worker.split_gs_uri("gs://evil-bucket/inputs/x.mp4", prefix="inputs/")


def test_worker_requires_hash_for_every_input() -> None:
    manifest = {
        "approval_id": "approved",
        "security_policy": "rts-media-security-gate-v1",
        "security_fingerprint": "a" * 64,
        "task_count": 1,
        "inputs": ["gs://rts-vlog-render-files-20260805/inputs/x.mp4"],
        "input_hashes": [],
        "output_uri": "gs://rts-vlog-render-files-20260805/outputs/x.mp4",
    }
    with pytest.raises(SystemExit, match="hash list mismatch"):
        worker.validate_manifest(manifest, "approved")
