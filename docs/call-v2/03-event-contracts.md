# Call V2 Event Contracts

## Purpose

V2 needs explicit contracts between modules. Provider payloads, STT provider events, agent outputs, and TTS chunks should not flow through the system as loosely understood dictionaries.

This document defines the domain events and payload shapes that each module should produce or consume.

The concrete implementation can use Python dataclasses, Pydantic models, or typed dictionaries. The important part is that the boundaries are explicit and testable.

## Naming Principles

- Provider-specific events stay inside `TelephonyAdapter`.
- STT-specific events stay inside `STTEngine`.
- The runtime should operate on v2 domain events.
- Every event should carry enough metadata for tracing.
- Every turn-related event should include `generation_id` when applicable.
- Timestamps should distinguish backend wall time from provider/STT audio time when possible.

## Shared Types

### TimestampMetadata

```python
class TimestampMetadata:
    backend_received_at_ms: int
    provider_timestamp_ms: int | None
    audio_offset_ms: int | None
```

Fields:

- `backend_received_at_ms`: monotonic runtime timestamp when event was received or created.
- `provider_timestamp_ms`: timestamp from telephony provider if available.
- `audio_offset_ms`: STT/audio timeline offset if available.

### AudioFormat

```python
class AudioFormat:
    codec: str              # "mulaw", "linear16"
    sample_rate_hz: int     # usually 8000
    channels: int           # usually 1
    container: str | None   # usually None for raw frames
```

### CallIdentity

```python
class CallIdentity:
    call_id: str | None
    resume_id: str | None
    provider: str
    provider_call_id: str | None
    stream_id: str | None
```

`resume_id` is recruitment-specific but may exist during the first v2 use case. The general runtime should not require it as a core concept.

## Telephony Adapter Output Events

These events are emitted by provider adapters into `CallSession`.

### TelephonyStreamStarted

```python
class TelephonyStreamStarted:
    type: Literal["telephony.stream_started"]
    identity: CallIdentity
    inbound_format: AudioFormat
    outbound_format: AudioFormat
    timestamps: TimestampMetadata
    raw_provider_event: dict | None
```

Meaning:

The provider media stream is ready and outbound audio may be sent.

Rules:

- `stream_id` must be known if provider requires it for outbound audio.
- No TTS audio should be sent before this event.

### TelephonyAudioFrame

```python
class TelephonyAudioFrame:
    type: Literal["telephony.audio_frame"]
    identity: CallIdentity
    payload: bytes
    format: AudioFormat
    sequence_number: int | None
    timestamps: TimestampMetadata
```

Meaning:

Inbound caller audio frame after base64 decoding and provider normalization.

Rules:

- Payload is raw bytes in the declared format.
- Adapter should not perform STT-specific transformations.

### TelephonyDtmf

```python
class TelephonyDtmf:
    type: Literal["telephony.dtmf"]
    identity: CallIdentity
    digit: str
    timestamps: TimestampMetadata
```

### TelephonyStreamStopped

```python
class TelephonyStreamStopped:
    type: Literal["telephony.stream_stopped"]
    identity: CallIdentity
    reason: str | None
    timestamps: TimestampMetadata
    raw_provider_event: dict | None
```

Meaning:

Provider stream ended. Active STT, agent, and TTS work should be cancelled.

### TelephonyError

```python
class TelephonyError:
    type: Literal["telephony.error"]
    identity: CallIdentity
    code: str | None
    message: str
    recoverable: bool
    timestamps: TimestampMetadata
```

## Runtime To Telephony Adapter Commands

These commands are sent from `CallSession` to the adapter.

### SendAudioFrame

```python
class SendAudioFrame:
    type: Literal["telephony.send_audio_frame"]
    identity: CallIdentity
    payload: bytes
    format: AudioFormat
    generation_id: int | None
    is_first_frame: bool
    is_final_frame: bool
```

Rules:

- Adapter handles base64 encoding and provider envelope.
- Adapter validates `stream_id` before sending.
- Runtime must attach generation id for assistant audio tied to a turn.

### ClearOutboundAudio

```python
class ClearOutboundAudio:
    type: Literal["telephony.clear_outbound_audio"]
    identity: CallIdentity
    generation_id: int | None
    reason: str
```

Meaning:

