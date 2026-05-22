"""Phase 8 tests for call v2 session integration with fake providers."""

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
    SttError,
    SttTentativeEndpoint,
    TelephonyAudioFrame,
    TelephonyStreamStarted,
    TelephonyStreamStopped,
    TimestampMetadata,
)
from app.call_v2.persistence import FakeCallPersistence
from app.call_v2.session import CallSession, CallSessionConfig
from app.call_v2.state import CallRuntimeState
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter
from app.call_v2.tts.cache import InMemoryAudioCache
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.resolver import AudioSourceResolver
from app.call_v2.turns.endpointing import EndpointingSettings


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
                {
                    "id": "q1",
                    "text": "Tell me about a backend project you owned.",
                    "priority": 1,
                }
            ]
        },
        response_style=ResponseStyle(tone="professional"),
    )


def _session(
    *,
    agent_outputs: list[dict],
    tts_payload: bytes = b"\x00\x01" * 160,
):
    persistence = FakeCallPersistence()
    tts = FakeTtsEngine(payload=tts_payload)
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="call-1",
            initial_call_state=AgentVisibleCallState(
                phase="screening",
                consent_status="granted",
                open_items=["q1"],
            ),
            cache_policy_selector=lambda _output: CachePolicy(
                category="clarification_response"
            ),
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(
            provider="fake",
            input_format=LINEAR16_8K_MONO,
        ),
        agent_runner=FakeAgentRunner(outputs=agent_outputs),
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=tts,
        ),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    return session, persistence, tts


def _stream_started() -> TelephonyStreamStarted:
    identity = _identity()
    return TelephonyStreamStarted(
        type="telephony.stream_started",
        identity=identity,
        inbound_format=LINEAR16_8K_MONO,
        outbound_format=LINEAR16_8K_MONO,
        timestamps=TimestampMetadata(backend_received_at_ms=0),
    )


def _identity() -> CallIdentity:
    return CallIdentity(provider="browser", call_id="call-1", stream_id="stream-1")


def _final(
    text: str,
    *,
    generation_suffix: str = "a",
    start_ms: int = 1000,
    duration_ms: int = 500,
    received_at_ms: int = 100,
) -> SttFinalSegment:
    return SttFinalSegment(
        type="stt.final_segment",
        text=text,
        confidence=0.9,
        segment_id=f"segment-{generation_suffix}",
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=start_ms,
        ),
        duration_ms=duration_ms,
    )


def _endpoint(
    text: str,
    *,
    start_ms: int = 1000,
    duration_ms: int = 500,
    received_at_ms: int = 600,
) -> SttTentativeEndpoint:
    return SttTentativeEndpoint(
        type="stt.tentative_endpoint",
        text=text,
        confidence=0.9,
        silence_ms=500,
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=start_ms,
        ),
        duration_ms=duration_ms,
    )


def _audio_after_endpoint() -> TelephonyAudioFrame:
    return TelephonyAudioFrame(
        type="telephony.audio_frame",
        identity=_identity(),
        payload=b"\xff\x7f" * 160,
        format=LINEAR16_8K_MONO,
        sequence_number=2,
        timestamps=TimestampMetadata(
            backend_received_at_ms=700,
            audio_offset_ms=1600,
        ),
    )


def _silence_after_endpoint() -> TelephonyAudioFrame:
    return TelephonyAudioFrame(
        type="telephony.audio_frame",
        identity=_identity(),
        payload=b"\x00\x00" * 160,
        format=LINEAR16_8K_MONO,
        sequence_number=2,
        timestamps=TimestampMetadata(
            backend_received_at_ms=700,
            audio_offset_ms=1600,
        ),
    )


async def _start_stream(session: CallSession):
    await session.handle_telephony_event(_stream_started(), now_ms=0)


@pytest.mark.asyncio
async def test_session_normal_flow_reuses_speculative_agent_output_and_speaks():
    session, persistence, tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Thanks. What was the hardest part?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("I built APIs"), now_ms=100)
    tentative = await session.handle_stt_event(_endpoint("I built APIs"), now_ms=600)
    confirmed = await session.advance_time(700)

    assert tentative.outbound_audio_frames == []
    assert len(confirmed.outbound_audio_frames) == 1
    assert [turn.role for turn in persistence.turns] == ["user", "assistant"]
    assert persistence.turns[0].text == "I built APIs"
    assert persistence.turns[1].text == "Thanks. What was the hardest part?"
    assert len(tts.requests) == 1
    assert session.state_machine.state == CallRuntimeState.SPEAKING
    event_types = [item["event_type"] for item in session.trace.to_list()]
    assert "turn.tentative_started" in event_types
    assert "turn.confirmed" in event_types
    assert "audio.source_selected" in event_types


@pytest.mark.asyncio
async def test_session_runtime_opener_commits_assistant_context_without_user_turn():
    session, persistence, _tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Hi, this is a screening call. May I continue?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_stream(session)

    result = await session.start_runtime_opener(now_ms=50)

    assert len(result.outbound_audio_frames) == 1
    assert [turn.role for turn in persistence.turns] == ["assistant"]
    assert persistence.turns[0].text == "Hi, this is a screening call. May I continue?"
    assert [message.role for message in session.conversation] == ["assistant"]


