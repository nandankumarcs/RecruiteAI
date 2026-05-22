"""Phase 2 tests for call v2 telephony adapters."""

import base64
import json

import pytest

from app.call_v2.events import (
    AudioFormat,
    CallIdentity,
    ClearOutboundAudio,
    SendAudioFrame,
    TelephonyAudioFrame,
    TelephonyDtmf,
    TelephonyStreamStarted,
    TelephonyStreamStopped,
)
from app.call_v2.telephony.exotel import ExotelMediaTelephonyAdapter
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter


def test_simulator_adapter_ignores_connected_lifecycle_event():
    adapter = BrowserSimulatorTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {"event": "connected"},
        backend_received_at_ms=10,
    )

    assert event is None


def test_simulator_adapter_parses_start_event_to_stream_started():
    adapter = BrowserSimulatorTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {
            "event": "start",
            "start": {
                "stream_sid": "stream-1",
                "call_sid": "SIM-1",
                "call_id": "call-1",
                "custom_parameters": {"resume_id": "resume-1"},
                "timestamp": "123",
                "media_format": {
                    "encoding": "audio/L16",
                    "sample_rate": 8000,
                    "channels": 1,
                },
            },
        },
        backend_received_at_ms=20,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider == "browser"
    assert event.identity.stream_id == "stream-1"
    assert event.identity.provider_call_id == "SIM-1"
    assert event.identity.call_id == "call-1"
    assert event.identity.resume_id == "resume-1"
    assert event.inbound_format == AudioFormat(codec="linear16")
    assert event.outbound_format == AudioFormat(codec="linear16")
    assert event.timestamps.backend_received_at_ms == 20
    assert event.timestamps.provider_timestamp_ms == 123


def test_simulator_adapter_parses_media_json_string_to_audio_frame():
    adapter = BrowserSimulatorTelephonyAdapter()
    audio = b"\x01\x02\x03\x04"
    encoded = base64.b64encode(audio).decode("ascii")

    event = adapter.parse_inbound_message(
        json.dumps(
            {
                "event": "media",
                "stream_sid": "stream-1",
                "sequenceNumber": "9",
                "media": {"payload": encoded, "timestamp": "456"},
            }
        ),
        backend_received_at_ms=30,
    )

    assert isinstance(event, TelephonyAudioFrame)
    assert event.identity.stream_id == "stream-1"
    assert event.payload == audio
    assert event.sequence_number == 9
    assert event.format == AudioFormat(codec="linear16")
    assert event.timestamps.provider_timestamp_ms == 456
    assert event.timestamps.audio_offset_ms == 456


def test_simulator_adapter_parses_dtmf_and_stop_events():
    adapter = BrowserSimulatorTelephonyAdapter()

    dtmf_event = adapter.parse_inbound_message(
        {"event": "dtmf", "stream_sid": "stream-1", "dtmf": {"digit": "5"}},
        backend_received_at_ms=40,
    )
    stop_event = adapter.parse_inbound_message(
        {
            "event": "stop",
            "stream_sid": "stream-1",
            "stop": {"reason": "candidate_hangup"},
        },
        backend_received_at_ms=50,
    )

    assert isinstance(dtmf_event, TelephonyDtmf)
    assert dtmf_event.digit == "5"
    assert isinstance(stop_event, TelephonyStreamStopped)
    assert stop_event.reason == "candidate_hangup"
    assert stop_event.identity.stream_id == "stream-1"


def test_simulator_adapter_rejects_start_without_stream_id():
    adapter = BrowserSimulatorTelephonyAdapter()

    with pytest.raises(ValueError, match="missing stream id"):
        adapter.parse_inbound_message(
            {"event": "start", "start": {"call_sid": "SIM-1"}},
            backend_received_at_ms=10,
        )


def test_simulator_adapter_rejects_incompatible_declared_media_format():
    adapter = BrowserSimulatorTelephonyAdapter()

    with pytest.raises(ValueError, match="unsupported simulator sample rate"):
        adapter.parse_inbound_message(
            {
                "event": "start",
                "start": {
                    "stream_sid": "stream-1",
                    "media_format": {
                        "encoding": "audio/L16",
                        "sample_rate": 16000,
                        "channels": 1,
                    },
                },
            },
            backend_received_at_ms=10,
        )


def test_simulator_adapter_rejects_media_without_payload():
    adapter = BrowserSimulatorTelephonyAdapter()

    with pytest.raises(ValueError, match="missing audio payload"):
        adapter.parse_inbound_message(
            {"event": "media", "stream_sid": "stream-1", "media": {}},
            backend_received_at_ms=10,
        )


def test_simulator_adapter_rejects_unknown_event():
    adapter = BrowserSimulatorTelephonyAdapter()

    with pytest.raises(ValueError, match="unsupported simulator telephony event"):
        adapter.parse_inbound_message(
            {"event": "mystery"},
            backend_received_at_ms=10,
        )


def test_simulator_adapter_builds_outbound_audio_message():
    adapter = BrowserSimulatorTelephonyAdapter()
    command = SendAudioFrame(
        type="telephony.send_audio_frame",
        identity=CallIdentity(provider="browser", stream_id="stream-1"),
        payload=b"\x05\x06",
        format=AudioFormat(codec="linear16"),
        generation_id=7,
        is_first_frame=True,
        is_final_frame=False,
    )

    message = adapter.build_send_audio(command)

    assert message == {
        "event": "media",
        "stream_sid": "stream-1",
        "media": {"payload": base64.b64encode(b"\x05\x06").decode("ascii")},
    }


def test_simulator_adapter_rejects_wrong_outbound_audio_format():
    adapter = BrowserSimulatorTelephonyAdapter()
    command = SendAudioFrame(
        type="telephony.send_audio_frame",
        identity=CallIdentity(provider="browser", stream_id="stream-1"),
        payload=b"\x05\x06",
        format=AudioFormat(codec="mulaw"),
        generation_id=7,
        is_first_frame=True,
        is_final_frame=False,
    )

    with pytest.raises(ValueError, match="expected linear16"):
        adapter.build_send_audio(command)


def test_simulator_adapter_builds_clear_audio_message():
    adapter = BrowserSimulatorTelephonyAdapter()
    command = ClearOutboundAudio(
        type="telephony.clear_outbound_audio",
        identity=CallIdentity(provider="browser", stream_id="stream-1"),
        generation_id=7,
        reason="barge_in",
    )

    assert adapter.build_clear_audio(command) == {
        "event": "clear",
        "stream_sid": "stream-1",
    }


def test_exotel_adapter_uses_same_l16_shape_with_exotel_identity():
    adapter = ExotelMediaTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {
            "event": "start",
            "start": {
                "stream_sid": "exo-stream-1",
                "call_sid": "exo-call-1",
                "custom_parameters": {"resume_id": "resume-1"},
            },
        },
        backend_received_at_ms=10,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider == "exotel"
    assert event.identity.stream_id == "exo-stream-1"
    assert event.identity.provider_call_id == "exo-call-1"
    assert event.identity.resume_id == "resume-1"


def test_exotel_adapter_accepts_live_base64_media_format_declaration():
    adapter = ExotelMediaTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {
            "event": "start",
            "stream_sid": "exo-stream-1",
            "start": {
                "stream_sid": "exo-stream-1",
                "call_sid": "exo-call-1",
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": 8000,
                    "channels": 1,
                },
            },
        },
        backend_received_at_ms=10,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider == "exotel"
