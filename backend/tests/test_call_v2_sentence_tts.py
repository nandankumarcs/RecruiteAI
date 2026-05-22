"""Tests for sentence-level parallel TTS: splitter and session integration."""

from __future__ import annotations

import asyncio

import pytest

from app.call_v2.agent.config import AgentConfig, AgentVisibleCallState, CallScope, ResponseStyle
from app.call_v2.agent.fake import FakeAgentRunner
from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import CallIdentity, TelephonyStreamStarted, TimestampMetadata
from app.call_v2.persistence import FakeCallPersistence
from app.call_v2.session import CallSession, CallSessionConfig
from app.call_v2.state import CallRuntimeState
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter
from app.call_v2.tts.cache import InMemoryAudioCache
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.resolver import AudioSourceResolver
from app.call_v2.tts.sentence import split_sentences
from app.call_v2.turns.endpointing import EndpointingSettings


# ---------------------------------------------------------------------------
# Sentence splitter tests
# ---------------------------------------------------------------------------


def test_split_single_sentence():
    assert split_sentences("Hello there.") == ["Hello there."]


def test_split_two_sentences():
    result = split_sentences(
        "Great answer. Can you tell me more about the system?",
        min_chars=5,
    )
    assert result == [
        "Great answer.",
        "Can you tell me more about the system?",
    ]


def test_split_three_sentences():
    result = split_sentences(
        "Thanks for sharing that. Let me ask the next question. "
        "Can you describe a distributed system you built?",
        min_chars=5,
    )
    assert len(result) == 3
    assert result[0] == "Thanks for sharing that."
    assert result[2] == "Can you describe a distributed system you built?"


def test_no_split_on_abbreviation_mr():
    result = split_sentences("Mr. Smith leads the team. He is experienced.", min_chars=5)
    assert len(result) == 2
    assert result[0] == "Mr. Smith leads the team."


def test_no_split_on_abbreviation_dr():
    result = split_sentences("The role requires working with Dr. Patel.", min_chars=1)
    assert result == ["The role requires working with Dr. Patel."]


def test_no_split_on_decimal_number():
    result = split_sentences("The system processed 3.5 million records daily.", min_chars=1)
    assert result == ["The system processed 3.5 million records daily."]


def test_no_split_on_single_initial():
    result = split_sentences("J. K. Rowling wrote the series.", min_chars=1)
    assert result == ["J. K. Rowling wrote the series."]


def test_no_split_on_inc():
    result = split_sentences("She worked at Google Inc. for three years.", min_chars=1)
    assert result == ["She worked at Google Inc. for three years."]


def test_split_on_exclamation():
    result = split_sentences("Great! Let me ask you the first question.", min_chars=1)
    assert len(result) == 2
    assert result[0] == "Great!"


def test_split_on_question_mark():
    result = split_sentences("Is that right? Tell me more.", min_chars=1)
    assert len(result) == 2
    assert result[0] == "Is that right?"


def test_min_chars_joins_short_sentence():
    # "Got it." is 7 chars < default min_chars=20 → joins with next
    result = split_sentences(
        "Got it. Can you walk me through the architecture?",
        min_chars=20,
    )
    assert result == ["Got it. Can you walk me through the architecture?"]


def test_min_chars_joins_chain_of_short():
    # "Yes!" (4) < 10 → joins with "Sure!" → "Yes! Sure!" (10) = min_chars → emitted.
    # "Tell me about your experience." (30) → separate.
    result = split_sentences("Yes! Sure! Tell me about your experience.", min_chars=10)
    assert len(result) == 2
    assert result[0] == "Yes! Sure!"
    assert "experience." in result[1]


def test_empty_string_returns_empty():
    assert split_sentences("") == []


def test_whitespace_normalised():
    result = split_sentences("Hello   there.  How are  you?", min_chars=1)
    assert result[0] == "Hello there."
    assert result[1] == "How are you?"


def test_single_word_no_crash():
    result = split_sentences("Hello")
    assert result == ["Hello"]


# ---------------------------------------------------------------------------
# Session multi-sentence integration tests
# ---------------------------------------------------------------------------


def _agent_config() -> AgentConfig:
    return AgentConfig(
        agent_name="Test Agent",
        instructions="Screen the candidate.",
        scope=CallScope(purpose="Test"),
        response_style=ResponseStyle(tone="professional"),
    )


