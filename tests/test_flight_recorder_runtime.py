from __future__ import annotations

import pytest

from web_console.flight_recorder import (
    FlightRecorderSession,
    RecorderClosedError,
    redact,
)


def ticking_clock():
    values = iter(
        [
            "2026-08-06T12:00:00Z",
            "2026-08-06T12:00:01Z",
            "2026-08-06T12:00:02Z",
            "2026-08-06T12:00:03Z",
            "2026-08-06T12:00:04Z",
            "2026-08-06T12:00:05Z",
        ]
    )
    return lambda: next(values)


def test_session_starts_with_append_only_envelope():
    session = FlightRecorderSession(screen="compose", project="demo", clock=ticking_clock())
    first = session.events[0]
    assert first["event_type"] == "session_start"
    assert first["sequence"] == 1
    assert first["session_id"] == session.session_id
    assert first["event_id"] != session.session_id
    assert first["project"] == "demo"


def test_sequences_are_monotonic_and_step_is_validated():
    session = FlightRecorderSession(screen="compose", clock=ticking_clock())
    second = session.append("activation", payload={"action": "preview"}, step=(2, 7))
    third = session.append("api_success", request_id="req-1", step=(3, 7))
    assert [event["sequence"] for event in session.events] == [1, 2, 3]
    assert second["step"] == {"current": 2, "total": 7}
    assert third["request_id"] == "req-1"
    with pytest.raises(ValueError):
        session.append("step_changed", step=(8, 7))


def test_recursive_redaction_removes_forbidden_keys_and_values():
    cleaned = redact(
        {
            "authorization": "Bearer abc",
            "nested": {
                "cookie": "session=bad",
                "safe_url": "https://example.test/path?token=abc&mode=preview",
                "message": "failed with Bearer very-secret-token",
            },
            "items": [{"api_key": "bad"}, {"status": "ok"}],
        }
    )
    assert "authorization" not in cleaned
    assert "cookie" not in cleaned["nested"]
    assert "token=abc" not in cleaned["nested"]["safe_url"]
    assert "Bearer very-secret-token" not in cleaned["nested"]["message"]
    assert cleaned["items"] == [{}, {"status": "ok"}]


def test_queue_is_bounded_and_marks_evidence_gap():
    session = FlightRecorderSession(screen="compose", max_events=3, clock=ticking_clock())
    session.append("activation", payload={"number": 1})
    session.append("activation", payload={"number": 2})
    newest = session.append("activation", payload={"number": 3})
    assert len(session.events) == 3
    assert session.events[0]["event_type"] == "session_start"
    assert session.dropped_events == 1
    assert newest["payload"]["evidence_gap"]["dropped_events"] == 1
    assert [event["sequence"] for event in session.events] == [1, 3, 4]


def test_finalize_is_idempotent_and_closes_session():
    session = FlightRecorderSession(screen="compose", clock=ticking_clock())
    first_end = session.finalize(outcome="incident")
    second_end = session.finalize(outcome="ignored")
    assert first_end is second_end
    assert session.closed is True
    assert first_end["event_type"] == "session_end"
    assert first_end["payload"]["outcome"] == "incident"
    with pytest.raises(RecorderClosedError):
        session.append("activation")


def test_export_contains_no_mutable_internal_list_reference():
    session = FlightRecorderSession(screen="compose", clock=ticking_clock())
    exported = session.export()
    exported["events"].append({"fake": True})
    assert all("fake" not in event for event in session.events)
