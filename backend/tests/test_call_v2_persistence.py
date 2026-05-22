"""Phase 9 tests for call v2 database persistence."""

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from app.call_v2.agent.config import (
    AgentConfig,
    AgentVisibleCallState,
    CallScope,
    ResponseStyle,
)
from app.call_v2.agent.fake import FakeAgentRunner
from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import (
    SttFinalSegment,
    SttTentativeEndpoint,
    TimestampMetadata,
)
from app.call_v2.persistence import (
    FakeCallPersistence,
    SqlAlchemyCallPersistence,
    persist_call_v2_trace_summary,
)
from app.call_v2.session import CallSession, CallSessionConfig
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter
from app.call_v2.tts.cache import InMemoryAudioCache
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.resolver import AudioSourceResolver
from app.call_v2.turns.endpointing import EndpointingSettings
from app.models import Call, Job, Resume
from app.models.call_message import CallMessage


def _session_factory(db_session):
    @asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def _create_call(db_session, test_user, *, status: str = "queued") -> Call:
    job = Job(
        user_id=test_user.id,
        title="Backend Engineer",
        description="Build APIs.",
        requirements="Python, FastAPI",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Candidate",
        phone_number="+91-1111111111",
        email="candidate@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "Backend engineer"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        provider="browser",
        voice_runtime="call_v2",
        status=status,
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()
    await db_session.refresh(call)
    return call


def _start_message():
    return {
        "event": "start",
        "now_ms": 0,
        "stream_sid": "stream-v2",
        "start": {
            "stream_sid": "stream-v2",
            "call_id": "provider-call-v2",
            "call_sid": "provider-call-v2",
            "media_format": {
                "encoding": "audio/l16",
                "sample_rate": 8000,
                "channels": 1,
            },
        },
    }


def _media_message():
    return {
        "event": "media",
        "now_ms": 650,
        "stream_sid": "stream-v2",
        "media": {
            "payload": "AAE=",
            "timestamp": 1600,
            "chunk": 1,
        },
    }


def _agent_config() -> AgentConfig:
    return AgentConfig(
        agent_name="Recruiting Call Agent",
        instructions="Ask one concise screening question at a time.",
        scope=CallScope(
            purpose="Screen a backend engineer.",
            allowed_topics=["technical experience"],
            disallowed_topics=[],
            compliance_notes=[],
            success_criteria=["Collect technical signal."],
        ),
        context={"questions": [{"id": "q1", "text": "Tell me about a project."}]},
        response_style=ResponseStyle(tone="professional"),
    )


def _session(call: Call, db_session, *, agent_text: str = "Thanks. Next question."):
    adapter = BrowserSimulatorTelephonyAdapter()
    return CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id=str(call.id),
            initial_call_state=AgentVisibleCallState(
                phase="screening",
                consent_status="granted",
                open_items=["q1"],
            ),
            cache_policy_selector=lambda _output: CachePolicy(
                category="clarification_response"
            ),
        ),
        telephony_adapter=adapter,
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=FakeAgentRunner(
            outputs=[
                {
                    "spoken_text": agent_text,
                    "action": "continue",
                    "tool_calls": [],
                    "state_updates": {},
                }
            ]
        ),
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=FakeTtsEngine(payload=b"\x00\x01" * 160),
        ),
        persistence=SqlAlchemyCallPersistence(
            call_id=call.id,
            session_factory=_session_factory(db_session),
        ),
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )


