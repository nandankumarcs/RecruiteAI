"""Exotel-profile simulator regression tests.

Each test encodes a failure discovered during live Exotel testing so that
simulator gates must pass before another live Exotel call is placed.

See: docs/call-v2/07-testing-and-simulator-plan.md §Gate 8
     handoff: /tmp/recruiteai-call-v2-handoff-2026-05-22.md §Live Exotel Findings
"""

from __future__ import annotations

import base64

import pytest

from app.call_v2.agent.config import (
    AgentConfig,
    AgentVisibleCallState,
    CallScope,
    ResponseStyle,
)
from app.call_v2.agent.fake import FakeAgentRunner
from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import (
    CallIdentity,
    SttFinalSegment,
    SttSpeechStarted,
    SttTentativeEndpoint,
    TelephonyAudioFrame,
    TelephonyStreamStarted,
    TimestampMetadata,
)
from app.call_v2.persistence import FakeCallPersistence
from app.call_v2.session import CallSession, CallSessionConfig
from app.call_v2.state import CallRuntimeState
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.telephony.exotel import ExotelMediaTelephonyAdapter
from app.call_v2.tts.cache import InMemoryAudioCache
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.resolver import AudioSourceResolver
from app.call_v2.turns.endpointing import EndpointingSettings


# ---------------------------------------------------------------------------
# Fixtures: Exotel live payload shapes
# ---------------------------------------------------------------------------


def _exotel_start_payload(
    *,
    stream_sid: str = "exo-stream-live",
    resume_id: str = "voice/00000000-0000-0000-0000-000000000001",
) -> dict:
    """Full live Exotel start payload shape discovered during Phase 11 testing.

    Key details:
    - stream_sid appears at top level AND inside start.stream_sid
    - leg_sid, account_sid, from, to are all present
    - custom_parameters uses a "key-only" shape where the resume path is the KEY
      with an empty-string value (Exotel-specific encoding)
    - media_format.encoding is "base64" (not "audio/l16") even though the actual
      payload is base64-encoded L16 8 kHz audio
    - media_format includes bit_rate which is not part of the audio format contract
    """
    return {
        "event": "start",
        "stream_sid": stream_sid,
        "sequence_number": "1",
        "start": {
            "stream_sid": stream_sid,
            "call_sid": "EXOTEL-CALL-SID-TEST",
            "leg_sid": "EXOTEL-LEG-SID-TEST",
            "account_sid": "EXOTEL-ACCOUNT-SID-TEST",
            "from": "+91XXXXXXXXXX",
            "to": "+91YYYYYYYYYY",
            "custom_parameters": {resume_id: ""},
            "media_format": {
                "encoding": "base64",
                "sample_rate": 8000,
                "bit_rate": "128kbps",
            },
        },
    }


def _exotel_media_frame(
    *,
    stream_sid: str = "exo-stream-live",
    timestamp: int = 2000,
    sequence: int = 2,
    active: bool = True,
) -> dict:
    """Exotel media frame as sent after endpointing (continuous stream)."""
    payload = b"\xff\x7f" * 160 if active else b"\x00\x00" * 160
    return {
        "event": "media",
        "stream_sid": stream_sid,
        "sequenceNumber": str(sequence),
        "media": {
            "payload": base64.b64encode(payload).decode("ascii"),
            "timestamp": str(timestamp),
            "chunk": str(sequence),
        },
    }


# ---------------------------------------------------------------------------
# Session factory: Exotel profile
# ---------------------------------------------------------------------------


def _agent_config() -> AgentConfig:
    return AgentConfig(
        agent_name="Recruiting Call Agent",
        instructions="Conduct a concise screening call using the provided scope.",
        scope=CallScope(
            purpose="Screen a candidate for a backend engineer role.",
            allowed_topics=["technical experience", "role fit"],
            disallowed_topics=["medical advice"],
            compliance_notes=["Ask one thing at a time."],
            success_criteria=["Collect enough signal for evaluation."],
        ),
        context={
            "questions": [
                {"id": "q1", "text": "Tell me about a backend project you owned.", "priority": 1}
            ]
        },
        response_style=ResponseStyle(tone="professional"),
    )


def _exotel_session(*, agent_outputs: list[dict], tts_payload: bytes = b"\x00\x01" * 160):
    """Session wired with ExotelMediaTelephonyAdapter and the Exotel-specific config."""
    persistence = FakeCallPersistence()
    tts = FakeTtsEngine(payload=tts_payload)
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="exotel-call-live",
            initial_call_state=AgentVisibleCallState(
                phase="screening",
                consent_status="pending",
                open_items=["q1"],
            ),
            cache_policy_selector=lambda _output: CachePolicy(
                category="clarification_response"
            ),
            raw_audio_cancels_tentative_turns=False,  # Exotel fix from Phase 11
        ),
        telephony_adapter=ExotelMediaTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="deepgram", input_format=LINEAR16_8K_MONO),
        agent_runner=FakeAgentRunner(outputs=agent_outputs),
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=tts,
        ),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    return session, persistence, tts


