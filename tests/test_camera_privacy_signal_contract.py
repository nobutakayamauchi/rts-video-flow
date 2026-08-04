from pathlib import Path


HTML = Path("web_console/static/new-vlog.html").read_text(encoding="utf-8")


def test_camera_requires_audible_signal_before_get_user_media() -> None:
    signal_call = HTML.index("await playPrivacySignal('cameraOpen')")
    media_call = HTML.index("navigator.mediaDevices.getUserMedia")
    assert signal_call < media_call


def test_camera_and_recording_have_distinct_signals() -> None:
    for name in ("cameraOpen", "recordStart", "recordStop", "cameraClose"):
        assert name in HTML
    assert "このアプリは撮影を隠す機能を提供しません" in HTML


def test_camera_use_is_visibly_persistent() -> None:
    assert 'id="cameraSafety"' in HTML
    assert "カメラ使用中" in HTML
    assert "録画中" in HTML
    assert 'id="endCamera"' in HTML


def test_background_and_navigation_stop_capture() -> None:
    assert "visibilitychange" in HTML
    assert "pagehide" in HTML
    assert "beforeunload" in HTML
    assert "emergencyStopCamera" in HTML
    assert "自動再開はしません" in HTML


def test_recording_cannot_start_without_explicit_camera_activation() -> None:
    assert 'id="startRecord" disabled' in HTML
    assert "先にインカメまたはアウトカメを起動してください" in HTML


def test_no_silent_camera_setting_is_exposed() -> None:
    forbidden = (
        "silentCamera",
        "disableCameraSound",
        "mutePrivacySignal",
        "cameraSoundOff",
    )
    assert not any(value in HTML for value in forbidden)
