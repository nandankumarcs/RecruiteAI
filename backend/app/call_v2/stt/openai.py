"""OpenAI-backed buffered STT for call v2 simulator testing."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from openai import AsyncOpenAI

from app.call_v2.audio.formats import bytes_per_second
from app.call_v2.audio.wav import linear16_to_wav_bytes
from app.call_v2.events import (
    AudioFormat,
    SttError,
    SttFinalSegment,
    SttTentativeEndpoint,
    TelephonyAudioFrame,
    TimestampMetadata,
)
from app.call_v2.stt.base import SttEvent


@dataclass(slots=True)
class OpenAIBufferedTranscriptionEngine:
    """Buffer simulator audio and transcribe one confirmed candidate turn."""

    api_key: str
    input_format: AudioFormat
    model: str = "whisper-1"
    language: str | None = "en"
    provider: str = "openai"
    client: Any | None = None
    _buffer: bytearray = field(default_factory=bytearray)
    _first_audio_offset_ms: int | None = None
    _first_backend_received_at_ms: int | None = None
    closed: bool = False

    def __post_init__(self) -> None:
        if self.input_format.codec != "linear16":
            raise ValueError("OpenAI buffered STT expects linear16 input audio")
        if self.client is None:
            self.client = AsyncOpenAI(api_key=self.api_key)

    async def send_audio(self, frame: TelephonyAudioFrame) -> None:
        if self.closed:
            raise RuntimeError("cannot send audio to a closed OpenAI STT engine")
        if not frame.format.is_compatible_with(self.input_format):
            raise ValueError("audio frame format does not match OpenAI STT input")
        if not frame.payload:
            return
        if self._first_audio_offset_ms is None:
            self._first_audio_offset_ms = frame.timestamps.audio_offset_ms
            self._first_backend_received_at_ms = (
                frame.timestamps.backend_received_at_ms
            )
        self._buffer.extend(frame.payload)

    async def receive_events(self):
        if False:
            yield None

    async def close(self) -> None:
        self.closed = True

    def reset_buffer(self) -> None:
        self._buffer.clear()
        self._first_audio_offset_ms = None
        self._first_backend_received_at_ms = None

    async def transcribe_buffer(
        self,
        *,
        now_ms: int,
        silence_ms: int | None = None,
        clear: bool = True,
    ) -> list[SttEvent]:
        if not self._buffer:
            return []

        audio = bytes(self._buffer)
        duration_ms = _duration_ms(audio, self.input_format)
        timestamps = TimestampMetadata(
            backend_received_at_ms=now_ms,
            audio_offset_ms=self._first_audio_offset_ms,
        )
        try:
            text = await self._transcribe(audio)
        except Exception as exc:
            if clear:
                self.reset_buffer()
            return [
                SttError(
                    type="stt.error",
                    provider=self.provider,
                    code=exc.__class__.__name__,
                    message=str(exc),
                    recoverable=True,
                    timestamps=timestamps,
                )
            ]
        finally:
            if clear:
                self.reset_buffer()

        normalized = " ".join(text.split())
        if not normalized:
            return []

        segment = SttFinalSegment(
            type="stt.final_segment",
            text=normalized,
            confidence=None,
            segment_id=f"openai-buffer:{sha256(audio).hexdigest()[:16]}",
            timestamps=timestamps,
            duration_ms=duration_ms,
        )
        endpoint = SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text=normalized,
            confidence=None,
            silence_ms=silence_ms,
            timestamps=timestamps,
            duration_ms=duration_ms,
        )
        return [segment, endpoint]

    async def _transcribe(self, audio: bytes) -> str:
        wav_bytes = linear16_to_wav_bytes(audio, audio_format=self.input_format)
        file_obj = io.BytesIO(wav_bytes)
        file_obj.name = "call-v2-turn.wav"
        kwargs: dict[str, Any] = {
            "model": self.model,
            "file": file_obj,
            "response_format": "text",
        }
        if self.language:
            kwargs["language"] = self.language
        response = await self.client.audio.transcriptions.create(**kwargs)
        if isinstance(response, str):
            return response
        return str(getattr(response, "text", "") or "")


def _duration_ms(payload: bytes, audio_format: AudioFormat) -> int:
    return int(len(payload) * 1000 / bytes_per_second(audio_format))
