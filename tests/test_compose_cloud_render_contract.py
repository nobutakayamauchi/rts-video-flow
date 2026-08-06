from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / "web_console" / "static" / "compose-cloud-render.js").read_text(encoding="utf-8")
OVERLAY = (ROOT / "web_console" / "static" / "rts-progress-overlay.js").read_text(encoding="utf-8")
APP_V5 = (ROOT / "web_console" / "app_v5.py").read_text(encoding="utf-8")


def test_compose_controller_uses_governed_cloud_render_sequence() -> None:
    flow_start = CONTROLLER.index("async function cloudRender(mode)")
    flow_end = CONTROLLER.index("function delegatedActivation", flow_start)
    flow = CONTROLLER[flow_start:flow_end]

    prepare = flow.index("api/cloud-render/prepare-project")
    approve = flow.index("api/cloud-render/approve")
    dispatch = flow.index("api/cloud-render/dispatch")
    poll = flow.index("await pollStatus")
    assert prepare < approve < dispatch < poll
    assert "api/output/render" not in CONTROLLER


def test_compose_controller_requires_explicit_single_use_confirmation() -> None:
    assert "window.confirm" in CONTROLLER
    assert "estimated_max_yen" in CONTROLLER
    assert "confirmation" in CONTROLLER
    assert "承認はこの1回だけ有効" in CONTROLLER


def test_compose_controller_prevents_duplicate_taps_and_polls_status() -> None:
    assert "let busy = false" in CONTROLLER
    assert "if (busy)" in CONTROLLER
    assert "document.addEventListener('pointerup', delegatedActivation, true)" in CONTROLLER
    assert "document.addEventListener('touchend', delegatedActivation" in CONTROLLER
    assert "document.addEventListener('click', delegatedActivation, true)" in CONTROLLER
    assert "window.setTimeout(() => pollStatus" in CONTROLLER
    assert "event.stopImmediatePropagation()" in CONTROLLER
    assert "同じ処理を重複して開始しません" in CONTROLLER


def test_compose_controller_reports_acceptance_and_progress_in_overlay() -> None:
    assert "window.RTSProgressOverlay" in CONTROLLER
    assert "✓ 受け付けました" in CONTROLLER
    assert "progress()?.update" in CONTROLLER
    assert "progress()?.finish" in CONTROLLER
    assert "progress()?.fail" in CONTROLLER


def test_compose_controller_reconnects_transport_failures_without_unlocking_duplicate_render() -> None:
    assert "function isConnectionError" in CONTROLLER
    assert "function scheduleReconnect" in CONTROLLER
    assert "state: 'reconnecting'" in CONTROLLER
    assert "今すぐ再接続" in CONTROLLER
    assert "pollTimer = window.setTimeout(() => pollStatus" in CONTROLLER
    assert "画面操作やタブ移動は可能です" in CONTROLLER
    assert "function renderButtons()" in CONTROLLER
    render_buttons = CONTROLLER[CONTROLLER.index("function renderButtons()") : CONTROLLER.index("function setBusy", CONTROLLER.index("function renderButtons()"))]
    assert "#apply" not in render_buttons


def test_shared_overlay_is_fixed_following_nonblocking_and_detects_stalls() -> None:
    assert "position: fixed" in OVERLAY
    assert "env(safe-area-inset-bottom)" in OVERLAY
    assert "aria-live" in OVERLAY
    assert ".rts-progress-overlay.visible" in OVERLAY
    assert "pointer-events: none" in OVERLAY
    assert ".rts-progress-action" in OVERLAY
    assert "pointer-events: auto" in OVERLAY
    assert "silentFor >= 30000" in OVERLAY
    assert "silentFor >= 120000" in OVERLAY
    assert "elapsed.textContent" in OVERLAY
    assert "updated.textContent" in OVERLAY
    assert "window.RTSProgressOverlay = {show, update, finish, fail, setAction, setStep}" in OVERLAY


def test_app_v5_injects_overlay_before_governed_compose_controller() -> None:
    overlay = APP_V5.index('rts-progress-overlay.js?v=20260806a')
    controller = APP_V5.index('compose-cloud-render.js?v=20260806b')
    assert overlay < controller
    assert "compose-controls-recovery|compose-cloud-render|rts-progress-overlay" in APP_V5
    assert 'COMPOSE_CONTROL_TAGS = ""' not in APP_V5
