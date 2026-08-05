from __future__ import annotations

import hashlib
import json
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


def media_runner_for(streams_by_name: dict[str, list[dict[str, object]]]):
    commands: list[list[str]] = []

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if command[0] == "ffprobe":
            path = Path(command[-1])
            streams = streams_by_name.get(path.name)
            if streams is None and path.name.startswith("input-"):
                streams = [
                    {"index": 0, "codec_name": "hevc", "codec_type": "video"},
                    {"index": 1, "codec_name": "aac", "codec_type": "audio"},
                ]
            if streams is None:
                raise AssertionError(f"unexpected probe target: {path}")
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": streams}), stderr="")
        if command[0] == "ffmpeg":
            source = Path(command[command.index("-i") + 1])
            target = Path(command[-1])
            target.write_bytes(source.read_bytes() + b"-remuxed")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected media command: {command}")

    return runner, commands


def normal_streams() -> list[dict[str, object]]:
    return [
        {"index": 0, "codec_name": "h264", "codec_type": "video"},
        {"index": 1, "codec_name": "aac", "codec_type": "audio"},
    ]


def iphone_streams() -> list[dict[str, object]]:
    return normal_streams() + [
        {"index": 2, "codec_type": "data"},
        {"index": 3, "codec_type": "data"},
        {"index": 4, "codec_type": "data"},
        {"index": 5, "codec_type": "data"},
        {"index": 6, "codec_type": "data"},
    ]


def test_prepare_project_uploads_inputs_then_manifest_and_waits_for_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_a = tmp_path / "opening.mp4"
    source_b = tmp_path / "ending.mp4"
    source_a.write_bytes(b"opening")
    source_b.write_bytes(b"ending")
    stage_root = tmp_path / "staging"
    monkeypatch.setattr(project, "STAGING_ROOT", stage_root)
    monkeypatch.setattr(project, "collect_timeline_sources", lambda name: (tmp_path, [source_a, source_b]))
    monkeypatch.setattr(project, "create_security_pass", fake_security)
    commands: list[list[str]] = []
    media_runner, _ = media_runner_for({"opening.mp4": normal_streams(), "ending.mp4": normal_streams()})

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    store = HandoffStore(tmp_path / "handoff")
    prepared = project.prepare_project(
        store, "demo", "preview", runner=runner, media_runner=media_runner, now=1000
    )

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
    assert (prepared.staging_dir / "NORMALIZATION_REPORT.json").is_file()
    assert (prepared.staging_dir / "manifest.json").is_file()


def test_prepare_project_rolls_back_request_when_manifest_upload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "opening.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(project, "STAGING_ROOT", tmp_path / "staging")
    monkeypatch.setattr(project, "collect_timeline_sources", lambda name: (tmp_path, [source]))
    monkeypatch.setattr(project, "create_security_pass", fake_security)
    media_runner, _ = media_runner_for({"opening.mp4": normal_streams()})
    calls = 0

    def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.CalledProcessError(1, command, stderr="manifest upload failed")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    store = HandoffStore(tmp_path / "handoff")
    with pytest.raises(HandoffError, match="manifest upload failed"):
        project.prepare_project(
            store, "demo", "final", runner=runner, media_runner=media_runner, now=1000
        )
    assert list((tmp_path / "handoff").glob("*.json")) == []


def test_stage_ascii_inputs_renames_non_ascii_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "動画素材.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(project, "STAGING_ROOT", tmp_path / "staging")
    media_runner, _ = media_runner_for({"動画素材.mp4": normal_streams()})
    stage, staged = project.stage_ascii_inputs("demo", [source], "run-1", media_runner=media_runner)
    assert stage.is_dir()
    assert staged[0].name == "input-001.mp4"
    assert staged[0].read_bytes() == b"video"


def test_stage_ascii_inputs_remuxes_iphone_data_streams_without_mutating_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "iphone.mov"
    source.write_bytes(b"original")
    monkeypatch.setattr(project, "STAGING_ROOT", tmp_path / "staging")
    media_runner, commands = media_runner_for({"iphone.mov": iphone_streams()})

    stage, staged = project.stage_ascii_inputs("demo", [source], "run-2", media_runner=media_runner)

    assert source.read_bytes() == b"original"
    assert staged[0].name == "input-001.mp4"
    assert staged[0].read_bytes() == b"original-remuxed"
    ffmpeg = next(command for command in commands if command[0] == "ffmpeg")
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:v:0"
    assert "0:a:0?" in ffmpeg
    assert "-c" in ffmpeg and "copy" in ffmpeg
    report = json.loads((stage / "NORMALIZATION_REPORT.json").read_text())
    assert report["inputs"][0]["method"] == "remux"
    assert report["inputs"][0]["before"]["data"] == 5
    assert report["inputs"][0]["after"] == {"video": 1, "audio": 1}
    assert report["inputs"][0]["removed_streams"] == 5


def test_normalization_rejects_multiple_video_streams(tmp_path: Path) -> None:
    source = tmp_path / "multi.mov"
    source.write_bytes(b"video")
    runner, _ = media_runner_for(
        {
            "multi.mov": [
                {"index": 0, "codec_type": "video"},
                {"index": 1, "codec_type": "video"},
            ]
        }
    )
    with pytest.raises(HandoffError, match="exactly one video"):
        project.normalize_cloud_input(source, tmp_path / "output", runner=runner)
