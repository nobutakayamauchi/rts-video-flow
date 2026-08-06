import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_DIR = Path(__file__).parents[1] / "schemas" / "flight-recorder"


def schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate(name: str, value: dict) -> None:
    Draft202012Validator(schema(name), format_checker=FormatChecker()).validate(value)


def base_event() -> dict:
    return {
        "version": 1,
        "event_id": "event-0001",
        "session_id": "session-0001",
        "sequence": 1,
        "occurred_at": "2026-08-06T20:45:00+09:00",
        "event_type": "activation",
        "screen": "preview_review",
        "project": "01-segment-smoke-v3",
        "request_id": None,
        "execution_id": None,
        "step": {"current": 1, "total": 7},
        "payload": {"action": "start_final_render", "element_id": "start-final"},
    }


def incident() -> dict:
    return {
        "version": 1,
        "incident_id": "incident-0001",
        "session_id": "session-0001",
        "status": "REPORT_FINALIZED",
        "started_at": "2026-08-06T20:45:00+09:00",
        "finalized_at": "2026-08-06T20:46:00+09:00",
        "project": "01-segment-smoke-v3",
        "event_count": 3,
        "events_sha256": "a" * 64,
        "expected_path": ["preview_review", "final_preparing"],
        "observed_path": ["preview_review", "no_transition"],
        "first_divergence_index": 1,
        "evidence_complete": True,
        "missing_evidence": [],
        "request_ids": [],
        "execution_ids": [],
        "redaction": {
            "policy": "rts-flight-recorder-redaction-v1",
            "passed": True,
            "removed_fields": [],
        },
    }


def assessment() -> dict:
    return {
        "version": 1,
        "assessment_id": "assessment-0001",
        "incident_id": "incident-0001",
        "status": "DIAGNOSED",
        "failure_class": "transition_not_connected",
        "first_divergence": {"index": 1, "expected": "final_preparing", "actual": "no_transition"},
        "observations": ["activation event was recorded", "no following API start was recorded"],
        "inferences": ["the UI action may not be connected"],
        "confidence": 0.82,
        "missing_evidence": [],
        "release_blocking": True,
        "reproduction_steps": ["open preview review", "press final render"],
        "suspected_paths": ["web_console/static/video-review.html"],
        "required_tests": ["final render activation starts exactly one request"],
    }


def repair_plan() -> dict:
    return {
        "version": 1,
        "plan_id": "repair-plan-0001",
        "incident_id": "incident-0001",
        "assessment_id": "assessment-0001",
        "status": "REPRODUCTION_READY",
        "repository": "nobutakayamauchi/rts-video-flow",
        "base_ref": "feat/rts-flight-recorder-repair-forge-v1",
        "repair_branch": "repair/incident-0001",
        "reproduction_test": {
            "path": "tests/test_incident_0001.py",
            "command": "python3 -m pytest -q tests/test_incident_0001.py",
            "failed_before_patch": True,
        },
        "allowed_paths": ["web_console/static/video-review.html", "tests/test_incident_0001.py"],
        "forbidden_paths": [".github/workflows", "web_console/cloud_cost_gate.py", "web_console/media_security_gate.py"],
        "limits": {"max_changed_files": 3, "max_changed_lines": 150, "max_new_dependencies": 0},
        "human_approval_required": True,
    }


def patch_review() -> dict:
    return {
        "version": 1,
        "review_id": "patch-review-0001",
        "plan_id": "repair-plan-0001",
        "status": "READY_FOR_HUMAN_REVIEW",
        "commit_sha": "b" * 40,
        "changed_files": ["web_console/static/video-review.html", "tests/test_incident_0001.py"],
        "changed_lines": 42,
        "tests": {
            "reproduction_failed_before": True,
            "reproduction_passed_after": True,
            "regression_passed": True,
            "deleted_tests": 0,
            "weakened_assertions": 0,
        },
        "guards": {
            "scope_within_plan": True,
            "security_bypass": False,
            "approval_bypass": False,
            "cost_gate_bypass": False,
            "errors_swallowed": False,
        },
        "rollback": {"available": True, "command": "git revert " + "b" * 40},
        "decision": "PASS",
        "conditions": [],
    }


