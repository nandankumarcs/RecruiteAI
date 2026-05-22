"""Domain event contracts for the call v2 runtime.

These models are intentionally provider-agnostic. Provider payloads should be
translated into these contracts at adapter boundaries before reaching the core
session runtime.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Literal


def _to_plain_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_plain_value(item) for key, item in asdict(value).items()}
    if isinstance(value, bytes):
        return {"encoding": "base64", "byte_length": len(value)}
    if isinstance(value, dict):
        return {str(key): _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_value(item) for item in value]
    return value


class EventPayload:
    """Mixin for serializable event payloads."""

    def to_dict(self) -> dict[str, Any]:
        return _to_plain_value(self)


@dataclass(frozen=True, slots=True)
class TimestampMetadata(EventPayload):
    backend_received_at_ms: int
    provider_timestamp_ms: int | None = None
    audio_offset_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AudioFormat(EventPayload):
    codec: Literal["mulaw", "linear16"]
    sample_rate_hz: int = 8000
    channels: int = 1
    container: str | None = None

    def is_compatible_with(self, other: "AudioFormat") -> bool:
        return (
            self.codec == other.codec
            and self.sample_rate_hz == other.sample_rate_hz
            and self.channels == other.channels
            and self.container == other.container
        )


@dataclass(frozen=True, slots=True)
class CallIdentity(EventPayload):
    provider: str
    call_id: str | None = None
    resume_id: str | None = None
    provider_call_id: str | None = None
    stream_id: str | None = None

    def require_stream_id(self) -> str:
        if not self.stream_id:
            raise ValueError("stream_id is required for outbound telephony audio")
        return self.stream_id


@dataclass(frozen=True, slots=True)
class TelephonyStreamStarted(EventPayload):
    type: Literal["telephony.stream_started"]
    identity: CallIdentity
    inbound_format: AudioFormat
    outbound_format: AudioFormat
    timestamps: TimestampMetadata
    raw_provider_event: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TelephonyAudioFrame(EventPayload):
    type: Literal["telephony.audio_frame"]
    identity: CallIdentity
    payload: bytes
    format: AudioFormat
    sequence_number: int | None
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TelephonyDtmf(EventPayload):
    type: Literal["telephony.dtmf"]
    identity: CallIdentity
    digit: str
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TelephonyStreamStopped(EventPayload):
    type: Literal["telephony.stream_stopped"]
    identity: CallIdentity
    reason: str | None
    timestamps: TimestampMetadata
    raw_provider_event: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SendAudioFrame(EventPayload):
    type: Literal["telephony.send_audio_frame"]
    identity: CallIdentity
    payload: bytes
    format: AudioFormat
    generation_id: int | None
    is_first_frame: bool
    is_final_frame: bool

    def validate_ready_to_send(self) -> None:
        self.identity.require_stream_id()


@dataclass(frozen=True, slots=True)
class ClearOutboundAudio(EventPayload):
    type: Literal["telephony.clear_outbound_audio"]
    identity: CallIdentity
    generation_id: int | None
    reason: str

    def validate_ready_to_send(self) -> None:
        self.identity.require_stream_id()


@dataclass(frozen=True, slots=True)
class EndProviderCall(EventPayload):
    type: Literal["telephony.end_call"]
    identity: CallIdentity
    reason: str


@dataclass(frozen=True, slots=True)
class SttConnected(EventPayload):
    type: Literal["stt.connected"]
    provider: str
    model: str
    input_format: AudioFormat
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class SttSpeechStarted(EventPayload):
    type: Literal["stt.speech_started"]
    timestamps: TimestampMetadata
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class SttInterimTranscript(EventPayload):
    type: Literal["stt.interim_transcript"]
    text: str
    confidence: float | None
    timestamps: TimestampMetadata
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SttFinalSegment(EventPayload):
    type: Literal["stt.final_segment"]
    text: str
    confidence: float | None
    segment_id: str | None
    timestamps: TimestampMetadata
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SttTentativeEndpoint(EventPayload):
    type: Literal["stt.tentative_endpoint"]
    text: str
    confidence: float | None
    silence_ms: int | None
    timestamps: TimestampMetadata
    duration_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SttUtteranceEnded(EventPayload):
    type: Literal["stt.utterance_ended"]
    text: str
    confidence: float | None
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class SttError(EventPayload):
    type: Literal["stt.error"]
    provider: str
    code: str | None
    message: str
    recoverable: bool
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TentativeTurnStarted(EventPayload):
    type: Literal["turn.tentative_started"]
    generation_id: int
    text: str
    source: str
    evidence: dict[str, Any]
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TentativeTurnCancelled(EventPayload):
    type: Literal["turn.tentative_cancelled"]
    generation_id: int
    reason: str
    replacement_generation_id: int | None
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TurnConfirmed(EventPayload):
    type: Literal["turn.confirmed"]
    generation_id: int
    text: str
    confidence: float | None
    duration_ms: int | None
    evidence: dict[str, Any]
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class TurnDiscarded(EventPayload):
    type: Literal["turn.discarded"]
    generation_id: int | None
    text: str
    reason: str
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class AgentRunStarted(EventPayload):
    type: Literal["agent.run_started"]
    generation_id: int
    speculative: bool
    input_fingerprint: str
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class AgentRunCompleted(EventPayload):
    type: Literal["agent.run_completed"]
    generation_id: int
    speculative: bool
    result: dict[str, Any]
    usage: dict[str, Any] | None
    latency_ms: int
    timestamps: TimestampMetadata


@dataclass(frozen=True, slots=True)
class AudioSourceSelected(EventPayload):
    type: Literal["audio.source_selected"]
    generation_id: int
    source: Literal["cache", "live_tts", "fallback_tts"]
    cache_key: str | None
    cache_category: str | None
    text_fingerprint: str
    timestamps: TimestampMetadata
    decision_reason: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptTurnCommitted(EventPayload):
    type: Literal["persistence.transcript_turn_committed"]
    generation_id: int | None
    role: Literal["user", "assistant"]
    message_id: str
    text_fingerprint: str
    timestamps: TimestampMetadata
