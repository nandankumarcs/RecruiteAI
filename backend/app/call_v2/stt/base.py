"""STT engine contracts for call v2."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, TypeAlias

from app.call_v2.events import (
    AudioFormat,
    SttConnected,
    SttError,
    SttFinalSegment,
    SttInterimTranscript,
    SttSpeechStarted,
    SttTentativeEndpoint,
    SttUtteranceEnded,
    TelephonyAudioFrame,
)

SttEvent: TypeAlias = (
    SttConnected
    | SttSpeechStarted
    | SttInterimTranscript
    | SttFinalSegment
    | SttTentativeEndpoint
    | SttUtteranceEnded
    | SttError
)


class SttEngine(Protocol):
    """Consumes audio frames and emits normalized STT events."""

    provider: str
    input_format: AudioFormat

    async def send_audio(self, frame: TelephonyAudioFrame) -> None:
        """Send caller audio to the STT engine."""

    async def receive_events(self) -> AsyncIterator[SttEvent]:
        """Yield normalized STT events."""

    async def close(self) -> None:
        """Close any STT resources."""

