"""OpenAI-backed TTS provider for call v2 simulator testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI

from app.call_v2.audio.wav import wav_bytes_to_linear16
from app.call_v2.tts.base import TtsAudio, TtsRequest
from app.call_v2.tts.providers import TtsProviderError


@dataclass(slots=True)
class OpenAITtsEngine:
    api_key: str
    provider: str = "openai"
    model: str = "gpt-4o-mini-tts"
    voice: str = "coral"
    language: str = "en"
    speaking_style: str | None = None
    speed: float = 1.0
    client: Any | None = None
    cancelled_generation_ids: set[int] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = AsyncOpenAI(api_key=self.api_key)

    async def synthesize(self, request: TtsRequest) -> TtsAudio:
        if request.generation_id in self.cancelled_generation_ids:
            raise TtsProviderError(
                f"TTS generation {request.generation_id} was cancelled"
            )
        if request.output_format.codec != "linear16":
            raise TtsProviderError("OpenAI TTS currently emits linear16 only")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "voice": self.voice,
            "input": request.text,
            "response_format": "wav",
            "speed": self.speed,
        }
        if self.speaking_style:
            kwargs["instructions"] = self.speaking_style

        response = await self.client.audio.speech.create(**kwargs)
        wav_payload = await _read_binary_response(response)
        payload = wav_bytes_to_linear16(
            wav_payload,
            target_format=request.output_format,
        )
        if not payload:
            raise TtsProviderError("OpenAI TTS returned empty audio")

        return TtsAudio(
            payload=payload,
            audio_format=request.output_format,
            provider=self.provider,
            model=self.model,
            voice=self.voice,
            language=self.language,
            speaking_style=self.speaking_style,
        )

    def cancel(self, generation_id: int) -> None:
        self.cancelled_generation_ids.add(generation_id)


async def _read_binary_response(response: Any) -> bytes:
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content

    aread = getattr(response, "aread", None)
    if callable(aread):
        data = await aread()
        if isinstance(data, bytes):
            return data

    read = getattr(response, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data

    if isinstance(response, bytes):
        return response

    raise TtsProviderError("OpenAI TTS response did not contain binary audio")