Ask provider to clear buffered assistant audio if supported.

### EndProviderCall

```python
class EndProviderCall:
    type: Literal["telephony.end_call"]
    identity: CallIdentity
    reason: str
```

## STT Engine Output Events

### SttConnected

```python
class SttConnected:
    type: Literal["stt.connected"]
    provider: str
    model: str
    input_format: AudioFormat
    timestamps: TimestampMetadata
```

### SttSpeechStarted

```python
class SttSpeechStarted:
    type: Literal["stt.speech_started"]
    timestamps: TimestampMetadata
    confidence: float | None
```

Meaning:

STT/VAD believes speech has started.

Rules:

- This is not enough by itself to cancel TTS.
- While assistant is speaking, this should create `pending_barge_in`, not immediate cancellation.

### SttInterimTranscript

```python
class SttInterimTranscript:
    type: Literal["stt.interim_transcript"]
    text: str
    confidence: float | None
    timestamps: TimestampMetadata
```

Meaning:

Non-final transcript content.

Rules:

- Never persist as durable transcript.
- May be used for UI/debug trace and optional early barge-in hints.

### SttFinalSegment

```python
class SttFinalSegment:
    type: Literal["stt.final_segment"]
    text: str
    confidence: float | None
    segment_id: str | None
    timestamps: TimestampMetadata
```

Meaning:

Finalized segment, but not necessarily the full user turn.

Rules:

- Feed into transcript assembler.
- Deduplicate overlapping segments.

### SttTentativeEndpoint

```python
class SttTentativeEndpoint:
    type: Literal["stt.tentative_endpoint"]
    text: str
    confidence: float | None
    silence_ms: int | None
    timestamps: TimestampMetadata
```

Meaning:

STT endpointing suggests the user may have stopped. This starts speculation, not durable state.

### SttUtteranceEnded

```python
class SttUtteranceEnded:
    type: Literal["stt.utterance_ended"]
    text: str
    confidence: float | None
    timestamps: TimestampMetadata
```

Meaning:

STT believes the utterance is complete. Endpointing controller still decides whether this confirms a turn.

### SttError

```python
class SttError:
    type: Literal["stt.error"]
    provider: str
    code: str | None
    message: str
    recoverable: bool
    timestamps: TimestampMetadata
```

## Endpointing Events

Endpointing events are emitted by `EndpointingController`.

### TentativeTurnStarted

```python
class TentativeTurnStarted:
    type: Literal["turn.tentative_started"]
    generation_id: int
    text: str
    source: str              # "stt_endpoint", "utterance_end", "manual"
    evidence: dict
    timestamps: TimestampMetadata
```

Meaning:

Start speculative agent processing for a possible user turn.

Rules:

- Does not persist transcript.
- Does not execute tools.
- Does not speak.

### TentativeTurnCancelled

```python
class TentativeTurnCancelled:
    type: Literal["turn.tentative_cancelled"]
    generation_id: int
    reason: str
    replacement_generation_id: int | None
    timestamps: TimestampMetadata
```

Meaning:

Candidate continued or evidence invalidated the tentative turn.

### TurnConfirmed

```python
class TurnConfirmed:
    type: Literal["turn.confirmed"]
    generation_id: int
    text: str
    confidence: float | None
    duration_ms: int | None
    evidence: dict
    timestamps: TimestampMetadata
```

Meaning:

Candidate turn is confirmed and can be persisted, passed to agent, and used in conversation history.

### TurnDiscarded

```python
class TurnDiscarded:
    type: Literal["turn.discarded"]
    generation_id: int | None
    text: str
    reason: str              # "echo", "duplicate", "empty", "too_short_noise"
    timestamps: TimestampMetadata
```

## Agent Contracts

Full details live in `04-agent-contract.md`. Events here define runtime lifecycle.

### AgentRunStarted

```python
class AgentRunStarted:
    type: Literal["agent.run_started"]
    generation_id: int
    speculative: bool
    input_fingerprint: str
    timestamps: TimestampMetadata
```

### AgentRunCancelled

```python
class AgentRunCancelled:
    type: Literal["agent.run_cancelled"]
    generation_id: int
    reason: str
    timestamps: TimestampMetadata
```

### AgentRunCompleted

