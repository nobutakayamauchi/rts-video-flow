from __future__ import annotations

import hashlib
import json
import subprocess

from web_console import cloud_render_reconcile
from web_console.cloud_render_handoff import HandoffStore, RenderPolicy, SecurityBinding


def running_record(tmp_path):
    store = HandoffStore(tmp_path / "handoff")
    digest = hashlib.sha256(b"input").hexdigest()
    record = store.create_pending(
        project="demo-project",
        mode="preview",
        manifest_uri="gs://bucket/manifests/demo.json",
        output_uri="gs://bucket/outputs/demo/output.mp4",
        security=SecurityBinding(
            policy="rts-media-security-gate-v1",
            fingerprint=hashlib.sha256(b"security").hexdigest(),
            input_hashes=(digest,),
            files=1,
        ),
        policy=RenderPolicy(),
        now=100,
    )
    store.consume(record["request_id"], confirmation=record["confirmation"], now=101)
    return store, store.mark_execution(record["request_id"], "render-execution-1")


def test_execution_outcome_understands_success_and_failure() -> None:
    assert cloud_render_reconcile.execution_outcome({"succeededCount": 1}) == "SUCCEEDED"
    assert cloud_render_reconcile.execution_outcome({"failedCount": 1}) == "FAILED"
    assert cloud_render_reconcile.execution_outcome({"conditions": []}) == "RUNNING"


def test_execution_outcome_understands_nested_gcloud_status() -> None:
    assert cloud_render_reconcile.execution_outcome(
        {"status": {"succeededCount": 1, "conditions": []}}
    ) == "SUCCEEDED"
    assert cloud_render_reconcile.execution_outcome(
        {
            "status": {
                "failedCount": 1,
                "conditions": [
                    {"type": "Completed", "status": "False", "message": "container failed"}
                ],
            }
        }
    ) == "FAILED"


def test_successful_execution_is_materialized_and_completed(tmp_path, monkeypatch) -> None:
    store, record = running_record(tmp_path)
    monkeypatch.setattr(cloud_render_reconcile, "OUTPUT_DIR", tmp_path / "output")

    def runner(command, **kwargs):
        if command[:4] == ["gcloud", "run", "jobs", "executions"]:
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"status": {"succeededCount": 1}}), ""
            )
        if command[:3] == ["gcloud", "storage", "ls"]:
            return subprocess.CompletedProcess(command, 0, record["output_uri"] + "\n", "")
        if command[:3] == ["gcloud", "storage", "cp"]:
            target = command[-1]
            with open(target, "wb") as handle:
                handle.write(b"video-data")
            return subprocess.CompletedProcess(command, 0, "copied", "")
        raise AssertionError(command)

    reconciled = cloud_render_reconcile.reconcile_active_record(store, record, runner=runner, now=200)

    assert reconciled["status"] == "COMPLETED"
    assert reconciled["error"] is None
    assert (tmp_path / "output" / "demo-project" / "preview.mp4").read_bytes() == b"video-data"


def test_failed_execution_is_persisted(tmp_path) -> None:
    store, record = running_record(tmp_path)

    def runner(command, **kwargs):
        payload = {
            "status": {
                "failedCount": 1,
                "conditions": [
                    {"type": "Completed", "status": "False", "message": "container failed"}
                ],
            }
        }
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    reconciled = cloud_render_reconcile.reconcile_active_record(store, record, runner=runner)

    assert reconciled["status"] == "FAILED"
    assert reconciled["error"] == "container failed"


def test_transient_cloud_lookup_failure_keeps_running(tmp_path) -> None:
    store, record = running_record(tmp_path)

    def runner(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="temporary failure")

    reconciled = cloud_render_reconcile.reconcile_active_record(store, record, runner=runner)
    assert reconciled["status"] == "RUNNING"