async def _start_exotel_stream(session: CallSession, stream_sid: str = "exo-stream-live") -> None:
    await session.handle_telephony_message(
        _exotel_start_payload(stream_sid=stream_sid),
        now_ms=0,
    )


def _consent_final(*, received_at_ms: int = 100) -> SttFinalSegment:
    return SttFinalSegment(
        type="stt.final_segment",
        text="Yes. Go ahead.",
        confidence=0.95,
        segment_id="seg-consent",
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=500,
        ),
        duration_ms=800,
    )


def _consent_endpoint(*, received_at_ms: int = 600) -> SttTentativeEndpoint:
    return SttTentativeEndpoint(
        type="stt.tentative_endpoint",
        text="Yes. Go ahead.",
        confidence=0.95,
        silence_ms=500,
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=500,
        ),
        duration_ms=800,
    )


# ---------------------------------------------------------------------------
# Test 1: Exotel live start payload shape
# ---------------------------------------------------------------------------


def test_exotel_adapter_parses_full_live_start_payload_shape():
    """Adapter accepts the exact Exotel live start payload including all live fields."""
    adapter = ExotelMediaTelephonyAdapter()
    stream_sid = "exo-stream-live"
    resume_path = "voice/00000000-0000-0000-0000-000000000001"

    event = adapter.parse_inbound_message(
        _exotel_start_payload(stream_sid=stream_sid, resume_id=resume_path),
        backend_received_at_ms=10,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider == "exotel"
    assert event.identity.stream_id == stream_sid
    assert event.identity.provider_call_id == "EXOTEL-CALL-SID-TEST"
    assert event.inbound_format == LINEAR16_8K_MONO
    assert event.outbound_format == LINEAR16_8K_MONO
    assert event.timestamps.backend_received_at_ms == 10


def test_exotel_adapter_accepts_base64_encoding_declaration_in_live_start():
    """base64 encoding declaration in media_format.encoding must not raise."""
    adapter = ExotelMediaTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {
            "event": "start",
            "stream_sid": "exo-1",
            "start": {
                "stream_sid": "exo-1",
                "call_sid": "CALL-1",
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": 8000,
                    "bit_rate": "128kbps",
                },
            },
        },
        backend_received_at_ms=5,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider == "exotel"


def test_exotel_adapter_accepts_leg_sid_as_provider_call_id():
    """leg_sid is treated as the provider call id when call_sid is absent."""
    adapter = ExotelMediaTelephonyAdapter()

    event = adapter.parse_inbound_message(
        {
            "event": "start",
            "stream_sid": "exo-2",
            "start": {
                "stream_sid": "exo-2",
                "leg_sid": "LEG-SID-ONLY",
                "media_format": {
                    "encoding": "base64",
                    "sample_rate": 8000,
                },
            },
        },
        backend_received_at_ms=5,
    )

    assert isinstance(event, TelephonyStreamStarted)
    assert event.identity.provider_call_id == "LEG-SID-ONLY"


# ---------------------------------------------------------------------------
# Test 2: Continuous post-endpoint Exotel media frames must NOT cancel turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exotel_continuous_media_after_endpoint_does_not_cancel_turn():
    """Critical regression: Exotel sends continuous media frames after Deepgram endpointing.

    With raw_audio_cancels_tentative_turns=False, those frames must not trip
    audio_after_tentative cancellation. The turn must confirm and persist.
    """
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "Great. Can you tell me about a backend project?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_exotel_stream(session)

    await session.handle_stt_event(_consent_final(), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(), now_ms=600)

    # Exotel sends several media frames continuously after Deepgram endpointed.
    # These must NOT cancel the tentative turn.
    for seq, ts in [(2, 1800), (3, 2000), (4, 2200), (5, 2400)]:
        result = await session.handle_telephony_message(
            _exotel_media_frame(timestamp=ts, sequence=seq, active=True),
            now_ms=ts // 2,
        )
        assert result.outbound_audio_frames == [], (
            f"media frame {seq} should not produce outbound audio"
        )

    # Advance past confirmation deadline → turn must confirm.
    result = await session.advance_time(900)

    trace_types = [item["event_type"] for item in session.trace.to_list()]
    assert "turn.confirmed" in trace_types, "turn must confirm despite continuous Exotel media"
    assert "turn.tentative_cancelled" not in trace_types, (
        "media frames must not cancel tentative turn for Exotel profile"
    )
    assert len(result.outbound_audio_frames) == 1, "assistant audio must be generated"
    assert [t.role for t in persistence.turns] == ["user", "assistant"]
    assert persistence.turns[0].text == "Yes. Go ahead."
    assert session.state_machine.state == CallRuntimeState.SPEAKING


