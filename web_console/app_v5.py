#!/usr/bin/env python3
"""V5 web entry point with finished timed-narration interaction layers."""
from __future__ import annotations

import re

from fastapi import Request
from fastapi.responses import HTMLResponse

from web_console.app import STATIC_DIR
from web_console.app_v4 import app

TIMED_NARRATION_TAGS = (
    '<script src="timed-narration-finish.js?v=20260805b"></script>',
    '<script src="timed-narration-recording-overlay.js?v=20260805b"></script>',
    '<script src="timed-narration-visibility-fix.js?v=20260805b"></script>',
    '<script src="timed-narration-return-fix.js?v=20260805b"></script>',
)
TIMED_NARRATION_SCRIPT_RE = re.compile(
    r'<script\s+src=["\']timed-narration-(?:finish|recording-overlay|visibility-fix|return-fix)\.js(?:\?[^"\']*)?["\']\s*></script>\s*',
    flags=re.IGNORECASE,
)
COMPOSE_CONTROL_TAG = '<script src="static/compose-controls-recovery.js?v=20260805a"></script>'
COMPOSE_CONTROL_RE = re.compile(
    r'<script\s+src=["\'](?:static/)?compose-controls-recovery\.js(?:\?[^"\']*)?["\']\s*></script>\s*',
    flags=re.IGNORECASE,
)


@app.middleware("http")
async def inject_mobile_interaction_controllers(request: Request, call_next):
    """Serve mobile editors uncached with one canonical controller set."""
    if request.method == "GET" and request.url.path == "/static/timed-narration.html":
        html = (STATIC_DIR / "timed-narration.html").read_text(encoding="utf-8")
        # Remove stale or duplicate controller tags before injecting the current
        # set. iPhone Safari previously mixed old and new handlers after deploys.
        html = TIMED_NARRATION_SCRIPT_RE.sub("", html)
        injected = "\n".join(TIMED_NARRATION_TAGS)
        html = html.replace("</body>", f"{injected}\n</body>")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    if request.method == "GET" and request.url.path in {"/", "/static/compose.html"}:
        html = (STATIC_DIR / "compose.html").read_text(encoding="utf-8")
        html = COMPOSE_CONTROL_RE.sub("", html)
        html = html.replace("</body>", f"{COMPOSE_CONTROL_TAG}\n</body>")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    return await call_next(request)
