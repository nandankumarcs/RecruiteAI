"""Phase 8 tests for call v2 session integration with fake providers."""

import asyncio

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
    # Speculative agent runs now launch as background tasks (see
    # _launch_speculative_agent_run). Yield so the gen=1 task completes and
    # consumes "Stale response." before we cancel it — this exercises the
    # exact invariant the test cares about: a *completed* stale speculative
    # result must not be used for a later confirmed turn. Without this yield,
    # the cancellation would race ahead of the task and leave the "Stale"
    # output in the FakeAgentRunner queue, which is a different (and also
    # valid) code path.
    await asyncio.sleep(0)
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


@pytest.mark.asyncio
async def test_speculative_agent_run_is_dispatched_as_background_task():
    """Speculative runs must be fire-and-forget so the caller's state_lock can
    be released while the LLM call is in flight. handle_stt_event must return
    BEFORE the agent run completes (which is what allows the runtime to
    forward audio frames concurrently)."""

    class _SlowAgentRunner:
        def __init__(self):
            self.gate = asyncio.Event()
            self.calls: list = []

        async def run(self, agent_input):
            self.calls.append(agent_input)
            await self.gate.wait()
            from app.call_v2.agent.output import validate_agent_output
            return validate_agent_output(
                {
                    "spoken_text": "ok",
                    "action": "continue",
                    "tool_calls": [],
                    "state_updates": {},
                },
                available_tools=[],
                speculative=True,
            )

    persistence = FakeCallPersistence()
    slow_runner = _SlowAgentRunner()
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="call-bg",
            initial_call_state=AgentVisibleCallState(
                phase="screening", consent_status="granted", open_items=[]
            ),
            cache_policy_selector=lambda _o: CachePolicy(category="clarification_response"),
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=slow_runner,
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=FakeTtsEngine(payload=b"\x00\x01" * 160),
        ),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("hello"), now_ms=100)
    # If handle_stt_event awaited the agent inline, this call would hang
    # forever on slow_runner.gate. It must return promptly.
    await asyncio.wait_for(
        session.handle_stt_event(_endpoint("hello"), now_ms=600),
        timeout=1.0,
    )

    pending = session._pending_agent_tasks.get(1)
    assert pending is not None
    assert not pending.done()

    # Release the gate so the task doesn't leak across tests.
    slow_runner.gate.set()
    await asyncio.wait_for(pending, timeout=1.0)
    assert session._agent_runs[1].output.spoken_text == "ok"


@pytest.mark.asyncio
async def test_mark_agent_stale_cancels_in_flight_speculative_task():
    """When a tentative is cancelled mid-run, the speculative task must be
    cancelled so we don't waste the LLM call and don't leave a stored run."""

    class _GatedRunner:
        def __init__(self):
            self.gate = asyncio.Event()
            self.cancelled = False

        async def run(self, agent_input):
            try:
                await self.gate.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            from app.call_v2.agent.output import validate_agent_output
            return validate_agent_output(
                {"spoken_text": "x", "action": "continue", "tool_calls": [], "state_updates": {}},
                available_tools=[],
                speculative=True,
            )

    runner = _GatedRunner()
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="call-cancel",
            initial_call_state=AgentVisibleCallState(
                phase="screening", consent_status="granted", open_items=[]
            ),
            cache_policy_selector=lambda _o: CachePolicy(category="clarification_response"),
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=runner,
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=FakeTtsEngine(payload=b"\x00\x01" * 160),
        ),
        persistence=FakeCallPersistence(),
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("hello"), now_ms=100)
    await session.handle_stt_event(_endpoint("hello"), now_ms=600)
    pending = session._pending_agent_tasks.get(1)
    assert pending is not None and not pending.done()

    # Yield so the task actually enters runner.run() and reaches the
    # await self.gate.wait() suspension point. Without this, the cancel
    # below would terminate the task before it ever ran, so the runner's
    # CancelledError handler wouldn't execute.
    await asyncio.sleep(0)

    await session.handle_telephony_event(_audio_after_endpoint(), now_ms=700)
    try:
        await asyncio.wait_for(pending, timeout=1.0)
    except asyncio.CancelledError:
        pass

    assert pending.cancelled() or pending.done()
    assert runner.cancelled is True


