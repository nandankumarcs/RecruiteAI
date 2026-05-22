"""Browser/simulator telephony adapter for call v2.

The existing browser simulator uses the same L16 8kHz media shape as the
Exotel path. This adapter keeps that provider-specific envelope at the edge and
emits provider-agnostic v2 events.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import (
    CallIdentity,
    ClearOutboundAudio,
    SendAudioFrame,
    TelephonyAudioFrame,
    TelephonyDtmf,
    TelephonyStreamStarted,
    TelephonyStreamStopped,
    TimestampMetadata,
)


class BrowserSimulatorTelephonyAdapter:
    """Adapter for browser simulator messages that mirror Exotel media events."""

    provider = "browser"
    audio_format = LINEAR16_8K_MONO

    def parse_inbound_message(
        self,
        message: str | dict,
        *,
        backend_received_at_ms: int,
    ) -> TelephonyStreamStarted | TelephonyAudioFrame | TelephonyDtmf | TelephonyStreamStopped | None:
        payload = self._coerce_message(message)
        event = payload.get("event")

        if event == "connected":
            return None
        if event == "start":
            return self._parse_start(payload, backend_received_at_ms)
        if event == "media":
            return self._parse_media(payload, backend_received_at_ms)
        if event == "dtmf":
            return self._parse_dtmf(payload, backend_received_at_ms)
        if event == "stop":
            return self._parse_stop(payload, backend_received_at_ms)

        raise ValueError(f"unsupported simulator telephony event: {event!r}")

    def build_send_audio(self, command: SendAudioFrame) -> dict:
        command.validate_ready_to_send()
        self._validate_audio_format(command.format)
        return {
            "event": "media",
            "stream_sid": command.identity.require_stream_id(),
            "media": {
                "payload": base64.b64encode(command.payload).decode("ascii"),
            },
        }

    def build_clear_audio(self, command: ClearOutboundAudio) -> dict:
        command.validate_ready_to_send()
        return {
            "event": "clear",
            "stream_sid": command.identity.require_stream_id(),
        }

    def _parse_start(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TelephonyStreamStarted:
        identity = self._identity_from_payload(payload)
        if not identity.stream_id:
            raise ValueError("simulator start event missing stream id")
        self._validate_declared_media_format(payload)
        return TelephonyStreamStarted(
            type="telephony.stream_started",
            identity=identity,
            inbound_format=self.audio_format,
            outbound_format=self.audio_format,
            timestamps=self._timestamps(payload, backend_received_at_ms),
            raw_provider_event=payload,
        )

    def _parse_media(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TelephonyAudioFrame:
        identity = self._identity_from_payload(payload)
        encoded_audio = (payload.get("media") or {}).get("payload")
        if not encoded_audio:
            raise ValueError("simulator media event missing audio payload")
        return TelephonyAudioFrame(
            type="telephony.audio_frame",
            identity=identity,
            payload=base64.b64decode(encoded_audio),
            format=self.audio_format,
            sequence_number=self._sequence_number(payload),
            timestamps=self._timestamps(payload, backend_received_at_ms),
        )

    def _parse_dtmf(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TelephonyDtmf:
        digit = str((payload.get("dtmf") or {}).get("digit") or "")
        if not digit:
            raise ValueError("simulator dtmf event missing digit")
        return TelephonyDtmf(
            type="telephony.dtmf",
            identity=self._identity_from_payload(payload),
            digit=digit,
            timestamps=self._timestamps(payload, backend_received_at_ms),
        )

    def _parse_stop(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TelephonyStreamStopped:
        stop = payload.get("stop") or {}
        return TelephonyStreamStopped(
            type="telephony.stream_stopped",
            identity=self._identity_from_payload(payload),
            reason=stop.get("reason"),
            timestamps=self._timestamps(payload, backend_received_at_ms),
            raw_provider_event=payload,
        )

    def _coerce_message(self, message: str | dict) -> dict[str, Any]:
        if isinstance(message, str):
            parsed = json.loads(message)
        else:
            parsed = message
        if not isinstance(parsed, dict):
            raise ValueError("simulator message must be a JSON object")
        return parsed

    def _identity_from_payload(self, payload: dict[str, Any]) -> CallIdentity:
        start = payload.get("start") or {}
        custom_parameters = start.get("custom_parameters") or {}
        stream_id = (
            payload.get("stream_sid")
            or payload.get("streamSid")
            or start.get("stream_sid")
            or start.get("streamId")
        )
        provider_call_id = (
            start.get("call_sid")
            or start.get("callSid")
            or start.get("leg_sid")
            or payload.get("call_sid")
            or payload.get("callSid")
        )
        return CallIdentity(
            provider=self.provider,
            call_id=start.get("call_id") or payload.get("call_id"),
            resume_id=(
                start.get("resume_id")
                or custom_parameters.get("resume_id")
                or payload.get("resume_id")
            ),
            provider_call_id=provider_call_id,
            stream_id=stream_id,
        )

    def _timestamps(
        self,
        payload: dict[str, Any],
        backend_received_at_ms: int,
    ) -> TimestampMetadata:
        media = payload.get("media") or {}
        provider_timestamp = (
            media.get("timestamp")
            or payload.get("timestamp")
            or (payload.get("start") or {}).get("timestamp")
        )
        return TimestampMetadata(
            backend_received_at_ms=backend_received_at_ms,
            provider_timestamp_ms=self._optional_int(provider_timestamp),
            audio_offset_ms=self._optional_int(media.get("timestamp")),
        )

    def _sequence_number(self, payload: dict[str, Any]) -> int | None:
        media = payload.get("media") or {}
        return self._optional_int(
            payload.get("sequenceNumber")
            or payload.get("sequence_number")
            or media.get("chunk")
        )

    def _optional_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _validate_audio_format(self, audio_format: AudioFormat) -> None:
        if not audio_format.is_compatible_with(self.audio_format):
            raise ValueError(
                "simulator adapter expected linear16 8kHz mono audio, "
                f"got {audio_format}"
            )

    def _validate_declared_media_format(self, payload: dict[str, Any]) -> None:
        media_format = (payload.get("start") or {}).get("media_format") or {}
        if not media_format:
            return

        encoding = str(media_format.get("encoding") or "").lower()
        sample_rate = self._optional_int(media_format.get("sample_rate"))
        channels = self._optional_int(media_format.get("channels"))

        if encoding and encoding not in {"audio/l16", "linear16", "l16", "base64"}:
            raise ValueError(f"unsupported simulator media encoding: {encoding}")
        if sample_rate is not None and sample_rate != self.audio_format.sample_rate_hz:
            raise ValueError(f"unsupported simulator sample rate: {sample_rate}")
        if channels is not None and channels != self.audio_format.channels:
            raise ValueError(f"unsupported simulator channel count: {channels}")
