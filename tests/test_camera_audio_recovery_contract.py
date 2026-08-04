from pathlib import Path


APP = Path("web_console/app_v4.py").read_text(encoding="utf-8")
RECOVERY = Path("web_console/static/camera-audio-recovery.js").read_text(
    encoding="utf-8"
)


def test_new_wizard_injects_recovery_script_without_cache() -> None:
    assert "camera-audio-recovery.js?v=20260804b" in APP
    assert "no-store, no-cache, must-revalidate" in APP
    assert "HTMLResponse" in APP


def test_camera_open_always_creates_a_fresh_audio_context() -> None:
    assert "if (kind === 'cameraOpen') return createFreshPrivacyAudioContext()" in RECOVERY
    assert "discardPrivacyAudioContext()" in RECOVERY
    assert "new AudioContextClass()" in RECOVERY


def test_backgrounding_discards_interrupted_audio_context() -> None:
    assert "visibilitychange" in RECOVERY
    assert "pagehide" in RECOVERY
    assert "if (document.hidden) discardPrivacyAudioContext()" in RECOVERY


def test_recovery_keeps_camera_gate_fail_closed() -> None:
    assert "throw new Error('撮影合図音を開始できません')" in RECOVERY
    assert "撮影合図音の再生処理が中断されました" in RECOVERY
