#!/usr/bin/env python3
"""V5 web entry point with the finished timed-narration interaction layer."""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from web_console.app import STATIC_DIR
from web_console.app_v4 import app

TIMED_NARRATION_FINISH_TAG = (
    '<script src="timed-narration-finish.js?v=20260804a"></script>'
)


@app.middleware("http")
async def inject_timed_narration_finish(request: Request, call_next):
    """Serve the narration editor uncached with its completion controller."""
    if (
        request.method == "GET"
        and request.url.path == "/static/timed-narration.html"
    ):
        html = (STATIC_DIR / "timed-narration.html").read_text(encoding="utf-8")
        if TIMED_NARRATION_FINISH_TAG not in html:
            html = html.replace(
                "</body>", f"{TIMED_NARRATION_FINISH_TAG}\n</body>"
            )
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    return await call_next(request)
