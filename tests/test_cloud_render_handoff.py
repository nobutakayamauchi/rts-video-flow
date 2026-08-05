from __future__ import annotations

import json
from pathlib import Path

import pytest

from web_console.cloud_render_handoff import (
    HandoffError,
    HandoffStore,
    RenderPolicy,
    SecurityBinding,
    normalize_hashes,
)


HASH_A = "a" * 64
FINGERPRINT = "b" * 64


def binding() -> SecurityBinding:
    return SecurityBinding(
        policy="rts-media-security-gate-v1",
        fingerprint=FINGERPRINT,
        input_hashes=(HASH_A,),
        files=1,
    )


def create(store: HandoffStore, *, now: int = 100) -> dict:
    return store.create_pending(
        project="demo",
        mode="preview",
        manifest_uri="gs://bucket/manifests/run.json",
        output_uri="gs://bucket/outputs/run/output.mp4",
        security=binding(),
        policy=RenderPolicy(),
        now=now,
    )


def test_pending_request_is_integrity_bound_and_private(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    record = create(store)

    assert record["status"] == "AWAITING_APPROVAL"
    assert record["single_use"] is True
    assert record["confirmation"] == "3円上限で1回だけ実行"
    assert store.path_for(record["request_id"]).stat().st_mode & 0o777 == 0o600
    assert store.read(record["request_id"])["record_fingerprint"] == record["record_fingerprint"]


def test_request_can_be_consumed_only_once(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    pending = create(store)

    queued = store.consume(
        pending["request_id"],
        confirmation=pending["confirmation"],
        now=101,
    )
    assert queued["status"] == "QUEUED"
    assert queued["consumed_at"] == 101

    with pytest.raises(HandoffError, match="not awaiting approval|already consumed"):
        store.consume(
            pending["request_id"],
            confirmation=pending["confirmation"],
            now=102,
        )


def test_expired_or_wrong_confirmation_is_rejected(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    pending = create(store)

    with pytest.raises(HandoffError, match="confirmation"):
        store.consume(pending["request_id"], confirmation="YES", now=101)

    with pytest.raises(HandoffError, match="expired"):
        store.consume(
            pending["request_id"],
            confirmation=pending["confirmation"],
            now=pending["expires_at"] + 1,
        )


def test_execution_and_completion_follow_governed_states(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    pending = create(store)
    store.consume(pending["request_id"], confirmation=pending["confirmation"], now=101)

    running = store.mark_execution(pending["request_id"], "rts-vlog-render-abc")
    assert running["status"] == "RUNNING"
    assert running["execution"] == "rts-vlog-render-abc"

    completed = store.finish(pending["request_id"], success=True)
    assert completed["status"] == "COMPLETED"
    assert completed["error"] is None

    with pytest.raises(HandoffError, match="not active"):
        store.finish(pending["request_id"], success=True)


def test_tampered_record_is_rejected(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    pending = create(store)
    path = store.path_for(pending["request_id"])
    data = json.loads(path.read_text(encoding="utf-8"))
    data["policy"]["estimated_max_yen"] = 999
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(HandoffError, match="integrity"):
        store.read(pending["request_id"])


def test_security_binding_and_hashes_are_strict(tmp_path: Path) -> None:
    store = HandoffStore(tmp_path)
    with pytest.raises(HandoffError, match="security binding"):
        store.create_pending(
            project="demo",
            mode="final",
            manifest_uri="gs://bucket/m.json",
            output_uri="gs://bucket/o.mp4",
            security=SecurityBinding(
                policy="rts-media-security-gate-v1",
                fingerprint=FINGERPRINT,
                input_hashes=(HASH_A,),
                files=2,
            ),
            policy=RenderPolicy(),
        )

    assert normalize_hashes([HASH_A.upper(), HASH_A]) == (HASH_A,)
    with pytest.raises(HandoffError, match="invalid input hash"):
        normalize_hashes(["not-a-hash"])
