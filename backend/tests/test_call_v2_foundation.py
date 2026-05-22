"""Phase 1 tests for call v2 foundation contracts."""

import pytest

from app.call_v2.events import (
    AudioFormat,
    CallIdentity,
    SendAudioFrame,
    TelephonyAudioFrame,
    TimestampMetadata,
)
from app.call_v2.ids import GenerationIdManager
from app.call_v2.state import (
    CallRuntimeState,
    CallStateMachine,
    InvalidStateTransition,
)
from app.call_v2.trace import TraceLogger


def test_audio_frame_serialization_summarizes_raw_audio_payload():
    event = TelephonyAudioFrame(
        type="telephony.audio_frame",
        identity=CallIdentity(provider="exotel", stream_id="stream-1"),
        payload=b"123456",
        format=AudioFormat(codec="linear16"),
        sequence_number=7,
        timestamps=TimestampMetadata(backend_received_at_ms=100),
    )

    payload = event.to_dict()

    assert payload["type"] == "telephony.audio_frame"
    assert payload["payload"] == {"encoding": "base64", "byte_length": 6}
    assert payload["identity"]["provider"] == "exotel"
    assert payload["format"]["codec"] == "linear16"


def test_send_audio_requires_stream_id_before_provider_write():
    command = SendAudioFrame(
        type="telephony.send_audio_frame",
        identity=CallIdentity(provider="exotel", stream_id=None),
        payload=b"audio",
        format=AudioFormat(codec="linear16"),
        generation_id=1,
        is_first_frame=True,
        is_final_frame=False,
    )

    with pytest.raises(ValueError, match="stream_id is required"):
        command.validate_ready_to_send()


def test_audio_format_compatibility_is_exact():
    exotel_format = AudioFormat(codec="linear16", sample_rate_hz=8000)
    twilio_format = AudioFormat(codec="mulaw", sample_rate_hz=8000)
    other_rate = AudioFormat(codec="linear16", sample_rate_hz=16000)

    assert exotel_format.is_compatible_with(AudioFormat(codec="linear16"))
    assert not exotel_format.is_compatible_with(twilio_format)
    assert not exotel_format.is_compatible_with(other_rate)


def test_call_state_machine_allows_happy_path_transitions():
    machine = CallStateMachine()

    machine.transition_to(
        CallRuntimeState.WAITING_FOR_STREAM,
        reason="context loaded",
    )
    machine.transition_to(CallRuntimeState.LISTENING, reason="stream started")
    machine.transition_to(
        CallRuntimeState.SPECULATING,
        reason="tentative endpoint",
    )
    machine.transition_to(CallRuntimeState.AGENT_RUNNING, reason="turn confirmed")
    machine.transition_to(CallRuntimeState.SPEAKING, reason="agent result ready")
    machine.transition_to(CallRuntimeState.POST_TTS_GUARD, reason="tts complete")
    machine.transition_to(CallRuntimeState.LISTENING, reason="guard expired")
    machine.transition_to(CallRuntimeState.ENDING, reason="provider stopped")
    machine.transition_to(CallRuntimeState.ENDED, reason="cleanup complete")

    assert machine.state == CallRuntimeState.ENDED
    assert [item.reason for item in machine.history] == [
        "context loaded",
        "stream started",
        "tentative endpoint",
        "turn confirmed",
        "agent result ready",
        "tts complete",
        "guard expired",
        "provider stopped",
        "cleanup complete",
    ]


def test_call_state_machine_rejects_illegal_transition():
    machine = CallStateMachine()

    with pytest.raises(InvalidStateTransition):
        machine.transition_to(CallRuntimeState.SPEAKING, reason="too early")


def test_generation_manager_blocks_stale_or_unconfirmed_generations_from_speaking():
    manager = GenerationIdManager()

    generation_1 = manager.start_generation()
    generation_2 = manager.start_generation()

    manager.mark_stale(generation_1)
    manager.mark_confirmed(generation_2)

    assert not manager.can_speak(generation_1)
    assert manager.can_speak(generation_2)
    with pytest.raises(ValueError, match="cannot confirm stale generation"):
        manager.mark_confirmed(generation_1)


def test_generation_manager_rejects_unknown_generation_confirmation():
    manager = GenerationIdManager()

    with pytest.raises(ValueError, match="unknown generation"):
        manager.mark_confirmed(1)

    manager.start_generation()

    with pytest.raises(ValueError, match="unknown generation"):
        manager.mark_confirmed(99)

    with pytest.raises(ValueError, match="unknown generation"):
        manager.mark_stale(99)


def test_trace_logger_emits_ordered_redacted_events():
    logger = TraceLogger(trace_id="trace-1")

    logger.emit(
        "agent.run_started",
        call_id="call-1",
        generation_id=3,
        data={
            "Authorization": "Bearer secret",
            "nested": {"api_key": "secret-key", "safe": "value"},
        },
        at_ms=10,
    )
    logger.emit("agent.run_completed", call_id="call-1", generation_id=3, at_ms=20)

    events = logger.to_list()

    assert [event["event_type"] for event in events] == [
        "agent.run_started",
        "agent.run_completed",
    ]
    assert events[0]["trace_id"] == "trace-1"
    assert events[0]["data"]["Authorization"] == "[REDACTED]"
    assert events[0]["data"]["nested"]["api_key"] == "[REDACTED]"
    assert events[0]["data"]["nested"]["safe"] == "value"
    assert events[1]["monotonic_ms"] == 20
