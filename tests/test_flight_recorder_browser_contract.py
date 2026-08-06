from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SDK = (ROOT / "web_console/static/rts-flight-recorder.js").read_text(encoding="utf-8")


def test_browser_sdk_is_singleton_and_exposes_public_api():
    assert "if (window.RTSFlightRecorder) return" in SDK
    assert "window.RTSFlightRecorder =" in SDK
    for name in ("record", "exportSession", "clear()", "stop()", "start(newSessionId)"):
        assert name in SDK


def test_browser_sdk_records_required_signal_families():
    for event_type in (
        "interaction",
        "navigation",
        "visibility",
        "js_error",
        "promise_rejection",
        "network",
        "api_result",
        "api_error",
        "session",
    ):
        assert f"'{event_type}'" in SDK


def test_browser_sdk_does_not_capture_form_values_or_response_bodies():
    forbidden = (
        ".value",
        "response.text(",
        "response.json(",
        "FormData(event.target)",
        "document.cookie",
        "localStorage",
        "sessionStorage",
    )
    for token in forbidden:
        assert token not in SDK


def test_browser_sdk_redacts_sensitive_keys_and_limits_evidence():
    assert "SENSITIVE_KEY" in SDK
    assert "[REDACTED]" in SDK
    assert "MAX_QUEUE = 500" in SDK
    assert "queue.shift()" in SDK
    assert "slice(0, 1000)" in SDK


def test_browser_sdk_preserves_monotonic_sequence_and_session_identity():
    assert "sequence: ++sequence" in SDK
    assert "session_id: sessionId" in SDK
    assert "event_id:" in SDK
    assert "recorded_at: new Date().toISOString()" in SDK


def test_browser_sdk_tracks_fetch_without_changing_return_or_error_semantics():
    assert "const response = await originalFetch(input, init)" in SDK
    assert "return response" in SDK
    assert "throw error" in SDK
    assert "performance.now()" in SDK


def test_browser_sdk_is_non_blocking_and_has_no_overlay_or_modal():
    for forbidden in ("preventDefault()", "stopPropagation()", "alert(", "confirm(", "position: fixed"):
        assert forbidden not in SDK
