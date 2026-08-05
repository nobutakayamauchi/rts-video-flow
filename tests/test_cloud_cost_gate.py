from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cloud_cost_gate.py"
spec = importlib.util.spec_from_file_location("cloud_cost_gate", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
Estimate = module.Estimate
validate = module.validate


def valid_estimate() -> Estimate:
    return Estimate(
        project="rts-vlog-render",
        region="asia-northeast1",
        bucket="rts-vlog-render-files-20260805",
        job="rts-vlog-render",
        input_bytes=10_000_000,
        cpu=2,
        memory_gib=4,
        timeout_seconds=600,
        task_count=1,
        estimated_max_yen=10,
    )


def write_security_pass(pass_path: Path, media_path: Path) -> None:
    payload = {
        "status": "PASS",
        "policy": "rts-media-security-gate-v1",
        "inspected_at": int(time.time()),
        "files": [
            {
                "path": str(media_path),
                "sha256": hashlib.sha256(media_path.read_bytes()).hexdigest(),
                "size_bytes": media_path.stat().st_size,
            }
        ],
        "security_fingerprint": "a" * 64,
    }
    pass_path.write_text(json.dumps(payload), encoding="utf-8")


def test_valid_estimate_passes() -> None:
    assert validate(valid_estimate()) == []


def test_rejects_parallel_tasks() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"task_count": 2}))
    assert "task_count must be 1" in validate(estimate)


def test_rejects_wrong_project_and_region() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"project": "wrong", "region": "us-central1"}))
    errors = validate(estimate)
    assert "project mismatch" in errors
    assert "region mismatch" in errors


def test_rejects_oversized_input() -> None:
    estimate = Estimate(**(valid_estimate().__dict__ | {"input_bytes": module.MAX_INPUT_BYTES + 1}))
    assert "input size exceeds safe maximum" in validate(estimate)


def test_security_pass_revalidates_unchanged_file(tmp_path: Path) -> None:
    media = tmp_path / "safe.mp4"
    media.write_bytes(b"safe-media")
    security_pass = tmp_path / "SECURITY_PASS.json"
    write_security_pass(security_pass, media)

    loaded = module.load_security_pass(security_pass, media.stat().st_size)

    assert loaded["status"] == "PASS"


def test_security_pass_rejects_same_size_content_change(tmp_path: Path) -> None:
    media = tmp_path / "safe.mp4"
    media.write_bytes(b"AAAA")
    security_pass = tmp_path / "SECURITY_PASS.json"
    write_security_pass(security_pass, media)
    media.write_bytes(b"BBBB")

    with pytest.raises(SystemExit, match="security pass file hash mismatch"):
        module.load_security_pass(security_pass, media.stat().st_size)


def test_security_pass_rejects_changed_file_size(tmp_path: Path) -> None:
    media = tmp_path / "safe.mp4"
    media.write_bytes(b"AAAA")
    security_pass = tmp_path / "SECURITY_PASS.json"
    write_security_pass(security_pass, media)
    media.write_bytes(b"AAAA-more")

    with pytest.raises(SystemExit, match="security pass file size changed"):
        module.load_security_pass(security_pass, 4)


def test_security_pass_rejects_missing_file(tmp_path: Path) -> None:
    media = tmp_path / "safe.mp4"
    media.write_bytes(b"AAAA")
    security_pass = tmp_path / "SECURITY_PASS.json"
    write_security_pass(security_pass, media)
    media.unlink()

    with pytest.raises(SystemExit, match="security pass input file missing or unsafe"):
        module.load_security_pass(security_pass, 4)


def test_security_pass_rejects_symlink_input(tmp_path: Path) -> None:
    real_media = tmp_path / "real.mp4"
    real_media.write_bytes(b"AAAA")
    linked_media = tmp_path / "linked.mp4"
    linked_media.symlink_to(real_media)
    security_pass = tmp_path / "SECURITY_PASS.json"
    write_security_pass(security_pass, linked_media)

    with pytest.raises(SystemExit, match="security pass input file missing or unsafe"):
        module.load_security_pass(security_pass, linked_media.stat().st_size)
