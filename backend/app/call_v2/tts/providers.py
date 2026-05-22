"""Fake TTS providers for call v2 tests and simulator wiring."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.call_v2.tts.base import TtsAudio, TtsRequest


class TtsProviderError(RuntimeError):
    """Raised when a TTS provider cannot synthesize audio."""


@dataclass(slots=True)
class FakeTtsEngine:
    provider: str = "fake"
    model: str = "fake-tts"
    voice: str = "test"
    language: str = "en"
    speaking_style: str | None = None
    payload: bytes = b"\x00\x01" * 160
    fail: bool = False
    requests: list[TtsRequest] = field(default_factory=list)
    cancelled_generation_ids: set[int] = field(default_factory=set)

    async def synthesize(self, request: TtsRequest) -> TtsAudio:
        self.requests.append(request)
        if request.generation_id in self.cancelled_generation_ids:
            raise TtsProviderError(
                f"TTS generation {request.generation_id} was cancelled"
            )
        if self.fail:
            raise TtsProviderError(f"{self.provider} fake TTS failure")
        return TtsAudio(
            payload=self.payload,
            audio_format=request.output_format,
            provider=self.provider,
            model=self.model,
            voice=self.voice,
            language=self.language,
            speaking_style=self.speaking_style,
        )

    def cancel(self, generation_id: int) -> None:
        self.cancelled_generation_ids.add(generation_id)