@pytest.mark.asyncio
async def test_exotel_turn_does_not_confirm_when_audio_cancellation_is_enabled():
    """Sanity check: with raw_audio_cancels_tentative_turns=True (browser default),
    high-energy audio after endpoint DOES cancel the tentative turn."""
    persistence = FakeCallPersistence()
    tts = FakeTtsEngine(payload=b"\x00\x01" * 160)
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="browser-call",
            initial_call_state=AgentVisibleCallState(
                phase="screening",
                consent_status="pending",
                open_items=["q1"],
            ),
            raw_audio_cancels_tentative_turns=True,  # browser default
        ),
        telephony_adapter=ExotelMediaTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=FakeAgentRunner(outputs=[
            {
                "spoken_text": "Speculative output — must be discarded.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]),
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=tts,
        ),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    await session.handle_telephony_message(
        _exotel_start_payload(),
        now_ms=0,
    )

    await session.handle_stt_event(_consent_final(), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(), now_ms=600)

    # High-energy frame after tentative endpoint.
    await session.handle_telephony_message(
        _exotel_media_frame(timestamp=1800, sequence=2, active=True),
        now_ms=700,
    )

    trace_types = [item["event_type"] for item in session.trace.to_list()]
    assert "turn.tentative_cancelled" in trace_types, (
        "with raw_audio_cancels=True, high-energy post-endpoint audio must cancel"
    )


# ---------------------------------------------------------------------------
# Test 3: Candidate continuation is driven by STT events, not raw audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exotel_stt_speech_started_cancels_tentative_turn():
    """When raw audio cancellation is disabled, stt.speech_started must cancel
    the tentative turn to handle candidate continuation correctly."""
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "Should not speak — speculative.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
            {
                "spoken_text": "Got it. Tell me about the hardest part.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    await _start_exotel_stream(session)

    # First tentative endpoint
    await session.handle_stt_event(_consent_final(), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(), now_ms=600)

    # STT detects new speech — must cancel via STT, not via raw audio
    result = await session.handle_stt_event(
        SttSpeechStarted(
            type="stt.speech_started",
            timestamps=TimestampMetadata(backend_received_at_ms=650),
        ),
        now_ms=650,
    )

    trace_types = [item["event_type"] for item in session.trace.to_list()]
    assert "turn.tentative_cancelled" in trace_types
    cancelled_events = [
        item for item in session.trace.to_list()
        if item["event_type"] == "turn.tentative_cancelled"
    ]
    assert cancelled_events[0]["data"]["reason"] == "speech_started_after_tentative"
    assert result.outbound_audio_frames == []
    assert persistence.turns == []
    assert session.state_machine.state == CallRuntimeState.LISTENING


@pytest.mark.asyncio
async def test_exotel_new_stt_final_after_tentative_replaces_and_confirms():
    """A new STT final segment after tentative endpoint cancels and replaces the
    pending turn via the STT path. The continued text is eventually confirmed."""
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "Stale result — must not speak.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
            {
                "spoken_text": "Thanks for the full answer.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    await _start_exotel_stream(session)

    # First tentative endpoint A
    await session.handle_stt_event(_consent_final(received_at_ms=100), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(received_at_ms=600), now_ms=600)

    # Candidate continues — new final segment with changed text cancels via STT
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="Yes. Go ahead. I am happy to proceed.",
            confidence=0.92,
            segment_id="seg-continuation",
            timestamps=TimestampMetadata(backend_received_at_ms=700, audio_offset_ms=1500),
            duration_ms=1200,
        ),
        now_ms=700,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="Yes. Go ahead. I am happy to proceed.",
            confidence=0.92,
            silence_ms=500,
            timestamps=TimestampMetadata(backend_received_at_ms=900, audio_offset_ms=1500),
            duration_ms=1200,
        ),
        now_ms=900,
    )
    result = await session.advance_time(1200)

    assert len(result.outbound_audio_frames) == 1
    assert [t.role for t in persistence.turns] == ["user", "assistant"]
    assert "I am happy to proceed" in persistence.turns[0].text
    assert persistence.turns[1].text == "Thanks for the full answer."
    assert session.state_machine.state == CallRuntimeState.SPEAKING


# ---------------------------------------------------------------------------
# Test 4: Post-TTS immediate speech is captured (Exotel profile)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exotel_candidate_speech_immediately_after_tts_is_captured():
    """Candidate starts speaking shortly after TTS completes. The turn must be
    captured even with the post_tts_guard active."""
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "May I ask you about your backend experience?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
            {
                "spoken_text": "Great. Tell me more about that system.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    await _start_exotel_stream(session)

    # First turn: consent
    await session.handle_stt_event(_consent_final(), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(), now_ms=600)
    first_result = await session.advance_time(900)
    assert len(first_result.outbound_audio_frames) == 1
    assert session.state_machine.state == CallRuntimeState.SPEAKING

    # TTS completes
    await session.complete_tts(now_ms=1500)
    assert session.state_machine.state == CallRuntimeState.POST_TTS_GUARD

    # Candidate speaks immediately after TTS — STT events arrive quickly
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="Yes I have built many backend systems.",
            confidence=0.91,
            segment_id="seg-post-tts",
            timestamps=TimestampMetadata(backend_received_at_ms=1600, audio_offset_ms=3000),
            duration_ms=1500,
        ),
        now_ms=1600,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="Yes I have built many backend systems.",
            confidence=0.91,
            silence_ms=500,
            timestamps=TimestampMetadata(backend_received_at_ms=1700, audio_offset_ms=3000),
            duration_ms=1500,
        ),
        now_ms=1700,
    )
    result = await session.advance_time(2000)

    assert len(result.outbound_audio_frames) == 1
    assert len(persistence.turns) == 4  # opener(assistant) + 2nd-turn user + assistant + 3rd-turn user + assistant
    user_turns = [t for t in persistence.turns if t.role == "user"]
    assert any("backend systems" in t.text for t in user_turns)
    assert session.state_machine.state == CallRuntimeState.SPEAKING


