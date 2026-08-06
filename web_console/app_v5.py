#!/usr/bin/env python3
"""V5 web entry point with governed cloud-render handoff."""
from __future__ import annotations

import re

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from web_console.app import STATIC_DIR
from web_console.app_v4 import app
from web_console.cloud_render_api import router as cloud_render_router
from web_console import app_v3 as legacy

FLIGHT_RECORDER_TAG = '<script src="/static/rts-flight-recorder.js?v=20260806a"></script>'
FLIGHT_RECORDER_RE = re.compile(
    r'<script\s+src=["\'](?:/static/|static/)?rts-flight-recorder\.js(?:\?[^"\']*)?["\']\s*></script>\s*',
    flags=re.IGNORECASE,
)
TIMED_NARRATION_TAGS = (
    FLIGHT_RECORDER_TAG,
    '<script src="timed-narration-finish.js?v=20260805b"></script>',
    '<script src="timed-narration-recording-overlay.js?v=20260805b"></script>',
    '<script src="timed-narration-visibility-fix.js?v=20260805b"></script>',
    '<script src="timed-narration-return-fix.js?v=20260805b"></script>',
)
TIMED_NARRATION_SCRIPT_RE = re.compile(
    r'<script\s+src=["\']timed-narration-(?:finish|recording-overlay|visibility-fix|return-fix)\.js(?:\?[^"\']*)?["\']\s*></script>\s*',
    flags=re.IGNORECASE,
)
COMPOSE_CONTROL_TAGS = (
    FLIGHT_RECORDER_TAG,
    '<script src="static/rts-progress-overlay.js?v=20260806a"></script>',
    '<script src="static/compose-cloud-render.js?v=20260806b"></script>',
)
OUTPUT_CONTROL_TAGS = (
    FLIGHT_RECORDER_TAG,
    '<script src="rts-progress-overlay.js?v=20260806a"></script>',
    '<script src="compose-cloud-render.js?v=20260806b"></script>',
    '<script src="output-review-flow.js?v=20260806e"></script>',
)
COMPOSE_CONTROL_RE = re.compile(
    r'<script\s+src=["\'](?:static/)?(?:compose-controls-recovery|compose-cloud-render|rts-progress-overlay|output-review-flow)\.js(?:\?[^"\']*)?["\']\s*></script>\s*',
    flags=re.IGNORECASE,
)


def reject_local_render(project_name: str, mode: str):
    """Fail closed instead of OOM-killing the Oracle web service."""
    raise HTTPException(
        status_code=503,
        detail=(
            "Oracle上でのローカル書き出しは、メモリ不足による停止を防ぐため無効化しました。"
            "RTS 3.5のSecurity Gate・Cost Gate・Cloud Run経路から実行してください。"
        ),
    )


legacy.run_render = reject_local_render
app.include_router(cloud_render_router)


def uncached_html(html: str) -> HTMLResponse:
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


def inject_scripts(html: str, tags: tuple[str, ...], cleanup: re.Pattern[str] | None = None) -> str:
    """Inject one canonical recorder/controller set before </body>."""
    html = FLIGHT_RECORDER_RE.sub("", html)
    if cleanup is not None:
        html = cleanup.sub("", html)
    injected = "\n".join(tags)
    return html.replace("</body>", f"{injected}\n</body>")


@app.middleware("http")
async def inject_mobile_interaction_controllers(request: Request, call_next):
    """Serve mobile editors uncached with one canonical controller set."""
    if request.method == "GET" and request.url.path == "/static/timed-narration.html":
        html = (STATIC_DIR / "timed-narration.html").read_text(encoding="utf-8")
        return uncached_html(inject_scripts(html, TIMED_NARRATION_TAGS, TIMED_NARRATION_SCRIPT_RE))

    if request.method == "GET" and request.url.path in {"/", "/static/compose.html"}:
        html = (STATIC_DIR / "compose.html").read_text(encoding="utf-8")
        return uncached_html(inject_scripts(html, COMPOSE_CONTROL_TAGS, COMPOSE_CONTROL_RE))

    if request.method == "GET" and request.url.path == "/static/output.html":
        html = (STATIC_DIR / "output.html").read_text(encoding="utf-8")
        return uncached_html(inject_scripts(html, OUTPUT_CONTROL_TAGS, COMPOSE_CONTROL_RE))

    return await call_next(request)