@pytest.mark.asyncio
async def test_session_cancels_speculation_when_candidate_continues():
    session, persistence, tts = _session(
        agent_outputs=[
            {
                "spoken_text": "This speculative result must not speak.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("I built APIs"), now_ms=100)
    await session.handle_stt_event(_endpoint("I built APIs"), now_ms=600)
    cancelled = await session.handle_telephony_event(_audio_after_endpoint(), now_ms=700)

    assert cancelled.outbound_audio_frames == []
    assert persistence.turns == []
    assert tts.requests == []
    assert 1 in tts.cancelled_generation_ids
    assert session.state_machine.state == CallRuntimeState.LISTENING
    event_types = [item["event_type"] for item in session.trace.to_list()]
    assert "turn.tentative_cancelled" in event_types


@pytest.mark.asyncio
async def test_session_does_not_cancel_speculation_for_silence_media_frame():
    session, persistence, tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Thanks. What was hard?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("I built APIs"), now_ms=100)
    await session.handle_stt_event(_endpoint("I built APIs"), now_ms=600)
    await session.handle_telephony_event(_silence_after_endpoint(), now_ms=700)
    confirmed = await session.advance_time(800)

    assert len(confirmed.outbound_audio_frames) == 1
    assert [turn.role for turn in persistence.turns] == ["user", "assistant"]
    assert len(tts.requests) == 1


@pytest.mark.asyncio
async def test_session_uses_new_generation_after_stale_speculative_result():
    session, persistence, tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Stale response.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
            {
                "spoken_text": "Fresh response.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("I built APIs", generation_suffix="a"), now_ms=100)
    await session.handle_stt_event(_endpoint("I built APIs"), now_ms=600)
    await session.handle_telephony_event(_audio_after_endpoint(), now_ms=700)
    await session.handle_stt_event(
        _final(
            "I built APIs and workers",
            generation_suffix="b",
            start_ms=1000,
            duration_ms=900,
            received_at_ms=800,
        ),
        now_ms=800,
    )
    await session.handle_stt_event(
        _endpoint(
            "I built APIs and workers",
            start_ms=1000,
            duration_ms=900,
            received_at_ms=900,
        ),
        now_ms=900,
    )
    result = await session.advance_time(1000)

    assert len(result.outbound_audio_frames) == 1
    assert [turn.text for turn in persistence.turns] == [
        "I built APIs and workers",
        "Fresh response.",
    ]
    assert len(tts.requests) == 1


@pytest.mark.asyncio
async def test_session_clears_tts_on_transcript_barge_in():
    session, _persistence, tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Let me ask the next question now.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            }
        ]
    )
    await _start_stream(session)
    await session.handle_stt_event(_final("yes", duration_ms=150), now_ms=100)
    await session.handle_stt_event(_endpoint("yes", duration_ms=150), now_ms=600)
    await session.advance_time(700)

    barge_in = await session.handle_stt_event(
        _final(
            "Actually can you repeat that?",
            generation_suffix="barge",
            start_ms=2000,
            duration_ms=500,
            received_at_ms=750,
        ),
        now_ms=750,
    )

    assert len(barge_in.clear_audio_commands) == 1
    assert barge_in.clear_audio_commands[0].reason == "candidate_barge_in"
    assert 1 in tts.cancelled_generation_ids
    assert session.state_machine.state == CallRuntimeState.LISTENING


@pytest.mark.asyncio
async def test_session_end_call_action_ends_after_tts_completion():
    session, _persistence, _tts = _session(
        agent_outputs=[
            {
                "spoken_text": "Thanks for your time. Goodbye.",
                "action": "end_call_after_speaking",
                "tool_calls": [],
                "state_updates": {"call_complete": True},
            }
        ]
    )
    await _start_stream(session)
    await session.handle_stt_event(_final("no thanks"), now_ms=100)
    await session.handle_stt_event(_endpoint("no thanks"), now_ms=600)
    result = await session.advance_time(700)

    assert result.end_call is True
    assert session.state_machine.state == CallRuntimeState.SPEAKING

    await session.complete_tts(now_ms=900)

    assert session.state_machine.state == CallRuntimeState.ENDED


@pytest.mark.asyncio
async def test_session_provider_stop_closes_stt_and_ends():
    session, _persistence, _tts = _session(agent_outputs=[])
    await _start_stream(session)

    result = await session.handle_telephony_event(
        TelephonyStreamStopped(
            type="telephony.stream_stopped",
            identity=_identity(),
            reason="caller_hangup",
            timestamps=TimestampMetadata(backend_received_at_ms=1000),
        ),
        now_ms=1000,
    )

    assert result.end_call is True
    assert session.stt_engine.closed is True
    assert session.state_machine.state == CallRuntimeState.ENDED


@pytest.mark.asyncio
async def test_session_unrecoverable_stt_error_ends_call():
    session, _persistence, _tts = _session(agent_outputs=[])
    await _start_stream(session)

    result = await session.handle_stt_event(
        SttError(
            type="stt.error",
            provider="deepgram",
            code="connect_failed",
            message="could not connect",
            recoverable=False,
            timestamps=TimestampMetadata(backend_received_at_ms=100),
        ),
        now_ms=100,
    )

    assert result.end_call is True
    assert session.stt_engine.closed is True
    assert session.state_machine.state == CallRuntimeState.ENDED
