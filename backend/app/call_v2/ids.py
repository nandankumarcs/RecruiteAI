"""Generation id helpers for call v2 turn processing."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GenerationIdManager:
    """Tracks turn generation ids and stale speculative generations."""

    _next_generation_id: int = 1
    latest_started_generation_id: int | None = None
    latest_confirmed_generation_id: int | None = None
    _stale_generation_ids: set[int] = field(default_factory=set)

    def start_generation(self) -> int:
        generation_id = self._next_generation_id
        self._next_generation_id += 1
        self.latest_started_generation_id = generation_id
        return generation_id

    def mark_confirmed(self, generation_id: int) -> None:
        if self.is_stale(generation_id):
            raise ValueError(f"cannot confirm stale generation {generation_id}")
        if self.latest_started_generation_id is None:
            raise ValueError(f"unknown generation {generation_id}")
        if generation_id < 1 or generation_id > self.latest_started_generation_id:
            raise ValueError(f"unknown generation {generation_id}")
        self.latest_confirmed_generation_id = generation_id

    def mark_stale(self, generation_id: int) -> None:
        if (
            self.latest_started_generation_id is None
            or generation_id < 1
            or generation_id > self.latest_started_generation_id
        ):
            raise ValueError(f"unknown generation {generation_id}")
        self._stale_generation_ids.add(generation_id)

    def is_stale(self, generation_id: int) -> bool:
        return generation_id in self._stale_generation_ids

    def can_speak(self, generation_id: int) -> bool:
        return (
            generation_id == self.latest_confirmed_generation_id
            and not self.is_stale(generation_id)
        )
