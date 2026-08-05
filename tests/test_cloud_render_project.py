from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from web_console.cloud_render_handoff import HandoffError, HandoffStore
from web_console import cloud_render_project as project


def fake_security(paths: list[Path]) -> dict[str, object]:
    files = []
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append({"path": str(path), "sha256": digest, "size_bytes": path.stat().st_size})
    return {
        "status": "PASS",
        "policy": "rts-media-security-gate-v1",
        "files": files,
        "security_fingerprint": "a" * 64,
    }


def test_prepare_project_uploads_inputs_then_manifest_and_waits_for_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_a = tmp_path / "opening.mp4"
    source_b = tmp_path / "ending.mp4"
    source_a.write_bytes(b"opening")
    source_b.write_bytes(b"ending")
    stage_root = tmp_path / "staging"
    monkeypatch.setattr(project, "STAGING_ROOT", stage_root)
    monkeypatch.setattr(project, "collect_timeline_sources", lambda name: (tmp_path, [source_a, source_b]))
    monkeypatch.setattr(project, "create_security_pass", fake_security)
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    store = HandoffStore(tmp_path / "handoff")
    prepared = project.prepare_project(store, "demo", "preview", runner=runner, now=1000)

    assert prepared.record["status"] == "AWAITING_APPROVAL"
    assert prepared.record["consumed_at"] is None
    assert prepared.record["security"]["files"] == 2
    assert prepared.manifest["approval_id"] == prepared.record["request_id"]
    assert prepared.manifest["task_count"] == 1
    assert len(commands) == 3
    assert commands[0][:3] == ["gcloud", "storage", "cp"]
    assert commands[1][:3] == ["gcloud", "storage", "cp"]
    assert commands[2][-2].startswith("gs://rts-vlog-render-files-20260805/manifests/")
    assert (prepared.staging_dir / "SECURITY_PASS.json").is_file()
    assert (prepared.staging_dir / "manifest.json").is_file()


def test_prepare_project_rolls_back_request_when_manifest_upload_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "opening.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(project, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(project, "collect_timeline_sources", lambda name: (tmp_path, [source]))
    monkeypatch.setattr(project, "create_security_pass", fake_security)
    calls = 0

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(1, command, stderr="manifest upload failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    store = HandoffStore(tmp_path / "handoff")
    with pytest.raises(HandoffError, match="manifest upload failed"):
        project.prepare_project(store, "demo", "final", runner=runner, now=1000)
    assert list((tmp_path / "handoff").glob("*.json")) == []


def test_stage_ascii_inputs_renames_non_ascii_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "動画素材.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(project, "STAGING_ROOT", tmp_path / "staging")
    stage, staged = project.stage_ascii_inputs("demo", [source], "run-1")
    assert stage.is_dir()
    assert staged[0].name == "input-001.mp4"
    assert staged[0].read_bytes() == b"video"
