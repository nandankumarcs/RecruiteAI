"""Fixture-backed fake STT engine for simulator and unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator

from app.call_v2.events import AudioFormat, TelephonyAudioFrame
from app.call_v2.stt.base import SttEvent


@dataclass(slots=True)
class FakeSttEngine:
    provider: str
    input_format: AudioFormat
    events: list[SttEvent] = field(default_factory=list)
    received_audio: list[TelephonyAudioFrame] = field(default_factory=list)
    closed: bool = False

    async def send_audio(self, frame: TelephonyAudioFrame) -> None:
        if self.closed:
            raise RuntimeError("cannot send audio to a closed fake STT engine")
        self.received_audio.append(frame)

    async def receive_events(self) -> AsyncIterator[SttEvent]:
        for event in self.events:
            yield event

    async def close(self) -> None:
        self.closed = True

