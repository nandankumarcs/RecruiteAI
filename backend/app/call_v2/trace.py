"""Trace event foundation for call v2 runtime debugging."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from time import monotonic
from typing import Any
from uuid import uuid4


DEFAULT_REDACTED_KEYS = {
    "api_key",
    "api_token",
    "authorization",
    "auth_token",
    "password",
    "secret",
    "token",
}


def monotonic_ms() -> int:
    return int(monotonic() * 1000)


def _plain(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _plain(item) for key, item in asdict(value).items()}
    if isinstance(value, bytes):
        return {"encoding": "base64", "byte_length": len(value)}
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def redact(
    value: Any,
    *,
    redacted_keys: set[str] | None = None,
) -> Any:
    keys = redacted_keys or DEFAULT_REDACTED_KEYS
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            string_key = str(key)
            if string_key.lower() in keys:
                cleaned[string_key] = "[REDACTED]"
            else:
                cleaned[string_key] = redact(item, redacted_keys=keys)
        return cleaned
    if isinstance(value, list):
        return [redact(item, redacted_keys=keys) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class TraceEvent:
    trace_id: str
    event_type: str
    monotonic_ms: int
    call_id: str | None = None
    generation_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, redact_sensitive: bool = True) -> dict[str, Any]:
        payload = _plain(self)
        if redact_sensitive:
            payload = redact(payload)
        return payload


@dataclass(slots=True)
class TraceLogger:
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    events: list[TraceEvent] = field(default_factory=list)

    def emit(
        self,
        event_type: str,
        *,
        call_id: str | None = None,
        generation_id: int | None = None,
        data: dict[str, Any] | None = None,
        at_ms: int | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            trace_id=self.trace_id,
            event_type=event_type,
            monotonic_ms=at_ms if at_ms is not None else monotonic_ms(),
            call_id=call_id,
            generation_id=generation_id,
            data=data or {},
        )
        self.events.append(event)
        return event

    def to_list(self, *, redact_sensitive: bool = True) -> list[dict[str, Any]]:
        return [
            event.to_dict(redact_sensitive=redact_sensitive)
            for event in self.events
        ]
