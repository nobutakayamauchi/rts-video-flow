from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web_console" / "static"
COMPOSE = (STATIC / "compose-cloud-render.js").read_text(encoding="utf-8")
OUTPUT_REVIEW = (STATIC / "output-review-flow.js").read_text(encoding="utf-8")
VIDEO_REVIEW = (STATIC / "video-review.html").read_text(encoding="utf-8")
OVERLAY = (STATIC / "rts-progress-overlay.js").read_text(encoding="utf-8")


def test_preview_review_plays_inline_instead_of_opening_download_url() -> None:
    assert '<video id="player" controls playsinline' in VIDEO_REVIEW
    assert "const response=await fetch(source,{cache:'no-store'})" in VIDEO_REVIEW
    assert "URL.createObjectURL(blob)" in VIDEO_REVIEW
    assert "player.src=objectUrl" in VIDEO_REVIEW
    assert 'download=' not in VIDEO_REVIEW


def test_preview_review_final_action_is_a_real_button_with_single_accept_guard() -> None:
    assert '<button id="finalAction"' in VIDEO_REVIEW
    assert "if(finalAction.classList.contains('busy')) return" in VIDEO_REVIEW
    assert "finalAction.classList.add('busy')" in VIDEO_REVIEW
    assert "completed=preview&action=final" in VIDEO_REVIEW
    assert "finalAction.addEventListener('click',startFinal)" in VIDEO_REVIEW
    assert "finalAction.addEventListener('touchend',startFinal,{passive:false})" in VIDEO_REVIEW


def test_output_review_bridge_consumes_final_action_once_and_starts_final_render() -> None:
    assert "params.get('action') === 'final'" in OUTPUT_REVIEW
    assert "cleanUrl.searchParams.delete('action')" in OUTPUT_REVIEW
    assert "history.replaceState(null, '', cleanUrl)" in OUTPUT_REVIEW
    assert "window.setTimeout(() => finalButton.click(), 450)" in OUTPUT_REVIEW


def test_preview_and_final_outputs_have_distinct_user_actions() -> None:
    assert "プレビューを再生して確認" in OUTPUT_REVIEW
    assert "video-review.html?project=" in OUTPUT_REVIEW
    assert "保存先を選んで保存" in OUTPUT_REVIEW
    assert "api/download/" in OUTPUT_REVIEW


def test_cloud_render_reports_exact_stage_number_without_fake_percentage() -> None:
    assert "const TOTAL_STEPS = 7" in COMPOSE
    for step in range(1, 8):
        assert f"工程 {step}/7" in COMPOSE
    assert "totalSteps: TOTAL_STEPS" in COMPOSE
    assert "percentage" not in COMPOSE.lower()


def test_repeated_taps_cannot_dispatch_duplicate_cloud_jobs() -> None:
    assert "if (busy)" in COMPOSE
    assert "同じ処理を重複して開始しません" in COMPOSE
    assert "now - lastActivationAt < 900" in COMPOSE
    assert "event.stopImmediatePropagation()" in COMPOSE


def test_transport_failure_reconnects_without_false_job_failure() -> None:
    assert "function isConnectionError" in COMPOSE
    assert "load failed" in COMPOSE.lower()
    assert "function scheduleReconnect" in COMPOSE
    assert "state: 'reconnecting'" in COMPOSE
    assert "今すぐ再接続" in COMPOSE
    assert "Cloud Runの処理は継続中です" in COMPOSE


def test_completed_job_navigates_to_the_correct_review_state() -> None:
    assert "if (record.status === 'COMPLETED')" in COMPOSE
    assert "goToCompletedOutput(record.mode" in COMPOSE
    assert "completed', mode" in COMPOSE
    assert "request', requestId" in COMPOSE


def test_progress_overlay_does_not_globally_block_page_controls() -> None:
    assert "pointer-events: none" in OVERLAY
    assert ".rts-progress-action" in OVERLAY
    assert "pointer-events: auto" in OVERLAY
