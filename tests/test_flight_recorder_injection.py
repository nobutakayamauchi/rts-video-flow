from pathlib import Path


APP = Path("web_console/app_v5.py").read_text(encoding="utf-8")


def test_flight_recorder_is_injected_before_compose_controller():
    recorder = APP.index('/static/rts-flight-recorder.js?v=20260806a')
    overlay = APP.index('static/rts-progress-overlay.js?v=20260806a')
    compose = APP.index('static/compose-cloud-render.js?v=20260806b')
    assert recorder < overlay < compose


def test_flight_recorder_is_injected_into_all_governed_mobile_pages():
    assert 'TIMED_NARRATION_TAGS = (\n    FLIGHT_RECORDER_TAG,' in APP
    assert 'COMPOSE_CONTROL_TAGS = (\n    FLIGHT_RECORDER_TAG,' in APP
    assert 'OUTPUT_CONTROL_TAGS = (\n    FLIGHT_RECORDER_TAG,' in APP
    assert '/static/timed-narration.html' in APP
    assert '/static/compose.html' in APP
    assert '/static/output.html' in APP


def test_injection_removes_old_recorder_tags_before_adding_canonical_tag():
    assert 'FLIGHT_RECORDER_RE.sub("", html)' in APP
    assert 'return html.replace("</body>", f"{injected}\\n</body>")' in APP


def test_injected_pages_are_served_uncached():
    assert 'Cache-Control' in APP
    assert 'no-store, no-cache, must-revalidate, max-age=0' in APP
    assert 'Pragma' in APP
    assert 'no-cache' in APP


def test_flight_recorder_static_asset_exists():
    recorder = Path("web_console/static/rts-flight-recorder.js")
    assert recorder.exists()
    text = recorder.read_text(encoding="utf-8")
    assert 'window.RTSFlightRecorder' in text
    assert "record('session'" in text
