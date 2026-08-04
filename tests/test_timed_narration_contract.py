from pathlib import Path

import pytest
from fastapi import HTTPException

from web_console.app_v4 import narration_fit, safe_project_name


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "web_console" / "static"


def test_unicode_project_names_are_preserved() -> None:
    assert safe_project_name("テスト01") == "テスト01"
    assert safe_project_name("  Vlog テスト  ") == "Vlog-テスト"


def test_unsafe_empty_project_name_is_rejected() -> None:
    with pytest.raises(HTTPException):
        safe_project_name("../")


def test_narration_fit_states() -> None:
    assert narration_fit(12.0, 10.0) == "trim-tail"
    assert narration_fit(8.0, 10.0) == "pad-silence"
    assert narration_fit(10.02, 10.0) == "exact"


def test_timed_narration_page_exposes_countdown_and_manual_stop() -> None:
    page = (STATIC / "timed-narration.html").read_text(encoding="utf-8")
    assert "残り" in page
    assert "超過" in page
    assert "0秒を過ぎても自動停止しません" in page
    assert "映像と合わせて確認" in page
    assert "画像時間を録音時間に合わせる" in page


def test_new_vlog_routes_saved_material_to_audio_timing() -> None:
    page = (STATIC / "new-vlog.html").read_text(encoding="utf-8")
    assert "インカメを起動" in page
    assert "アウトカメを起動" in page
    assert "timed-narration.html" in page
