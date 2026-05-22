"""Provider-neutral TTS contracts for call v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.call_v2.events import AudioFormat


@dataclass(frozen=True, slots=True)
class TtsRequest:
    generation_id: int
    text: str
    output_format: AudioFormat
    provider: str
    model: str
    voice: str
    language: str = "en"
    speaking_style: str | None = None


@dataclass(frozen=True, slots=True)
class TtsAudio:
    payload: bytes
    audio_format: AudioFormat
    provider: str
    model: str
    voice: str
    language: str = "en"
    speaking_style: str | None = None


class TtsEngine(Protocol):
    provider: str
    model: str
    voice: str
    language: str
    speaking_style: str | None

    async def synthesize(self, request: TtsRequest) -> TtsAudio:
        """Return audio for one TTS request."""

    def cancel(self, generation_id: int) -> None:
        """Cancel or mark cancelled synthesis for a generation."""
