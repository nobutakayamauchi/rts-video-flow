from pathlib import Path


RECOVERY_JS = Path("web_console/static/camera-audio-recovery.js").read_text(
    encoding="utf-8"
)


def test_camera_preview_uses_a_safe_area_overlay_frame() -> None:
    assert "#cameraPreviewFrame.active" in RECOVERY_JS
    assert "env(safe-area-inset-top)" in RECOVERY_JS
    assert "env(safe-area-inset-bottom)" in RECOVERY_JS
    assert "z-index: 1000" in RECOVERY_JS


def test_camera_state_is_shown_in_a_translucent_top_overlay() -> None:
    assert "topOverlay.id = 'cameraTopOverlay'" in RECOVERY_JS
    assert "background: rgba(12, 15, 20, 0.68)" in RECOVERY_JS
    assert "この表示はカメラ・撮影の終了後に消えます" in RECOVERY_JS
    assert "overlayHead.appendChild(safetyTitle)" in RECOVERY_JS
    assert "overlayHead.appendChild(safetyElapsed)" in RECOVERY_JS


def test_recording_controls_are_in_the_bottom_overlay() -> None:
    assert "bottomOverlay.id = 'cameraBottomOverlay'" in RECOVERY_JS
    assert "recordRow.append(startButton, stopButton)" in RECOVERY_JS
    assert "bottomOverlay.append(label, recordRow, endButton)" in RECOVERY_JS


def test_overlays_only_appear_while_camera_is_active() -> None:
    assert "document.body.classList.toggle('camera-active', active)" in RECOVERY_JS
    assert "frame.classList.toggle('active', active)" in RECOVERY_JS
    assert "setCameraLayoutActive(Boolean(state.stream))" in RECOVERY_JS
    assert "setCameraLayoutActive(false)" in RECOVERY_JS


def test_recorded_preview_returns_to_the_normal_page_after_capture() -> None:
    assert "const previewMarker = document.createComment('camera-preview-home')" in RECOVERY_JS
    assert "restorePreviewHome()" in RECOVERY_JS
    assert "previewMarker.parentNode.insertBefore(preview, previewMarker.nextSibling)" in RECOVERY_JS
