"""Persistence contracts and stores for call v2 sessions."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.call_v2.events import CallIdentity, TimestampMetadata, TranscriptTurnCommitted
from app.database import async_session_factory
from app.models import Call
from app.models.call_message import CallMessage


@dataclass(frozen=True, slots=True)
class PersistedTurn:
    generation_id: int | None
    role: Literal["user", "assistant"]
    message_id: str
    text: str
    committed_at_ms: int


TerminalStatus = Literal["completed", "failed", "no_answer", "busy", "cancelled"]
TERMINAL_STATUSES = {"completed", "failed", "no_answer", "busy", "cancelled"}
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class CallPersistence(Protocol):
    async def mark_call_started(
        self,
        *,
        identity: CallIdentity,
        started_at_ms: int,
    ) -> None:
        """Persist that the media stream has started."""

    async def commit_transcript_turn(
        self,
        *,
        generation_id: int | None,
        role: Literal["user", "assistant"],
        text: str,
        committed_at_ms: int,
    ) -> TranscriptTurnCommitted:
        """Persist one transcript turn exactly once."""

    async def record_latency_metric(
        self,
        *,
        name: str,
        value_ms: int | float,
        generation_id: int | None = None,
    ) -> None:
        """Persist one latency metric."""

    async def record_cost_metric(
        self,
        *,
        name: str,
        amount_usd: int | float,
    ) -> None:
        """Persist one cost metric."""

    async def mark_call_ended(
        self,
        *,
        ended_at_ms: int,
        reason: str,
        status: TerminalStatus = "completed",
    ) -> None:
        """Persist terminal call state."""


@dataclass(slots=True)
class FakeCallPersistence:
    turns: list[PersistedTurn] = field(default_factory=list)
    _message_index: int = 1
    _committed_index: dict[str, str] = field(default_factory=dict)
    status: str = "pending"
    started_at_ms: int | None = None
    ended_at_ms: int | None = None
    duration_seconds: int | None = None
    latency_metrics: dict = field(default_factory=dict)
    cost_breakdown: dict = field(default_factory=dict)

    async def mark_call_started(
        self,
        *,
        identity: CallIdentity,
        started_at_ms: int,
    ) -> None:
        self.status = "in_progress"
        self.started_at_ms = started_at_ms

    async def commit_transcript_turn(
        self,
        *,
        generation_id: int | None,
        role: Literal["user", "assistant"],
        text: str,
        committed_at_ms: int,
    ) -> TranscriptTurnCommitted:
        fingerprint = _text_fingerprint(text)
        idempotency_key = _turn_idempotency_key(
            generation_id=generation_id,
            role=role,
            text_fingerprint=fingerprint,
        )
        existing_message_id = self._committed_index.get(idempotency_key)
        if existing_message_id is not None:
            return TranscriptTurnCommitted(
                type="persistence.transcript_turn_committed",
                generation_id=generation_id,
                role=role,
                message_id=existing_message_id,
                text_fingerprint=fingerprint,
                timestamps=TimestampMetadata(backend_received_at_ms=committed_at_ms),
            )

        message_id = f"msg-{self._message_index}"
        self._message_index += 1
        self._committed_index[idempotency_key] = message_id
        self.turns.append(
            PersistedTurn(
                generation_id=generation_id,
                role=role,
                message_id=message_id,
                text=text,
                committed_at_ms=committed_at_ms,
            )
        )
        return TranscriptTurnCommitted(
            type="persistence.transcript_turn_committed",
            generation_id=generation_id,
            role=role,
            message_id=message_id,
            text_fingerprint=fingerprint,
            timestamps=TimestampMetadata(backend_received_at_ms=committed_at_ms),
        )

    async def record_latency_metric(
        self,
        *,
        name: str,
        value_ms: int | float,
        generation_id: int | None = None,
    ) -> None:
        _record_latency_metric(
            self.latency_metrics,
            name=name,
            value_ms=value_ms,
            generation_id=generation_id,
        )

    async def record_cost_metric(
        self,
        *,
        name: str,
        amount_usd: int | float,
    ) -> None:
        _record_cost_metric(self.cost_breakdown, name=name, amount_usd=amount_usd)

    async def mark_call_ended(
        self,
        *,
        ended_at_ms: int,
        reason: str,
        status: TerminalStatus = "completed",
    ) -> None:
        self.ended_at_ms = ended_at_ms
        if self.started_at_ms is not None:
            self.duration_seconds = max(
                0,
                int((ended_at_ms - self.started_at_ms) / 1000),
            )
        if self.status not in TERMINAL_STATUSES:
            self.status = status


@dataclass(slots=True)
class SqlAlchemyCallPersistence:
    """Persist confirmed v2 call state to the existing calls tables."""

    call_id: uuid.UUID | str
    session_factory: SessionFactory = async_session_factory
    _started_at_ms: int | None = None

    async def mark_call_started(
        self,
        *,
        identity: CallIdentity,
        started_at_ms: int,
    ) -> None:
        self._started_at_ms = started_at_ms
        async with self.session_factory() as session:
            call = await session.get(Call, self._uuid_call_id())
            if call is None:
                raise ValueError(f"call not found: {self.call_id}")
            if call.status not in TERMINAL_STATUSES:
                call.status = "in_progress"
            call.provider = identity.provider
            if identity.provider_call_id:
                call.provider_call_id = identity.provider_call_id
            if call.started_at is None:
                call.started_at = _utc_now()
            await session.commit()

    async def commit_transcript_turn(
        self,
        *,
        generation_id: int | None,
        role: Literal["user", "assistant"],
        text: str,
        committed_at_ms: int,
    ) -> TranscriptTurnCommitted:
        cleaned = _clean_text(text)
        if not cleaned:
            raise ValueError("cannot persist an empty transcript turn")
        fingerprint = _text_fingerprint(cleaned)
        idempotency_key = _turn_idempotency_key(
            generation_id=generation_id,
            role=role,
            text_fingerprint=fingerprint,
        )

        async with self.session_factory() as session:
            call = await session.get(Call, self._uuid_call_id())
            if call is None:
                raise ValueError(f"call not found: {self.call_id}")

            metrics = dict(call.latency_metrics or {})
            v2_metrics = dict(metrics.get("call_v2") or {})
            committed_turns = dict(v2_metrics.get("committed_turns") or {})
            existing = committed_turns.get(idempotency_key)
            if existing is not None:
                return TranscriptTurnCommitted(
                    type="persistence.transcript_turn_committed",
                    generation_id=generation_id,
                    role=role,
                    message_id=str(existing["message_id"]),
                    text_fingerprint=fingerprint,
                    timestamps=TimestampMetadata(
                        backend_received_at_ms=committed_at_ms
                    ),
                )

            last_sequence = await session.scalar(
                select(func.max(CallMessage.sequence_number)).where(
                    CallMessage.call_id == call.id
                )
            )
            message = CallMessage(
                call_id=call.id,
                role=role,
                content=cleaned,
                sequence_number=(last_sequence or 0) + 1,
            )
            session.add(message)
            await session.flush()

            call.transcript = _append_transcript_line(
                call.transcript,
                role=role,
                text=cleaned,
            )
            committed_turns[idempotency_key] = {
                "message_id": str(message.id),
                "generation_id": generation_id,
                "role": role,
                "text_fingerprint": fingerprint,
                "committed_at_ms": committed_at_ms,
            }
            v2_metrics["committed_turns"] = committed_turns
            v2_metrics["last_committed_at_ms"] = committed_at_ms
            metrics["call_v2"] = v2_metrics
            call.latency_metrics = metrics
            await session.commit()

            return TranscriptTurnCommitted(
                type="persistence.transcript_turn_committed",
                generation_id=generation_id,
                role=role,
                message_id=str(message.id),
                text_fingerprint=fingerprint,
                timestamps=TimestampMetadata(backend_received_at_ms=committed_at_ms),
            )

    async def record_latency_metric(
        self,
        *,
        name: str,
        value_ms: int | float,
        generation_id: int | None = None,
    ) -> None:
        async with self.session_factory() as session:
            call = await session.get(Call, self._uuid_call_id())
            if call is None:
                raise ValueError(f"call not found: {self.call_id}")
            metrics = dict(call.latency_metrics or {})
            _record_latency_metric(
                metrics,
                name=name,
                value_ms=value_ms,
                generation_id=generation_id,
            )
            call.latency_metrics = metrics
            await session.commit()

    async def record_cost_metric(
        self,
        *,
        name: str,
        amount_usd: int | float,
    ) -> None:
        async with self.session_factory() as session:
            call = await session.get(Call, self._uuid_call_id())
            if call is None:
                raise ValueError(f"call not found: {self.call_id}")
            breakdown = dict(call.cost_breakdown or {})
            _record_cost_metric(breakdown, name=name, amount_usd=amount_usd)
            call.cost_breakdown = breakdown
            await session.commit()

    async def mark_call_ended(
        self,
        *,
        ended_at_ms: int,
        reason: str,
        status: TerminalStatus = "completed",
    ) -> None:
        async with self.session_factory() as session:
            call = await session.get(Call, self._uuid_call_id())
            if call is None:
                raise ValueError(f"call not found: {self.call_id}")
            if call.status not in TERMINAL_STATUSES:
                call.status = status
            if call.ended_at is None:
                call.ended_at = _utc_now()
            if self._started_at_ms is not None:
                call.duration_seconds = max(
                    0,
                    int((ended_at_ms - self._started_at_ms) / 1000),
                )
            metrics = dict(call.latency_metrics or {})
            v2_metrics = dict(metrics.get("call_v2") or {})
            v2_metrics["ended_reason"] = reason
            v2_metrics["ended_at_ms"] = ended_at_ms
            metrics["call_v2"] = v2_metrics
            call.latency_metrics = metrics
            await session.commit()

    def _uuid_call_id(self) -> uuid.UUID:
        if isinstance(self.call_id, uuid.UUID):
            return self.call_id
        return uuid.UUID(self.call_id)


async def persist_call_v2_trace_summary(
    *,
    call_id: uuid.UUID | str,
    trace_events: list[dict],
    session_factory: SessionFactory = async_session_factory,
) -> None:
    async with session_factory() as session:
        call = await session.get(
            Call,
            call_id if isinstance(call_id, uuid.UUID) else uuid.UUID(call_id),
        )
        if call is None:
            raise ValueError(f"call not found: {call_id}")
        metrics = dict(call.latency_metrics or {})
        v2_metrics = dict(metrics.get("call_v2") or {})
        counts: dict[str, int] = {}
        recent_control_events: list[dict] = []
        for event in trace_events:
            event_type = str(event.get("event_type") or "unknown")
            counts[event_type] = counts.get(event_type, 0) + 1
            if event_type != "telephony.audio_frame":
                recent_control_events.append(event)
        v2_metrics["trace_summary"] = {
            "total_events": len(trace_events),
            "event_counts": counts,
            "recent_control_events": recent_control_events[-200:],
        }
        metrics["call_v2"] = v2_metrics
        call.latency_metrics = metrics
        await session.commit()

def _text_fingerprint(text: str) -> str:
    normalized = " ".join(text.split())
    return sha256(normalized.encode("utf-8")).hexdigest()


def _clean_text(text: str) -> str:
    return " ".join(text.split())


def _turn_idempotency_key(
    *,
    generation_id: int | None,
    role: Literal["user", "assistant"],
    text_fingerprint: str,
) -> str:
    generation = generation_id if generation_id is not None else "none"
    return f"{role}:{generation}:{text_fingerprint}"


def _append_transcript_line(
    current: str | None,
    *,
    role: Literal["user", "assistant"],
    text: str,
) -> str:
    line = f"{role.title()}: {text}"
    return f"{current}\n{line}".strip() if current else line


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _record_latency_metric(
    metrics: dict,
    *,
    name: str,
    value_ms: int | float,
    generation_id: int | None,
) -> None:
    v2_metrics = dict(metrics.get("call_v2") or {})
    if generation_id is None:
        latency_ms = dict(v2_metrics.get("latency_ms") or {})
        latency_ms[name] = value_ms
        v2_metrics["latency_ms"] = latency_ms
    else:
        generation_latency_ms = dict(v2_metrics.get("generation_latency_ms") or {})
        generation_metrics = dict(generation_latency_ms.get(str(generation_id)) or {})
        generation_metrics[name] = value_ms
        generation_latency_ms[str(generation_id)] = generation_metrics
        v2_metrics["generation_latency_ms"] = generation_latency_ms
    metrics["call_v2"] = v2_metrics


def _record_cost_metric(
    breakdown: dict,
    *,
    name: str,
    amount_usd: int | float,
) -> None:
    costs = dict(breakdown.get("costs") or {})
    costs[name] = round(float(amount_usd), 6)
    breakdown["runtime"] = "call_v2"
    breakdown["costs"] = costs
    breakdown["estimated_total_usd"] = round(
        sum(float(value) for value in costs.values()),
        6,
    )
