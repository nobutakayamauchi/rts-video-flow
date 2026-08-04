from pathlib import Path


RECOVERY_JS = Path("web_console/static/camera-audio-recovery.js").read_text(
    encoding="utf-8"
)


def test_camera_preview_is_height_limited_on_mobile() -> None:
    assert "body.camera-active #preview" in RECOVERY_JS
    assert "max-height: min(38svh, 390px)" in RECOVERY_JS
    assert "max-height: 36svh" in RECOVERY_JS


def test_recording_controls_use_a_fixed_safe_area_dock() -> None:
    assert "#cameraControlDock" in RECOVERY_JS
    assert "position: fixed" in RECOVERY_JS
    assert "env(safe-area-inset-bottom)" in RECOVERY_JS
    assert "z-index: 1000" in RECOVERY_JS


def test_record_start_stop_and_camera_end_are_in_the_dock() -> None:
    assert "recordRow.append(startButton, stopButton)" in RECOVERY_JS
    assert "dock.append(label, recordRow, endButton)" in RECOVERY_JS


def test_dock_only_appears_while_camera_is_active() -> None:
    assert "document.body.classList.toggle('camera-active', active)" in RECOVERY_JS
    assert "dock.classList.toggle('hidden', !active)" in RECOVERY_JS
    assert "setCameraLayoutActive(Boolean(state.stream))" in RECOVERY_JS
    assert "setCameraLayoutActive(false)" in RECOVERY_JS