# ---------------------------------------------------------------------------
# Test 5: Clarification request uses live TTS (Exotel profile)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exotel_clarification_request_uses_live_tts_path():
    """Candidate asks for question clarification. Agent must explain naturally
    via live TTS; the cache must not interfere with the explanation path."""
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "Of course! The question is about a system you designed end-to-end.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_exotel_stream(session)

    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="Sorry, can you explain the question?",
            confidence=0.90,
            segment_id="seg-clarify",
            timestamps=TimestampMetadata(backend_received_at_ms=100, audio_offset_ms=500),
            duration_ms=900,
        ),
        now_ms=100,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="Sorry, can you explain the question?",
            confidence=0.90,
            silence_ms=500,
            timestamps=TimestampMetadata(backend_received_at_ms=600, audio_offset_ms=500),
            duration_ms=900,
        ),
        now_ms=600,
    )
    result = await session.advance_time(800)

    assert len(result.outbound_audio_frames) == 1
    assert [t.role for t in persistence.turns] == ["user", "assistant"]
    assert "question" in persistence.turns[1].text.lower()
    assert len(tts.requests) == 1, "explanation must go through live TTS"
    assert session.state_machine.state == CallRuntimeState.SPEAKING
    trace_types = [item["event_type"] for item in session.trace.to_list()]
    assert "audio.source_selected" in trace_types


# ---------------------------------------------------------------------------
# Test 6: Barge-in under Exotel profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exotel_barge_in_clears_audio_and_captures_candidate_turn():
    """Candidate interrupts assistant mid-TTS. A clear audio command must be sent,
    the stale generation cancelled, and the candidate turn processed normally."""
    session, persistence, tts = _exotel_session(
        agent_outputs=[
            {
                "spoken_text": "Certainly, let me walk you through the next question.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
            {
                "spoken_text": "No problem. Please go ahead.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    await _start_exotel_stream(session)

    # First turn completes — assistant is speaking
    await session.handle_stt_event(_consent_final(), now_ms=100)
    await session.handle_stt_event(_consent_endpoint(), now_ms=600)
    await session.advance_time(900)
    assert session.state_machine.state == CallRuntimeState.SPEAKING

    # Candidate interrupts with a new STT final while assistant is speaking
    barge_in_result = await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="Wait, I wanted to add something.",
            confidence=0.88,
            segment_id="seg-barge",
            timestamps=TimestampMetadata(backend_received_at_ms=950, audio_offset_ms=2000),
            duration_ms=700,
        ),
        now_ms=950,
    )

    # Clear outbound audio command must be issued
    assert len(barge_in_result.clear_audio_commands) == 1
    assert barge_in_result.clear_audio_commands[0].reason == "candidate_barge_in"

    # Generation must be cancelled
    assert len(tts.cancelled_generation_ids) > 0

    # State must return to LISTENING to process barge-in turn
    assert session.state_machine.state == CallRuntimeState.LISTENING

    # Now barge-in text leads to a tentative turn — confirm it
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="Wait, I wanted to add something.",
            confidence=0.88,
            silence_ms=500,
            timestamps=TimestampMetadata(backend_received_at_ms=1000, audio_offset_ms=2000),
            duration_ms=700,
        ),
        now_ms=1000,
    )
    result = await session.advance_time(1200)

    assert len(result.outbound_audio_frames) == 1
    user_turns = [t for t in persistence.turns if t.role == "user"]
    assert any("add something" in t.text for t in user_turns)
    assert session.state_machine.state == CallRuntimeState.SPEAKING