@pytest.mark.asyncio
async def test_session_end_cancels_pending_speculative_tasks():
    """end() must cancel any in-flight speculative tasks so they don't race
    on session state after the call has ended."""

    class _GatedRunner:
        def __init__(self):
            self.gate = asyncio.Event()

        async def run(self, agent_input):
            await self.gate.wait()
            from app.call_v2.agent.output import validate_agent_output
            return validate_agent_output(
                {"spoken_text": "x", "action": "continue", "tool_calls": [], "state_updates": {}},
                available_tools=[],
                speculative=True,
            )

    runner = _GatedRunner()
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="call-end",
            initial_call_state=AgentVisibleCallState(
                phase="screening", consent_status="granted", open_items=[]
            ),
            cache_policy_selector=lambda _o: CachePolicy(category="clarification_response"),
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=runner,
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=FakeTtsEngine(payload=b"\x00\x01" * 160),
        ),
        persistence=FakeCallPersistence(),
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    await _start_stream(session)

    await session.handle_stt_event(_final("hello"), now_ms=100)
    await session.handle_stt_event(_endpoint("hello"), now_ms=600)
    pending = session._pending_agent_tasks.get(1)
    assert pending is not None and not pending.done()

    await session.end(reason="test", now_ms=700)
    try:
        await asyncio.wait_for(pending, timeout=1.0)
    except asyncio.CancelledError:
        pass
    assert pending.cancelled() or pending.done()


# ---------------------------------------------------------------------------
# Silence escalation: 5s nudge / 12s stronger nudge / 20s end-call
# ---------------------------------------------------------------------------

def _silence_session():
    """Session with the agent runner emptied (silence path never invokes it)."""
    return _session(agent_outputs=[])


async def _drive_into_post_tts_guard(session: CallSession, now_ms: int = 0) -> None:
    """Put the session into POST_TTS_GUARD with a silence window open at now_ms.

    Simulates: AI just finished speaking the opener. We hand-roll the state
    rather than running a full turn so the test doesn't depend on agent /
    TTS / endpointing details.
    """
    await _start_stream(session)
    session.identity = session.identity  # ensure set
    session._transition(CallRuntimeState.SPEAKING, "test_setup_speaking")
    await session.complete_tts(now_ms=now_ms)
    assert session.state_machine.state == CallRuntimeState.POST_TTS_GUARD
    assert session._silence_started_at_ms == now_ms


@pytest.mark.asyncio
async def test_silence_nudge_fires_at_5s_threshold():
    session, _persistence, tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    # 4.9s after listening starts — no nudge yet.
    result = await session.advance_time(4900)
    assert result.outbound_audio_frames == []
    assert session._nudge_stage == 0

    # 5.0s — stage 1 nudge fires.
    result = await session.advance_time(5000)
    assert len(result.outbound_audio_frames) > 0
    assert session._nudge_stage == 1
    # Nudge was synthesised, so TTS got called once.
    assert len(tts.requests) == 1
    # The nudge text matches the stage 1 phrase.
    assert "Are you still there" in tts.requests[0].text


@pytest.mark.asyncio
async def test_silence_escalates_to_stage_2_at_12s():
    """Stage 2 fires at 12s elapsed FROM THE ORIGINAL SILENCE ORIGIN,
    not from when stage 1 ended. The candidate's total silence budget is
    20s — the nudges don't extend it."""
    session, _persistence, tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    # Fire stage 1 nudge first (at 5s elapsed).
    await session.advance_time(5000)
    # Simulate the nudge TTS completing at 6.5s. Because _nudge_stage > 0,
    # complete_tts must NOT re-arm the silence window — the origin stays
    # anchored at 0 so the 12s threshold is measured from the original
    # silence, not from after the nudge.
    await session.complete_tts(now_ms=6500)
    assert session._silence_started_at_ms == 0   # origin preserved
    assert session._nudge_stage == 1

    # 11.9s elapsed from origin — no escalation yet.
    result = await session.advance_time(11900)
    assert result.outbound_audio_frames == []
    assert session._nudge_stage == 1

    # 12s elapsed from origin — stage 2 fires.
    result = await session.advance_time(12000)
    assert len(result.outbound_audio_frames) > 0
    assert session._nudge_stage == 2
    assert (
        "can't hear" in tts.requests[-1].text.lower()
        or "are you able" in tts.requests[-1].text.lower()
    )


@pytest.mark.asyncio
async def test_silence_ends_call_at_20s():
    session, _persistence, tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    # 20s of total silence — end-call fires.
    result = await session.advance_time(20000)
    assert len(result.outbound_audio_frames) > 0
    # The end-call phrase is multi-sentence, so any TTS request from this
    # turn carrying the disconnect language counts.
    all_text = " ".join(r.text.lower() for r in tts.requests)
    assert "disconnected" in all_text
    assert session._end_after_speaking is True
    assert session._end_after_speaking_reason == "silence_timeout"


