"""Tests for the production-shaped Exotel and browser v2 runtime wiring."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest

from app.call_v2.agent.openai import OpenAIChatStructuredModel
from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.runtime import (
    CallV2RuntimeFactory,
    CallV2Context,
    build_agent_config,
    build_deepgram_keyterms,
    _adapter_for_provider,
)
from app.call_v2.stt.deepgram import DeepgramStreamingSttEngine
from app.call_v2.telephony.exotel import ExotelMediaTelephonyAdapter
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter
from app.models import Call, InterviewQuestion, Job, Resume
from app.routers import browser_webhooks, exotel_webhooks


class _FakeChatCompletions:
    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "spoken_text": "Thanks. Can you tell me more?",
                                "action": "continue",
                                "tool_calls": [],
                                "state_updates": {},
                            }
                        )
                    )
                )
            ]
        )


class _FakeOpenAIClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeChatCompletions())


def _context() -> CallV2Context:
    job_id = uuid.uuid4()
    resume_id = uuid.uuid4()
    return CallV2Context(
        resume=Resume(
            id=resume_id,
            job_id=job_id,
            candidate_name="Ada Candidate",
            phone_number="+919999999999",
            email="ada@example.com",
            file_path="/tmp/resume.pdf",
            file_type="pdf",
            parsed_data={"skills": ["FastAPI", "PostgreSQL", "FastAPI"]},
        ),
        job=Job(
            id=job_id,
            user_id=uuid.uuid4(),
            title="Backend Engineer",
            description="Build APIs and async services.",
            requirements="FastAPI\nPostgreSQL",
            evaluation_criteria="Clarity and production experience.",
        ),
        questions=[
            InterviewQuestion(
                id=uuid.uuid4(),
                job_id=job_id,
                question_text="Tell me about a backend system you owned.",
                category="project",
                difficulty=3,
                order_index=1,
            )
        ],
        call=Call(
            id=uuid.uuid4(),
            resume_id=resume_id,
            job_id=job_id,
            provider="exotel",
            voice_runtime="call_v2",
            status="pending",
            phone_number="+919999999999",
        ),
    )


@pytest.mark.asyncio
async def test_openai_structured_model_uses_json_mode_and_parses_object():
    client = _FakeOpenAIClient()
    model = OpenAIChatStructuredModel(api_key="test-key", model="gpt-test", client=client)

    parsed = await model.ainvoke([{"role": "user", "content": "Return JSON"}])

    assert parsed["spoken_text"] == "Thanks. Can you tell me more?"
    assert client.chat.completions.kwargs["response_format"] == {"type": "json_object"}


def test_deepgram_streaming_url_matches_exotel_audio_contract():
    engine = DeepgramStreamingSttEngine(
        api_key="test-key",
        input_format=LINEAR16_8K_MONO,
        model="nova-3",
        language="en-IN",
        endpointing_ms=500,
        utterance_end_ms=1000,
        keyterms=["FastAPI"],
    )

    url = engine._listen_url()

    assert url.startswith("wss://api.deepgram.com/v1/listen?")
    assert "encoding=linear16" in url
    assert "sample_rate=8000" in url
    assert "interim_results=true" in url
    assert "vad_events=true" in url
    assert "endpointing=500" in url
    assert "utterance_end_ms=1000" in url
    assert "keyterm=FastAPI" in url


def test_deepgram_streaming_url_uses_keywords_for_non_nova3_models():
    engine = DeepgramStreamingSttEngine(
        api_key="test-key",
        input_format=LINEAR16_8K_MONO,
        model="nova-2-phonecall",
        language="en-IN",
        keyterms=["FastAPI"],
    )

    url = engine._listen_url()
    # nova-2 uses the legacy `keywords` parameter with an intensifier, not `keyterm`.
    assert "keyterm=" not in url
    assert "keywords=FastAPI%3A2" in url  # URL-encoded "FastAPI:2"


def test_agent_config_carries_questions_context_and_non_deterministic_policy():
    config = build_agent_config(_context())

    assert config.config_version == "call-agent.v2.exotel"
    assert config.context["questions"][0]["text"] == "Tell me about a backend system you owned."
    assert set(config.context["candidate"]) == {"name", "email", "phone_number"}
    assert "Ask for consent" in config.instructions
    assert "deterministic script" in config.instructions
    assert any("Ask for consent once" in c for c in config.constraints)
    assert any("clearly declines consent" in c for c in config.constraints)
    assert any("called back" in c for c in config.constraints)
    assert any("move on to the next question" in c for c in config.constraints)
    assert any("At most one follow-up" in c for c in config.constraints)
    assert any("Never repeat the opener" in c for c in config.constraints)
    assert any("do not ask that same question again" in c for c in config.constraints)


def test_deepgram_keyterms_are_unique_and_contextual():
    terms = build_deepgram_keyterms(_context())

    assert "Ada Candidate" in terms
    assert "Backend Engineer" in terms
    assert terms.count("FastAPI") == 1


@pytest.mark.asyncio
async def test_exotel_runtime_disables_raw_audio_tentative_cancellation(monkeypatch):
    context = _context()

    async def fake_load_context(*, resume_id, provider):
        return context

    monkeypatch.setattr("app.call_v2.runtime.load_call_v2_context", fake_load_context)
    monkeypatch.setattr("app.call_v2.runtime.build_deepgram_keyterms", lambda _context: [])

    class _Settings:
        OPENAI_API_KEY = "openai-key"
        DEEPGRAM_API_KEY = "deepgram-key"
        DEEPGRAM_STT_MODEL = "nova-2-phonecall"
        DEEPGRAM_STT_MODEL_BROWSER = "nova-3"
        DEEPGRAM_STT_LANGUAGE = "en-IN"
        PIPELINE_STT_ENDPOINTING_MS = 500
        PIPELINE_STT_UTTERANCE_END_MS = 1000
        PIPELINE_SPECULATIVE_CONFIRMATION_MS = 800
        PIPELINE_SILENCE_NUDGE_MS = 5000
        PIPELINE_SILENCE_NUDGE_ESCALATE_MS = 12000
        PIPELINE_SILENCE_ENDCALL_MS = 20000
        OPENAI_TTS_MODEL = "tts-model"
        OPENAI_TTS_VOICE = "voice"
        OPENAI_TTS_SPEED = 1.0
        OPENAI_TEXT_MODEL = "text-model"
        OPENAI_MODEL = "fallback-model"
        TTS_PROVIDER = "openai"
        COMPANY_NAME = "Test Corp"
        AGENT_PROVIDER = "openai"
        GROQ_API_KEY = ""
        GROQ_AGENT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
        GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    monkeypatch.setattr("app.call_v2.runtime.get_settings", lambda: _Settings())

    session = await CallV2RuntimeFactory().create_session(
        resume_id=context.resume.id,
        provider="exotel",
    )

    assert session.config.raw_audio_cancels_tentative_turns is False


@pytest.mark.asyncio
async def test_exotel_media_route_hands_resolved_uuid_to_v2_runtime(monkeypatch):
    resume_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, str]] = []

    class _Runtime:
        async def handle(self, websocket, *, resume_id, provider):
            calls.append((resume_id, provider))

    class _WebSocket:
        url = "wss://example.test/ws/exotel-media/voice"
        query_params = {}

        async def accept(self):
            self.accepted = True

    monkeypatch.setattr(exotel_webhooks, "get_call_v2_runtime", lambda: _Runtime())

    await exotel_webhooks.exotel_media_stream(
        _WebSocket(),
        resume_id=f"voice/{resume_id}",
    )

    assert calls == [(resume_id, "exotel")]


# ---------------------------------------------------------------------------
# Browser provider wiring
# ---------------------------------------------------------------------------


def test_adapter_for_provider_returns_correct_adapter_types():
    assert isinstance(_adapter_for_provider("exotel"), ExotelMediaTelephonyAdapter)
    assert isinstance(_adapter_for_provider("browser"), BrowserSimulatorTelephonyAdapter)


def test_adapter_for_provider_raises_for_unknown_provider():
    with pytest.raises(ValueError, match="unsupported call v2 provider"):
        _adapter_for_provider("twilio")


@pytest.mark.asyncio
async def test_browser_runtime_uses_browser_simulator_adapter(monkeypatch):
    context = _context()

    async def fake_load_context(*, resume_id, provider):
        return context

    monkeypatch.setattr("app.call_v2.runtime.load_call_v2_context", fake_load_context)
    monkeypatch.setattr("app.call_v2.runtime.build_deepgram_keyterms", lambda _context: [])

    class _Settings:
        OPENAI_API_KEY = "openai-key"
        DEEPGRAM_API_KEY = "deepgram-key"
        DEEPGRAM_STT_MODEL = "nova-2-phonecall"
        DEEPGRAM_STT_MODEL_BROWSER = "nova-3"
        DEEPGRAM_STT_LANGUAGE = "en-IN"
        PIPELINE_STT_ENDPOINTING_MS = 500
        PIPELINE_STT_UTTERANCE_END_MS = 1000
        PIPELINE_SPECULATIVE_CONFIRMATION_MS = 800
        PIPELINE_SILENCE_NUDGE_MS = 5000
        PIPELINE_SILENCE_NUDGE_ESCALATE_MS = 12000
        PIPELINE_SILENCE_ENDCALL_MS = 20000
        OPENAI_TTS_MODEL = "tts-model"
        OPENAI_TTS_VOICE = "voice"
        OPENAI_TTS_SPEED = 1.0
        OPENAI_TEXT_MODEL = "text-model"
        OPENAI_MODEL = "fallback-model"
        TTS_PROVIDER = "openai"
        COMPANY_NAME = "Test Corp"
        AGENT_PROVIDER = "openai"
        GROQ_API_KEY = ""
        GROQ_AGENT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
        GROQ_BASE_URL = "https://api.groq.com/openai/v1"

    monkeypatch.setattr("app.call_v2.runtime.get_settings", lambda: _Settings())

    session = await CallV2RuntimeFactory().create_session(
        resume_id=context.resume.id,
        provider="browser",
    )

    assert isinstance(session.telephony_adapter, BrowserSimulatorTelephonyAdapter)
    assert session.config.raw_audio_cancels_tentative_turns is False


@pytest.mark.asyncio
async def test_browser_media_route_hands_resume_uuid_to_v2_runtime(monkeypatch):
    resume_id = uuid.uuid4()
    call_id = uuid.uuid4()
    calls: list[tuple[uuid.UUID, str]] = []

    class _Runtime:
        async def handle(self, websocket, *, resume_id, provider):
            calls.append((resume_id, provider))

    class _WebSocket:
        application_state = type("S", (), {"name": "CONNECTED"})()
        query_params = {"token": "test-token"}

        async def close(self, **kwargs):
            pass

    monkeypatch.setattr(browser_webhooks, "get_call_v2_runtime", lambda: _Runtime())
    monkeypatch.setattr(
        browser_webhooks,
        "decode_token",
        lambda token: {
            "purpose": "simulator_join",
            "resume_id": str(resume_id),
            "call_id": str(call_id),
        },
    )

    # Stub DB lookup so the route doesn't hit the real database.
    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def get(self, model, pk):
            call = Call(
                id=call_id,
                resume_id=resume_id,
                job_id=uuid.uuid4(),
                provider="browser",
                voice_runtime="call_v2",
                status="pending",
                phone_number="+10000000000",
            )
            return call

    monkeypatch.setattr(browser_webhooks, "async_session_factory", _FakeSession)

    ws = _WebSocket()
    await browser_webhooks.browser_media_stream(ws, resume_id=str(resume_id))

    assert calls == [(resume_id, "browser")]
