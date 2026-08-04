#!/usr/bin/env python3
"""V5 web entry point with finished timed-narration interaction layers."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from web_console.app import STATIC_DIR
from web_console.app_v4 import app

TIMED_NARRATION_TAGS = (
    '<script src="timed-narration-finish.js?v=20260804a"></script>',
    '<script src="timed-narration-recording-overlay.js?v=20260804a"></script>',
)


@app.middleware("http")
async def inject_timed_narration_finish(request: Request, call_next):
    """Serve the narration editor uncached with its interaction controllers."""
    if (
        request.method == "GET"
        and request.url.path == "/static/timed-narration.html"
    ):
        html = (STATIC_DIR / "timed-narration.html").read_text(encoding="utf-8")
        missing_tags = [tag for tag in TIMED_NARRATION_TAGS if tag not in html]
        if missing_tags:
            html = html.replace("</body>", f"{'\n'.join(missing_tags)}\n</body>")
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    return await call_next(request)
