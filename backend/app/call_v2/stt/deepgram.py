"""Deepgram streaming STT for call v2."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import websockets

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
    TimestampMetadata,
)


class DeepgramEventNormalizer:
    provider = "deepgram"

    def __init__(self, *, input_format: AudioFormat, model: str = "unknown") -> None:
        self.input_format = input_format
        self.model = model

    def normalize(
        self,
        message: str | dict[str, Any],
        *,
        backend_received_at_ms: int,
    ) -> list[
        SttSpeechStarted
        | SttInterimTranscript
        | SttFinalSegment
        | SttTentativeEndpoint
        | SttUtteranceEnded
        | SttError
    ]:
        payload = self._coerce_message(message)
        event_type = payload.get("type")

        if event_type == "SpeechStarted":
            return [
                SttSpeechStarted(
                    type="stt.speech_started",
                    timestamps=self._timestamps(payload, backend_received_at_ms),
                )
            ]
        if event_type == "UtteranceEnd":
            return [
                SttUtteranceEnded(
                    type="stt.utterance_ended",
                    text="",
                    confidence=None,
                    timestamps=self._timestamps(payload, backend_received_at_ms),
                )
            ]
        if event_type in {"Results", "FinalResult"}:
            return self._normalize_results(payload, backend_received_at_ms)
        if event_type == "Error" or payload.get("error"):
            error = payload.get("error") or {}
            return [
                SttError(
                    type="stt.error",
                    provider=self.provider,
                    code=error.get("code") or payload.get("code"),
                    message=(
                        error.get("message")
                        or payload.get("message")
                        or "Deepgram STT error"
                    ),
                    recoverable=bool(payload.get("recoverable", True)),
                    timestamps=self._timestamps(payload, backend_received_at_ms),
                )
            ]
        return []

    def _normalize_results(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> list[SttInterimTranscript | SttFinalSegment | SttTentativeEndpoint]:
        transcript = self._extract_transcript(payload)
        if not transcript:
            return []

        timestamps = self._timestamps(payload, backend_received_at_ms)
        confidence = self._extract_confidence(payload)
        duration_ms = self._duration_ms(payload)
        events: list[SttInterimTranscript | SttFinalSegment | SttTentativeEndpoint] = []

        is_final = self._is_final_result(payload)
        speech_final = self._is_speech_final(payload)

        if is_final:
            events.append(
                SttFinalSegment(
                    type="stt.final_segment",
                    text=transcript,
                    confidence=confidence,
                    segment_id=self._segment_id(payload),
                    timestamps=timestamps,
                    duration_ms=duration_ms,
                )
            )
        else:
            events.append(
                SttInterimTranscript(
                    type="stt.interim_transcript",
                    text=transcript,
                    confidence=confidence,
                    timestamps=timestamps,
                    duration_ms=duration_ms,
                )
            )

        if speech_final:
            events.append(
                SttTentativeEndpoint(
                    type="stt.tentative_endpoint",
                    text=transcript,
                    confidence=confidence,
                    silence_ms=None,
                    timestamps=timestamps,
                    duration_ms=duration_ms,
                )
            )

        return events

    def _coerce_message(self, message: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(message, str):
            parsed = json.loads(message)
        else:
            parsed = message
        if not isinstance(parsed, dict):
            raise ValueError("Deepgram message must be a JSON object")
        return parsed

    def _extract_transcript(self, payload: dict[str, Any]) -> str:
        return str(self._primary_alternative(payload).get("transcript", "")).strip()

    def _extract_confidence(self, payload: dict[str, Any]) -> float | None:
        value = self._primary_alternative(payload).get("confidence")
        if value is None:
            return None
        return float(value)

    def _primary_alternative(self, payload: dict[str, Any]) -> dict[str, Any]:
        alternatives = self._extract_alternatives(payload)
        if not alternatives:
            return {}
        first = alternatives[0]
        if isinstance(first, dict):
            return first
        return {}

    def _extract_alternatives(self, payload: dict[str, Any]) -> list[Any]:
        channel = payload.get("channel")
        if isinstance(channel, dict) and isinstance(channel.get("alternatives"), list):
            return channel["alternatives"]

        channels = payload.get("channels")
        if isinstance(channels, dict) and isinstance(channels.get("alternatives"), list):
            return channels["alternatives"]
        if isinstance(channels, list) and channels:
            first_channel = channels[0]
            if (
                isinstance(first_channel, dict)
                and isinstance(first_channel.get("alternatives"), list)
            ):
                return first_channel["alternatives"]

        alternatives = payload.get("alternatives")
        if isinstance(alternatives, list):
            return alternatives
        return []

    def _timestamps(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TimestampMetadata:
        return TimestampMetadata(
            backend_received_at_ms=backend_received_at_ms,
            provider_timestamp_ms=self._optional_ms(payload.get("timestamp")),
            audio_offset_ms=self._optional_ms(self._audio_offset_seconds(payload)),
        )

    def _duration_ms(self, payload: dict[str, Any]) -> int | None:
        return self._optional_ms(payload.get("duration"))

    def _optional_ms(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(float(value) * 1000)

    def _audio_offset_seconds(self, payload: dict[str, Any]) -> Any:
        start = payload.get("start")
        if start is not None:
            return start
        return payload.get("last_word_end")

    def _segment_id(self, payload: dict[str, Any]) -> str | None:
        return self._segment_id_from_timing(payload)

    def _segment_id_from_timing(self, payload: dict[str, Any]) -> str | None:
        start = payload.get("start")
        duration = payload.get("duration")
        if start is None and duration is None:
            return None
        return f"start={start};duration={duration}"

    def _is_final_result(self, payload: dict[str, Any]) -> bool:
        return bool(
            payload.get("is_final")
            or payload.get("speech_finalized")
            or payload.get("type") == "FinalResult"
        )

    def _is_speech_final(self, payload: dict[str, Any]) -> bool:
        return bool(payload.get("speech_final") or payload.get("speech_finalized"))


@dataclass(slots=True)
class DeepgramStreamingSttEngine:
    """Streams Exotel L16 frames to Deepgram and yields v2 STT events."""

    api_key: str
    input_format: AudioFormat
    model: str = "nova-3"
    language: str = "en-IN"
    endpointing_ms: int = 500
    utterance_end_ms: int = 1000
    keyterms: list[str] = field(default_factory=list)
    url: str = "wss://api.deepgram.com/v1/listen"
    provider: str = "deepgram"
    _ws: Any | None = field(default=None, init=False, repr=False)
    _connect_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _closed: bool = field(default=False, init=False)
    _connected_event_emitted: bool = field(default=False, init=False)
    _keepalive_task: asyncio.Task | None = field(default=None, init=False, repr=False)

    async def send_audio(self, frame: TelephonyAudioFrame) -> None:
        if self._closed:
            raise RuntimeError("cannot send audio to a closed Deepgram STT engine")
        if not frame.format.is_compatible_with(self.input_format):
            raise ValueError("audio frame format does not match Deepgram input")
        ws = await self._ensure_connected()
        await ws.send(frame.payload)

    async def receive_events(self):
        try:
            ws = await self._ensure_connected()
            if not self._connected_event_emitted:
                self._connected_event_emitted = True
                yield SttConnected(
                    type="stt.connected",
                    provider=self.provider,
                    model=self.model,
                    input_format=self.input_format,
                    timestamps=TimestampMetadata(backend_received_at_ms=_now_ms()),
                )

            normalizer = DeepgramEventNormalizer(
                input_format=self.input_format,
                model=self.model,
            )
            async for raw_message in ws:
                for event in normalizer.normalize(
                    raw_message,
                    backend_received_at_ms=_now_ms(),
                ):
                    yield event
        except Exception as exc:
            if not self._closed:
                yield SttError(
                    type="stt.error",
                    provider=self.provider,
                    code=exc.__class__.__name__,
                    message=str(exc),
                    recoverable=False,
                    timestamps=TimestampMetadata(backend_received_at_ms=_now_ms()),
                )

    async def close(self) -> None:
        self._closed = True
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _ensure_connected(self):
        if self._ws is not None:
            return self._ws
        async with self._connect_lock:
            if self._ws is not None:
                return self._ws
            if not self.api_key:
                raise RuntimeError("DEEPGRAM_API_KEY is required for live STT")
            self._ws = await websockets.connect(
                self._listen_url(),
                additional_headers={"Authorization": f"Token {self.api_key}"},
                ping_interval=None,
            )
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            return self._ws

    def _listen_url(self) -> str:
        if self.input_format.codec != "linear16":
            raise ValueError("Deepgram live v2 STT currently expects linear16 audio")
        query: list[tuple[str, str | int]] = [
            ("model", self.model),
            ("language", self.language),
            ("encoding", "linear16"),
            ("sample_rate", self.input_format.sample_rate_hz),
            ("channels", self.input_format.channels),
            ("interim_results", "true"),
            ("vad_events", "true"),
            ("endpointing", self.endpointing_ms),
            ("utterance_end_ms", self.utterance_end_ms),
            ("punctuate", "true"),
            ("smart_format", "true"),
        ]
        if self.model.startswith("nova-3"):
            query.extend(("keyterm", term) for term in self.keyterms[:50] if term.strip())
        return f"{self.url}?{urlencode(query)}"

    async def _keepalive_loop(self) -> None:
        while not self._closed:
            await asyncio.sleep(5)
            ws = self._ws
            if ws is not None:
                await ws.send(json.dumps({"type": "KeepAlive"}))


def _now_ms() -> int:
    return int(asyncio.get_running_loop().time() * 1000)
