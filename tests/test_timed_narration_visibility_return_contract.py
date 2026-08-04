from pathlib import Path


VISIBILITY_JS = Path(
    "web_console/static/timed-narration-visibility-fix.js"
).read_text(encoding="utf-8")
RETURN_JS = Path("web_console/static/timed-narration-return-fix.js").read_text(
    encoding="utf-8"
)
APP_V5 = Path("web_console/app_v5.py").read_text(encoding="utf-8")
DEPLOY = Path("scripts/deploy_symlink_aware_vlog_service.sh").read_text(
    encoding="utf-8"
)


def test_visual_timer_and_stop_stay_in_normal_editor_before_recording() -> None:
    assert "restoreNormalEditor();" in VISIBILITY_JS
    assert "timed-narration-visual-home" in VISIBILITY_JS
    assert "timed-narration-clock-home" in VISIBILITY_JS
    assert "timed-narration-stop-home" in VISIBILITY_JS


def test_controls_move_to_overlay_only_on_explicit_start_tap() -> None:
    assert "moveControlsIntoRecordingOverlay" in VISIBILITY_JS
    assert "startButton.addEventListener('click'" in VISIBILITY_JS
    assert "{capture: true}" in VISIBILITY_JS


def test_saved_return_button_cannot_keep_pointer_events_disabled() -> None:
    assert "#skip.saved-return" in RETURN_JS
    assert "pointer-events: auto !important" in RETURN_JS
    assert "classList.remove('saving-lock')" in RETURN_JS
    assert "window.location.href = returnUrl" in RETURN_JS


def test_server_and_deploy_include_both_hotfix_scripts() -> None:
    for name in (
        "timed-narration-visibility-fix.js",
        "timed-narration-return-fix.js",
    ):
        assert name in APP_V5
        assert name in DEPLOY
    assert "v=20260805a" in APP_V5