def _multi_session(*, spoken_text: str):
    persistence = FakeCallPersistence()
    tts = FakeTtsEngine(payload=b"\x00\x01" * 160)
    session = CallSession(
        config=CallSessionConfig(
            agent_config=_agent_config(),
            call_id="test-call",
            initial_call_state=AgentVisibleCallState(
                phase="screening", consent_status="granted", open_items=[]
            ),
            cache_policy_selector=lambda _: CachePolicy(category="conversation_turn"),
        ),
        telephony_adapter=BrowserSimulatorTelephonyAdapter(),
        stt_engine=FakeSttEngine(provider="fake", input_format=LINEAR16_8K_MONO),
        agent_runner=FakeAgentRunner(outputs=[{
            "spoken_text": spoken_text,
            "action": "continue",
            "tool_calls": [],
            "state_updates": {},
        }]),
        audio_resolver=AudioSourceResolver(cache=InMemoryAudioCache(), primary_tts=tts),
        persistence=persistence,
        endpointing_settings=EndpointingSettings(confirmation_window_ms=50),
    )
    return session, persistence, tts


async def _start(session: CallSession):
    await session.handle_telephony_event(
        TelephonyStreamStarted(
            type="telephony.stream_started",
            identity=CallIdentity(provider="browser", call_id="test-call", stream_id="s1"),
            inbound_format=LINEAR16_8K_MONO,
            outbound_format=LINEAR16_8K_MONO,
            timestamps=TimestampMetadata(backend_received_at_ms=0),
        ),
        now_ms=0,
    )


@pytest.mark.asyncio
async def test_single_sentence_uses_fast_path():
    """Single sentence: no pending_sentences, result looks identical to before."""
    session, _, _ = _multi_session(spoken_text="Hello, how are you?")
    await _start(session)
    result = await session.start_runtime_opener(now_ms=0)

    assert result.pending_sentences == []
    assert len(result.outbound_audio_frames) > 0


@pytest.mark.asyncio
async def test_multi_sentence_returns_pending_tasks():
    """Multi-sentence response: sentence 0 in frames, rest in pending_sentences."""
    text = (
        "Great, thanks for sharing that. "
        "Let me ask you about your backend experience. "
        "Can you describe a distributed system you have built?"
    )
    session, _, tts = _multi_session(spoken_text=text)
    await _start(session)

    from app.call_v2.stt.fake import FakeSttEngine
    from app.call_v2.events import SttFinalSegment, SttTentativeEndpoint
    await session.handle_stt_event(
        SttFinalSegment(type="stt.final_segment", text="Yes.", confidence=0.9,
                        segment_id="s1", timestamps=TimestampMetadata(backend_received_at_ms=100),
                        duration_ms=300),
        now_ms=100,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(type="stt.tentative_endpoint", text="Yes.", confidence=0.9,
                             silence_ms=500, timestamps=TimestampMetadata(backend_received_at_ms=600),
                             duration_ms=300),
        now_ms=600,
    )
    result = await session.advance_time(700)

    assert len(result.outbound_audio_frames) > 0, "sentence 0 frames must be present"
    assert len(result.pending_sentences) >= 1, "remaining sentences must be pending tasks"
    # All pending tasks should resolve to frames (FakeTts is synchronous → all done instantly)
    for task in result.pending_sentences:
        plan = await task
        assert len(plan.frames) > 0


@pytest.mark.asyncio
async def test_barge_in_cancels_pending_sentence_tasks():
    """Barge-in marks generation stale → pending sentence tasks cancelled."""
    text = (
        "Sure, let me explain that. "
        "The question is about a system you designed end-to-end. "
        "Feel free to take your time."
    )
    session, _, tts = _multi_session(spoken_text=text)
    await _start(session)

    from app.call_v2.events import SttFinalSegment, SttTentativeEndpoint
    await session.handle_stt_event(
        SttFinalSegment(type="stt.final_segment", text="Yes.", confidence=0.9,
                        segment_id="s1", timestamps=TimestampMetadata(backend_received_at_ms=100),
                        duration_ms=300),
        now_ms=100,
    )
    await session.handle_stt_event(
        SttTentativeEndpoint(type="stt.tentative_endpoint", text="Yes.", confidence=0.9,
                             silence_ms=500, timestamps=TimestampMetadata(backend_received_at_ms=600),
                             duration_ms=300),
        now_ms=600,
    )
    result = await session.advance_time(700)
    gen_id = result.outbound_audio_frames[0].generation_id if result.outbound_audio_frames else None
    pending = result.pending_sentences[:]

    # Trigger barge-in
    await session.handle_stt_event(
        SttFinalSegment(type="stt.final_segment", text="Wait, actually...", confidence=0.9,
                        segment_id="s2", timestamps=TimestampMetadata(backend_received_at_ms=750),
                        duration_ms=500),
        now_ms=750,
    )

    # Pending tasks should be cancelled after a brief yield
    await asyncio.sleep(0)
    if gen_id is not None:
        assert gen_id in tts.cancelled_generation_ids


@pytest.mark.asyncio
async def test_min_chars_batching_reduces_sentence_count():
    """Responses with short first sentences get batched → fewer pending tasks."""
    text = "Got it. Can you describe a system you designed?"
    sentences = split_sentences(text, min_chars=20)
    # "Got it." is 7 chars < 20 → batched with next
    assert len(sentences) == 1