@pytest.mark.asyncio
async def test_silence_timer_resets_on_candidate_speech():
    """A real candidate speech event (final segment with text and
    confidence > 0) cancels the in-progress silence window."""
    session, _persistence, _tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    # 4s of silence — about to nudge.
    result = await session.advance_time(4000)
    assert result.outbound_audio_frames == []

    # Candidate speaks with confidence > 0. Silence window must cancel —
    # no nudge should fire at the original 5s mark.
    from app.call_v2.events import SttFinalSegment, TimestampMetadata
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="Hello",
            confidence=0.9,
            segment_id=None,
            timestamps=TimestampMetadata(backend_received_at_ms=4500),
            duration_ms=400,
        ),
        now_ms=4500,
    )
    assert session._silence_started_at_ms is None
    assert session._nudge_stage == 0

    result = await session.advance_time(5500)
    assert result.outbound_audio_frames == []
    assert session._nudge_stage == 0


@pytest.mark.asyncio
async def test_silence_nudge_disabled_when_threshold_is_zero():
    """Setting silence_nudge_ms=0 turns the feature off entirely."""
    persistence = FakeCallPersistence()
    tts = FakeTtsEngine(payload=b"\x00\x01" * 160)
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="call-no-nudge",
            initial_call_state=AgentVisibleCallState(
                phase="screening", consent_status="granted", open_items=[]
            ),
            cache_policy_selector=lambda _o: CachePolicy(category="clarification_response"),
            silence_nudge_ms=0,
            silence_nudge_escalate_ms=0,
            silence_endcall_ms=0,
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=FakeAgentRunner(outputs=[]),
        audio_resolver=AudioSourceResolver(
            cache=InMemoryAudioCache(),
            primary_tts=tts,
        ),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
    )
    await _drive_into_post_tts_guard(session, now_ms=0)

    # Even at 60s of silence, nothing should fire.
    result = await session.advance_time(60_000)
    assert result.outbound_audio_frames == []
    assert tts.requests == []


@pytest.mark.asyncio
async def test_silence_timer_ignores_tts_echo_events():
    """Echo from the AI's own TTS bleeding into the candidate mic surfaces
    as SttSpeechStarted (VAD only) and as Interim/Final transcripts with
    confidence=0. These must NOT reset the silence timer — otherwise a
    silent candidate's mic loopback prevents the nudge from ever firing
    (the bug we observed in call 30ed2cd6)."""
    session, _persistence, tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    from app.call_v2.events import (
        SttFinalSegment,
        SttInterimTranscript,
        SttSpeechStarted,
        TimestampMetadata,
    )

    # Simulate a sequence of echo / VAD-only events spread across the
    # silence window. None of them should reset the silence timer.
    await session.handle_stt_event(
        SttSpeechStarted(
            type="stt.speech_started",
            timestamps=TimestampMetadata(backend_received_at_ms=1000),
        ),
        now_ms=1000,
    )
    await session.handle_stt_event(
        SttInterimTranscript(
            type="stt.interim_transcript",
            text="AI",  # echo of the opener's "junior AI engineer position"
            confidence=0.0,
            timestamps=TimestampMetadata(backend_received_at_ms=2000),
            duration_ms=1000,
        ),
        now_ms=2000,
    )
    await session.handle_stt_event(
        SttFinalSegment(
            type="stt.final_segment",
            text="AI",
            confidence=0.0,
            segment_id=None,
            timestamps=TimestampMetadata(backend_received_at_ms=3500),
            duration_ms=1200,
        ),
        now_ms=3500,
    )
    # Silence origin must still be 0 — none of the echo events reset it.
    assert session._silence_started_at_ms == 0

    # At 5s elapsed, the nudge fires normally.
    result = await session.advance_time(5000)
    assert len(result.outbound_audio_frames) > 0
    assert session._nudge_stage == 1
    assert "Are you still there" in tts.requests[-1].text


@pytest.mark.asyncio
async def test_silence_full_escalation_ladder_within_20s_budget():
    """End-to-end ladder: stage 1 at 5s, stage 2 at 12s, end-call at 20s,
    all measured from the original silence origin. The intermediate nudge
    TTS completing does NOT reset the origin."""
    session, _persistence, tts = _silence_session()
    await _drive_into_post_tts_guard(session, now_ms=0)

    # Stage 1 at 5s.
    result = await session.advance_time(5000)
    assert len(result.outbound_audio_frames) > 0
    assert session._nudge_stage == 1
    # Stage 1 nudge audio plays for ~1.5s — simulate completion.
    await session.complete_tts(now_ms=6500)
    assert session._silence_started_at_ms == 0  # origin preserved

    # Stage 2 at 12s.
    result = await session.advance_time(12000)
    assert len(result.outbound_audio_frames) > 0
    assert session._nudge_stage == 2
    await session.complete_tts(now_ms=13500)
    assert session._silence_started_at_ms == 0  # origin preserved

    # End-call at 20s.
    result = await session.advance_time(20000)
    assert len(result.outbound_audio_frames) > 0
    assert session._end_after_speaking is True
    assert session._end_after_speaking_reason == "silence_timeout"
