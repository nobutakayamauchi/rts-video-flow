from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = (ROOT / "web_console" / "static" / "compose-cloud-render.js").read_text(encoding="utf-8")
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
    assert "if (busy) return" in CONTROLLER
    assert "document.addEventListener('pointerup', delegatedActivation, true)" in CONTROLLER
    assert "document.addEventListener('touchend', delegatedActivation" in CONTROLLER
    assert "document.addEventListener('click', delegatedActivation, true)" in CONTROLLER
    assert "window.setTimeout(() => pollStatus" in CONTROLLER
    assert "event.stopImmediatePropagation()" in CONTROLLER


def test_app_v5_injects_only_the_governed_compose_controller() -> None:
    assert 'compose-cloud-render.js?v=20260805c' in APP_V5
    assert "compose-controls-recovery|compose-cloud-render" in APP_V5
    assert 'COMPOSE_CONTROL_TAG = ""' not in APP_V5
