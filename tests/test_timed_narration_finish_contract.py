from pathlib import Path


FINISH_JS = Path("web_console/static/timed-narration-finish.js").read_text(
    encoding="utf-8"
)
APP_V5 = Path("web_console/app_v5.py").read_text(encoding="utf-8")
DEPLOY = Path("scripts/deploy_symlink_aware_vlog_service.sh").read_text(
    encoding="utf-8"
)


def test_finished_controller_is_injected_without_cache() -> None:
    assert "timed-narration-finish.js" in APP_V5
    assert 'request.url.path == "/static/timed-narration.html"' in APP_V5
    assert '"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"' in APP_V5
    assert "web_console.app_v5:app" in DEPLOY


def test_together_preview_stops_at_the_configured_target() -> None:
    assert "elapsed >= currentTarget()" in FINISH_JS
    assert "requestAnimationFrame(previewTick)" in FINISH_JS
    assert "audio?.pause()" in FINISH_JS
    assert "visualElement.pause()" in FINISH_JS
    assert "visualElement.currentTime = 0" in FINISH_JS
    assert "audio.currentTime = 0" in FINISH_JS


def test_short_and_long_narration_preview_messages_are_explicit() -> None:
    assert "超過した${delta.toFixed(1)}秒は再生していません" in FINISH_JS
    assert "最後の${(-delta).toFixed(1)}秒は無音として確認しました" in FINISH_JS


def test_save_is_guarded_against_double_submission() -> None:
    assert "saveInFlight || saved || !selectedFile" in FINISH_JS
    assert "saveInFlight = active" in FINISH_JS
    assert "二重送信を防ぐため" in FINISH_JS


def test_success_state_promotes_return_to_composition() -> None:
    assert "saveButton.textContent = '✓ 保存済み'" in FINISH_JS
    assert "skipLink.textContent = '構成へ戻る'" in FINISH_JS
    assert "skipLink.classList.add('saved-return')" in FINISH_JS
    assert "修正する場合は、構成画面からこの素材を開き直してください" in FINISH_JS


def test_success_state_locks_editing_controls() -> None:
    for control in (
        "startButton",
        "stopButton",
        "audioFileInput",
        "imageDurationInput",
        "discardButton",
        "playButton",
        "hintInput",
    ):
        assert control in FINISH_JS
    assert "element.disabled = true" in FINISH_JS