async def _call_messages(db_session, call: Call) -> list[CallMessage]:
    result = await db_session.execute(
        select(CallMessage)
        .where(CallMessage.call_id == call.id)
        .order_by(CallMessage.sequence_number)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_fake_persistence_matches_idempotent_commit_contract():
    persistence = FakeCallPersistence()

    first = await persistence.commit_transcript_turn(
        generation_id=3,
        role="assistant",
        text="Please continue.",
        committed_at_ms=100,
    )
    second = await persistence.commit_transcript_turn(
        generation_id=3,
        role="assistant",
        text="Please continue.",
        committed_at_ms=200,
    )
    await persistence.record_latency_metric(
        name="agent_ms",
        value_ms=42,
        generation_id=3,
    )
    await persistence.record_cost_metric(name="tts_usd", amount_usd=0.00123456)

    assert first.message_id == second.message_id
    assert len(persistence.turns) == 1
    assert persistence.latency_metrics["call_v2"]["generation_latency_ms"]["3"] == {
        "agent_ms": 42
    }
    assert persistence.cost_breakdown["costs"]["tts_usd"] == 0.001235


@pytest.mark.asyncio
async def test_sqlalchemy_persistence_marks_started_and_completed(db_session, test_user):
    call = await _create_call(db_session, test_user)
    persistence = SqlAlchemyCallPersistence(
        call_id=call.id,
        session_factory=_session_factory(db_session),
    )
    session = _session(call, db_session)

    await session.handle_telephony_message(_start_message(), now_ms=100)
    await session.end(reason="provider_stop", now_ms=2300)

    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.provider == "browser"
    assert call.provider_call_id == "provider-call-v2"
    assert call.started_at is not None
    assert call.ended_at is not None
    assert call.duration_seconds == 2
    assert call.latency_metrics["call_v2"]["ended_reason"] == "provider_stop"

    await persistence.mark_call_ended(
        ended_at_ms=5000,
        reason="duplicate_end",
        status="failed",
    )
    await db_session.refresh(call)
    assert call.status == "completed"


@pytest.mark.asyncio
async def test_sqlalchemy_persistence_records_latency_and_cost_metrics(
    db_session,
    test_user,
):
    call = await _create_call(db_session, test_user)
    persistence = SqlAlchemyCallPersistence(
        call_id=call.id,
        session_factory=_session_factory(db_session),
    )

    await persistence.record_latency_metric(name="stt_first_final_ms", value_ms=180)
    await persistence.record_latency_metric(
        name="agent_ms",
        value_ms=42,
        generation_id=9,
    )
    await persistence.record_cost_metric(name="stt_usd", amount_usd=0.002)
    await persistence.record_cost_metric(name="tts_usd", amount_usd=0.003)

    await db_session.refresh(call)
    assert call.latency_metrics["call_v2"]["latency_ms"] == {
        "stt_first_final_ms": 180
    }
    assert call.latency_metrics["call_v2"]["generation_latency_ms"]["9"] == {
        "agent_ms": 42
    }
    assert call.cost_breakdown == {
        "runtime": "call_v2",
        "costs": {"stt_usd": 0.002, "tts_usd": 0.003},
        "estimated_total_usd": 0.005,
    }


@pytest.mark.asyncio
async def test_persist_call_v2_trace_summary_counts_events(db_session, test_user):
    call = await _create_call(db_session, test_user)

    await persist_call_v2_trace_summary(
        call_id=call.id,
        trace_events=[
            {
                "event_type": "telephony.audio_frame",
                "data": {"payload": {"byte_length": 320}},
            },
            {"event_type": "stt.connected", "data": {}},
            {"event_type": "stt.final_segment", "data": {"text": "yes"}},
        ],
        session_factory=_session_factory(db_session),
    )

    await db_session.refresh(call)
    summary = call.latency_metrics["call_v2"]["trace_summary"]
    assert summary["event_counts"]["telephony.audio_frame"] == 1
    assert summary["event_counts"]["stt.connected"] == 1
    assert [event["event_type"] for event in summary["recent_control_events"]] == [
        "stt.connected",
        "stt.final_segment",
    ]


@pytest.mark.asyncio
async def test_sqlalchemy_persistence_commits_turn_once(db_session, test_user):
    call = await _create_call(db_session, test_user)
    persistence = SqlAlchemyCallPersistence(
        call_id=call.id,
        session_factory=_session_factory(db_session),
    )

    first = await persistence.commit_transcript_turn(
        generation_id=7,
        role="user",
        text="  I built APIs   ",
        committed_at_ms=700,
    )
    second = await persistence.commit_transcript_turn(
        generation_id=7,
        role="user",
        text="I built APIs",
        committed_at_ms=900,
    )

    await db_session.refresh(call)
    messages = await _call_messages(db_session, call)
    assert first.message_id == second.message_id
    assert len(messages) == 1
    assert messages[0].sequence_number == 1
    assert messages[0].content == "I built APIs"
    assert call.transcript == "User: I built APIs"


@pytest.mark.asyncio
async def test_call_session_persists_confirmed_turns_to_existing_models(
    db_session,
    test_user,
):
    call = await _create_call(db_session, test_user)
    session = _session(call, db_session, agent_text="Thanks. What was hard?")

    start_result = await session.handle_telephony_message(_start_message(), now_ms=0)
    assert start_result.outbound_audio_frames == []
    assert start_result.clear_audio_commands == []
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="I built APIs",
            confidence=0.9,
            segment_id="seg-1",
            timestamps=TimestampMetadata(
                backend_received_at_ms=100,
                audio_offset_ms=1000,
            ),
            duration_ms=500,
        ),
        now_ms=100,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="I built APIs",
            confidence=0.9,
            silence_ms=500,
            timestamps=TimestampMetadata(
                backend_received_at_ms=600,
                audio_offset_ms=1000,
            ),
            duration_ms=500,
        ),
        now_ms=600,
    )
    result = await session.advance_time(700)

    await db_session.refresh(call)
    messages = await _call_messages(db_session, call)
    assert len(result.outbound_audio_frames) == 1
    assert [(message.role, message.content) for message in messages] == [
        ("user", "I built APIs"),
        ("assistant", "Thanks. What was hard?"),
    ]
    assert call.transcript == "User: I built APIs\nAssistant: Thanks. What was hard?"


@pytest.mark.asyncio
async def test_call_session_never_persists_cancelled_speculation(db_session, test_user):
    call = await _create_call(db_session, test_user)
    session = _session(call, db_session)

    await session.handle_telephony_message(_start_message(), now_ms=0)
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="I built APIs",
            confidence=0.9,
            segment_id="seg-1",
            timestamps=TimestampMetadata(
                backend_received_at_ms=100,
                audio_offset_ms=1000,
            ),
            duration_ms=500,
        ),
        now_ms=100,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text="I built APIs",
            confidence=0.9,
            silence_ms=500,
            timestamps=TimestampMetadata(
                backend_received_at_ms=600,
                audio_offset_ms=1000,
            ),
            duration_ms=500,
        ),
        now_ms=600,
    )
    await session.handle_telephony_message(_media_message(), now_ms=650)

    await db_session.refresh(call)
    assert await _call_messages(db_session, call) == []
    assert call.transcript is None