```python
class AgentRunCompleted:
    type: Literal["agent.run_completed"]
    generation_id: int
    speculative: bool
    result: "AgentOutput"
    usage: dict | None
    latency_ms: int
    timestamps: TimestampMetadata
```

### AgentRunFailed

```python
class AgentRunFailed:
    type: Literal["agent.run_failed"]
    generation_id: int
    error_type: str
    message: str
    recoverable: bool
    timestamps: TimestampMetadata
```

## Audio Source And TTS Events

### AudioSourceSelected

```python
class AudioSourceSelected:
    type: Literal["audio.source_selected"]
    generation_id: int
    source: str              # "cache", "live_tts", "fallback_tts"
    cache_key: str | None
    cache_category: str | None
    text_fingerprint: str
    timestamps: TimestampMetadata
```

### TtsStarted

```python
class TtsStarted:
    type: Literal["tts.started"]
    generation_id: int
    provider: str
    voice: str
    streaming: bool
    text_fingerprint: str
    timestamps: TimestampMetadata
```

### TtsFirstAudio

```python
class TtsFirstAudio:
    type: Literal["tts.first_audio"]
    generation_id: int
    provider: str
    latency_ms: int
    timestamps: TimestampMetadata
```

### TtsAudioChunk

```python
class TtsAudioChunk:
    type: Literal["tts.audio_chunk"]
    generation_id: int
    payload: bytes
    format: AudioFormat
    sequence_number: int
    is_final: bool
    timestamps: TimestampMetadata
```

### TtsCancelled

```python
class TtsCancelled:
    type: Literal["tts.cancelled"]
    generation_id: int
    reason: str
    timestamps: TimestampMetadata
```

### TtsCompleted

```python
class TtsCompleted:
    type: Literal["tts.completed"]
    generation_id: int
    provider: str
    audio_duration_ms: int | None
    chunks_sent: int
    timestamps: TimestampMetadata
```

### TtsFailed

```python
class TtsFailed:
    type: Literal["tts.failed"]
    generation_id: int
    provider: str
    error_type: str
    message: str
    fallback_available: bool
    timestamps: TimestampMetadata
```

## Persistence Events

### TranscriptTurnCommitted

```python
class TranscriptTurnCommitted:
    type: Literal["persistence.transcript_turn_committed"]
    generation_id: int | None
    role: str                # "user", "assistant"
    message_id: str
    text_fingerprint: str
    timestamps: TimestampMetadata
```

### CallStatusChanged

```python
class CallStatusChanged:
    type: Literal["persistence.call_status_changed"]
    previous_status: str | None
    next_status: str
    reason: str
    timestamps: TimestampMetadata
```

## Trace Event Envelope

Every trace event should be serializable with a common envelope.

```python
class TraceEvent:
    trace_id: str
    call_id: str | None
    generation_id: int | None
    event_type: str
    monotonic_ms: int
    data: dict
```

Rules:

- Do not log raw credentials.
- Do not log full audio payloads by default.
- Transcript text may be logged in simulator/dev traces.
- Production trace logging should allow redaction or hashing.

## Idempotency Keys

Durable writes should use stable keys:

- User turn: `call_id:generation_id:user`
- Assistant turn: `call_id:generation_id:assistant`
- Cached audio asset: see cache policy doc.
- Trace id: generated once per call session.

## Required Seam Tests

### Telephony -> Runtime

- Twilio/Exotel/browser start events produce the same `TelephonyStreamStarted` shape.
- Media payloads become bytes with correct `AudioFormat`.
- Missing stream id blocks outbound audio.

### Runtime -> STT

- Audio frames are forwarded in expected format.
- Codec conversion happens only at explicit codec boundary.

### STT -> Endpointing

- Duplicate final segments are deduplicated.
- Tentative endpoint starts speculation.
- Delayed STT event does not by itself prove real silence.

### Endpointing -> Agent

- Tentative turn starts speculative run.
- Cancelled tentative turn cancels or stales agent run.
- Confirmed turn commits exactly once.

### Agent -> TTS

- Invalid agent output does not reach TTS.
- Stale generation output does not reach TTS.
- Terminal action waits for spoken text before ending call.

### TTS -> Telephony

- Chunks are paced.
- Provider clear audio is sent on confirmed barge-in if supported.
- Audio format matches adapter requirements.