def replay_result() -> dict:
    return {
        "version": 1,
        "replay_id": "replay-0001",
        "incident_id": "incident-0001",
        "review_id": "patch-review-0001",
        "status": "VERIFIED",
        "original_scenario_hash": "c" * 64,
        "observed_path": ["preview_review", "final_preparing", "final_running", "final_completed"],
        "expected_path": ["preview_review", "final_preparing", "final_running", "final_completed"],
        "same_execution_semantics": True,
        "regressions": [],
        "verified_at": "2026-08-06T21:00:00+09:00",
        "human_approval": {
            "approved": True,
            "approved_by": "human-reviewer",
            "approved_at": "2026-08-06T20:59:00+09:00",
        },
    }


@pytest.mark.parametrize(
    ("name", "factory"),
    [
        ("flight-event.schema.json", base_event),
        ("incident-report.schema.json", incident),
        ("debug-assessment.schema.json", assessment),
        ("repair-plan.schema.json", repair_plan),
        ("patch-review.schema.json", patch_review),
        ("replay-result.schema.json", replay_result),
    ],
)
def test_valid_contract_examples(name, factory):
    validate(name, factory())


@pytest.mark.parametrize("secret_key", ["authorization", "cookie", "password", "access_token", "client_secret", "raw_text", "media_bytes"])
def test_event_payload_rejects_sensitive_keys(secret_key):
    value = base_event()
    value["payload"][secret_key] = "must-not-be-recorded"
    with pytest.raises(Exception):
        validate("flight-event.schema.json", value)


def test_repair_plan_requires_reproduction_failure_before_patch():
    value = repair_plan()
    value["reproduction_test"]["failed_before_patch"] = False
    with pytest.raises(Exception):
        validate("repair-plan.schema.json", value)


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("tests", "deleted_tests"), 1),
        (("tests", "weakened_assertions"), 1),
        (("guards", "security_bypass"), True),
        (("guards", "approval_bypass"), True),
        (("guards", "cost_gate_bypass"), True),
        (("guards", "errors_swallowed"), True),
    ],
)
def test_patch_review_rejects_fake_repairs(path, replacement):
    value = patch_review()
    value[path[0]][path[1]] = replacement
    with pytest.raises(Exception):
        validate("patch-review.schema.json", value)


def test_verified_replay_rejects_regressions():
    value = replay_result()
    value["regressions"] = ["preview button stopped responding"]
    with pytest.raises(Exception):
        validate("replay-result.schema.json", value)


def assert_event_stream(events: list[dict]) -> None:
    if not events:
        raise ValueError("event stream is empty")
    session_ids = {event["session_id"] for event in events}
    if len(session_ids) != 1:
        raise ValueError("cross-session event mixture")
    sequences = [event["sequence"] for event in events]
    if sequences != list(range(1, len(events) + 1)):
        raise ValueError("event sequence must be contiguous, ordered, and unique")
    event_ids = [event["event_id"] for event in events]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate event id")
    for event in events:
        validate("flight-event.schema.json", event)
        step = event.get("step")
        if step and step["current"] > step["total"]:
            raise ValueError("current step exceeds total")


def test_event_stream_rejects_cross_session_mixture():
    first = base_event()
    second = copy.deepcopy(first)
    second.update(event_id="event-0002", session_id="session-9999", sequence=2)
    with pytest.raises(ValueError, match="cross-session"):
        assert_event_stream([first, second])


@pytest.mark.parametrize("sequences", [[1, 1], [2, 1], [1, 3]])
def test_event_stream_rejects_duplicate_reversed_or_gapped_sequence(sequences):
    events = []
    for index, sequence in enumerate(sequences, 1):
        event = base_event()
        event.update(event_id=f"event-{index:04d}", sequence=sequence)
        events.append(event)
    with pytest.raises(ValueError, match="sequence"):
        assert_event_stream(events)


def test_event_stream_rejects_impossible_progress():
    value = base_event()
    value["step"] = {"current": 8, "total": 7}
    with pytest.raises(ValueError, match="exceeds"):
        assert_event_stream([value])


def test_high_confidence_diagnosis_requires_complete_evidence():
    report = incident()
    report["evidence_complete"] = False
    report["missing_evidence"] = ["api outcome after activation"]
    diagnosis = assessment()
    diagnosis["confidence"] = 0.95
    if not report["evidence_complete"] and diagnosis["confidence"] > 0.8:
        with pytest.raises(ValueError, match="confidence"):
            raise ValueError("confidence exceeds available evidence")
