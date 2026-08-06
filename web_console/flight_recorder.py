from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import secrets
from typing import Any, Callable

_FORBIDDEN_KEY = re.compile(
    r"(authorization|cookie|password|passwd|token|secret|api[_-]?key|raw[_-]?text|media[_-]?bytes)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_URL_SECRET = re.compile(r"([?&](?:token|key|secret|signature|credential)=)[^&#\s]+", re.IGNORECASE)


class RecorderClosedError(RuntimeError):
    """Raised when an event is appended after finalization."""


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact(value: Any) -> Any:
    """Recursively remove forbidden fields and redact secret-like string values."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _FORBIDDEN_KEY.search(key_text):
                continue
            cleaned[key_text] = redact(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        text = _BEARER.sub("[REDACTED]", value)
        return _URL_SECRET.sub(r"\1[REDACTED]", text)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


@dataclass(slots=True)
class FlightRecorderSession:
    screen: str
    project: str | None = None
    max_events: int = 500
    clock: Callable[[], str] = _utc_now
    session_id: str = field(default_factory=lambda: _opaque_id("frs"))
    _events: list[dict[str, Any]] = field(default_factory=list, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _dropped_events: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.screen.strip():
            raise ValueError("screen is required")
        if self.max_events < 2:
            raise ValueError("max_events must be at least 2")
        self.append("session_start", payload={"recording": True})

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._events)

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    def append(
        self,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
        screen: str | None = None,
        request_id: str | None = None,
        execution_id: str | None = None,
        step: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        if self._closed:
            raise RecorderClosedError("flight recorder session is finalized")
        event_screen = (screen or self.screen).strip()
        if not event_screen:
            raise ValueError("screen is required")
        event: dict[str, Any] = {
            "version": 1,
            "event_id": _opaque_id("fre"),
            "session_id": self.session_id,
            "sequence": len(self._events) + self._dropped_events + 1,
            "occurred_at": self.clock(),
            "event_type": event_type,
            "screen": event_screen,
            "project": self.project,
            "request_id": request_id,
            "execution_id": execution_id,
            "step": None,
            "payload": redact(payload or {}),
        }
        if step is not None:
            current, total = step
            if current < 1 or total < 1 or current > total:
                raise ValueError("step must satisfy 1 <= current <= total")
            event["step"] = {"current": current, "total": total}
        if len(self._events) >= self.max_events:
            # Preserve session_start and the newest bounded evidence.
            self._events.pop(1)
            self._dropped_events += 1
            event["payload"]["evidence_gap"] = {
                "reason": "queue_limit",
                "dropped_events": self._dropped_events,
            }
        self._events.append(event)
        return event

    def finalize(self, *, outcome: str = "completed") -> dict[str, Any]:
        if self._closed:
            return self._events[-1]
        final_event = self.append(
            "session_end",
            payload={
                "outcome": outcome,
                "event_count": len(self._events) + 1,
                "dropped_events": self._dropped_events,
            },
        )
        self._closed = True
        return final_event

    def export(self) -> dict[str, Any]:
        return {
            "version": 1,
            "session_id": self.session_id,
            "project": self.project,
            "closed": self._closed,
            "dropped_events": self._dropped_events,
            "events": list(self._events),
        }
