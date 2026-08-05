from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from web_console.cloud_render_executor import build_execute_command, dispatch, parse_execution_name
from web_console.cloud_render_handoff import HandoffError, HandoffStore, RenderPolicy, SecurityBinding


def queued_store(tmp_path: Path) -> tuple[HandoffStore, dict]:
    store = HandoffStore(tmp_path / "state")
    pending = store.create_pending(
        project="demo",
        mode="preview",
        manifest_uri="gs://rts-vlog-render-files-20260805/manifests/demo.json",
        output_uri="gs://rts-vlog-render-files-20260805/outputs/demo/output.mp4",
        security=SecurityBinding(
            policy="rts-media-security-gate-v1",
            fingerprint="a" * 64,
            input_hashes=("b" * 64,),
            files=1,
        ),
        policy=RenderPolicy(),
        now=100,
    )
    queued = store.consume(
        pending["request_id"],
        confirmation=pending["confirmation"],
        now=101,
    )
    return store, queued


def test_command_is_bounded_to_one_async_job(tmp_path: Path) -> None:
    _, record = queued_store(tmp_path)
    command = build_execute_command(record)
    assert command[:5] == ("gcloud", "run", "jobs", "execute", "rts-vlog-render")
    assert "--tasks=1" in command
    assert "--task-timeout=10m" in command
    assert "--async" in command
    assert "--format=value(metadata.name)" in command
    env = next(value for value in command if value.startswith("--update-env-vars="))
    assert record["manifest_uri"] in env
    assert record["request_id"] in env


def test_dispatch_marks_execution_running(tmp_path: Path) -> None:
    store, record = queued_store(tmp_path)

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="rts-vlog-render-abc123\n", stderr="")

    result = dispatch(store, record["request_id"], runner=runner)
    assert result.execution == "rts-vlog-render-abc123"
    saved = store.read(record["request_id"])
    assert saved["status"] == "RUNNING"
    assert saved["execution"] == "rts-vlog-render-abc123"


def test_dispatch_failure_is_persisted(tmp_path: Path) -> None:
    store, record = queued_store(tmp_path)

    def runner(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="permission denied")

    with pytest.raises(HandoffError, match="dispatch failed"):
        dispatch(store, record["request_id"], runner=runner)
    saved = store.read(record["request_id"])
    assert saved["status"] == "FAILED"
    assert "permission denied" in saved["error"]


def test_nonqueued_request_cannot_dispatch(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path / "state")
    pending = store.create_pending(
        project="demo",
        mode="final",
        manifest_uri="gs://rts-vlog-render-files-20260805/manifests/demo.json",
        output_uri="gs://rts-vlog-render-files-20260805/outputs/demo/output.mp4",
        security=SecurityBinding(
            policy="rts-media-security-gate-v1",
            fingerprint="a" * 64,
            input_hashes=("b" * 64,),
            files=1,
        ),
        policy=RenderPolicy(),
    )
    with pytest.raises(HandoffError, match="not queued"):
        build_execute_command(pending)


def test_execution_name_parser_accepts_full_resource() -> None:
    value = "projects/p/locations/asia-northeast1/jobs/j/executions/rts-vlog-render-xyz\n"
    assert parse_execution_name(value) == "rts-vlog-render-xyz"
