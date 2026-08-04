from pathlib import Path


OVERLAY_JS = Path(
    "web_console/static/timed-narration-recording-overlay.js"
).read_text(encoding="utf-8")
APP_V5 = Path("web_console/app_v5.py").read_text(encoding="utf-8")
DEPLOY = Path("scripts/deploy_symlink_aware_vlog_service.sh").read_text(
    encoding="utf-8"
)


def test_record_button_describes_video_guided_recording() -> None:
    assert "映像を見ながら録音" in OVERLAY_JS


def test_recording_uses_a_full_screen_safe_area_overlay() -> None:
    assert "#narrationRecordingOverlay.active" in OVERLAY_JS
    assert "position: fixed" in OVERLAY_JS
    assert "env(safe-area-inset-top)" in OVERLAY_JS
    assert "env(safe-area-inset-bottom)" in OVERLAY_JS
    assert "z-index: 2000" in OVERLAY_JS


def test_visual_clock_and_stop_button_move_into_overlay() -> None:
    assert "visualStage.appendChild(visualBox)" in OVERLAY_JS
    assert "top.append(heading, clock, help)" in OVERLAY_JS
    assert "bottom.append(stateText, stopButton)" in OVERLAY_JS


def test_video_starts_muted_from_zero_after_recorder_starts() -> None:
    assert "recorder?.state === 'recording'" in OVERLAY_JS
    assert "visual.currentTime = 0" in OVERLAY_JS
    assert "visual.muted = true" in OVERLAY_JS
    assert "await visual.play()" in OVERLAY_JS


def test_video_freezes_but_recording_is_not_auto_stopped_at_target() -> None:
    assert "freezeVisualAtEnd()" in OVERLAY_JS
    assert "visual.pause()" in OVERLAY_JS
    assert "映像終了後も録音は続き" in OVERLAY_JS


def test_stop_restores_normal_editor_layout() -> None:
    assert "restoreAtMarker(visualBox, visualMarker)" in OVERLAY_JS
    assert "restoreAtMarker(clock, clockMarker)" in OVERLAY_JS
    assert "restoreAtMarker(stopButton, stopMarker)" in OVERLAY_JS
    assert "document.body.classList.remove('narration-recording-active')" in OVERLAY_JS


def test_backgrounding_stops_microphone_recording() -> None:
    assert "document.addEventListener('visibilitychange'" in OVERLAY_JS
    assert "stopButton.click()" in OVERLAY_JS
    assert "画面を離れたため" in OVERLAY_JS


def test_server_and_deploy_include_overlay_controller() -> None:
    assert "timed-narration-recording-overlay.js" in APP_V5
    assert "timed-narration-recording-overlay.js" in DEPLOY
