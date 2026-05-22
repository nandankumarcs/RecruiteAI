"""Speculative turn execution harness for call v2 tests.

The production agent runner arrives in a later phase. This module only models
the safety contract around speculative work: it can start, finish, and be
discarded, but its result is not eligible until the matching turn generation is
confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.call_v2.events import (
    AgentRunCompleted,
    AgentRunStarted,
    TentativeTurnCancelled,
    TentativeTurnStarted,
    TimestampMetadata,
)
from app.call_v2.ids import GenerationIdManager


def input_fingerprint(text: str) -> str:
    return sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class SpeculativeRun:
    generation_id: int
    input_fingerprint: str
    text: str
    started_at_ms: int
    completed_result: dict[str, Any] | None = None
    completed_at_ms: int | None = None
    cancelled: bool = False
    cancel_reason: str | None = None


@dataclass(slots=True)
class SpeculationHarness:
    """Tracks fake speculative agent runs until the real agent exists."""

    runs: dict[int, SpeculativeRun]

    def __init__(self) -> None:
        self.runs = {}

    def start(
        self,
        event: TentativeTurnStarted,
    ) -> AgentRunStarted:
        fingerprint = input_fingerprint(event.text)
        self.runs[event.generation_id] = SpeculativeRun(
            generation_id=event.generation_id,
            input_fingerprint=fingerprint,
            text=event.text,
            started_at_ms=event.timestamps.backend_received_at_ms,
        )
        return AgentRunStarted(
            type="agent.run_started",
            generation_id=event.generation_id,
            speculative=True,
            input_fingerprint=fingerprint,
            timestamps=event.timestamps,
        )

    def cancel(
        self,
        event: TentativeTurnCancelled,
    ) -> None:
        run = self.runs.get(event.generation_id)
        if run is None:
            return
        run.cancelled = True
        run.cancel_reason = event.reason

    def complete(
        self,
        generation_id: int,
        *,
        result: dict[str, Any],
        completed_at_ms: int,
        latency_ms: int,
    ) -> AgentRunCompleted:
        run = self._require_run(generation_id)
        run.completed_result = result
        run.completed_at_ms = completed_at_ms
        return AgentRunCompleted(
            type="agent.run_completed",
            generation_id=generation_id,
            speculative=True,
            result={
                **result,
                "discarded": run.cancelled,
                "cancel_reason": run.cancel_reason,
            },
            usage=None,
            latency_ms=latency_ms,
            timestamps=TimestampMetadata(backend_received_at_ms=completed_at_ms),
        )

    def eligible_result(
        self,
        generation_id: int,
        *,
        expected_fingerprint: str,
        generation_ids: GenerationIdManager,
    ) -> dict[str, Any] | None:
        run = self.runs.get(generation_id)
        if run is None:
            return None
        if run.cancelled or run.completed_result is None:
            return None
        if run.input_fingerprint != expected_fingerprint:
            return None
        if not generation_ids.can_speak(generation_id):
            return None
        return run.completed_result

    def _require_run(self, generation_id: int) -> SpeculativeRun:
        run = self.runs.get(generation_id)
        if run is None:
            raise ValueError(f"unknown speculative generation {generation_id}")
        return run
