from pathlib import Path


RETURN_FIX = Path(
    "web_console/static/timed-narration-return-fix.js"
).read_text(encoding="utf-8")
APP_V5 = Path("web_console/app_v5.py").read_text(encoding="utf-8")


def test_saved_return_removes_pointer_event_lock() -> None:
    assert "classList.remove('saving-lock')" in RETURN_FIX
    assert "style.pointerEvents = 'auto'" in RETURN_FIX
    assert "removeAttribute('aria-disabled')" in RETURN_FIX


def test_saved_return_navigates_directly_to_composition() -> None:
    assert "window.location.assign(returnUrl)" in RETURN_FIX
    assert "../?project=${encodeURIComponent(projectName)}" in RETURN_FIX


def test_return_fix_is_injected_after_narration_controllers() -> None:
    finish_index = APP_V5.index("timed-narration-finish.js")
    overlay_index = APP_V5.index("timed-narration-recording-overlay.js")
    return_index = APP_V5.index("timed-narration-return-fix.js")
    assert finish_index < overlay_index < return_index
