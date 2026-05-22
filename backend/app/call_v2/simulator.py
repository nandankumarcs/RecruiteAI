"""WebSocket harness for exercising call v2 with fake providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings
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
    SttInterimTranscript,
    SttSpeechStarted,
    SttTentativeEndpoint,
    SttUtteranceEnded,
    TimestampMetadata,
)
from app.call_v2.persistence import FakeCallPersistence
from app.call_v2.session import CallSession, CallSessionConfig, CallSessionResult
from app.call_v2.stt.deepgram import DeepgramStreamingSttEngine
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.stt.openai import OpenAIBufferedTranscriptionEngine
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter
from app.call_v2.tts.cache import InMemoryAudioCache
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.openai import OpenAITtsEngine
from app.call_v2.tts.resolver import AudioSourceResolver
from app.call_v2.turns.endpointing import EndpointingSettings


DEFAULT_AGENT_OUTPUTS = [
    {
        "spoken_text": "Thanks. What was the hardest part?",
        "action": "continue",
        "tool_calls": [],
        "state_updates": {},
    },
    {
        "spoken_text": "Got it. Please continue.",
        "action": "pause_for_user",
        "tool_calls": [],
        "state_updates": {},
    },
    {
        "spoken_text": "Thanks for speaking with me. Goodbye.",
        "action": "end_call_after_speaking",
        "tool_calls": [],
        "state_updates": {"call_complete": True},
    },
]


@dataclass(slots=True)
class CallV2SimulatorHarness:
    """Drives a v2 CallSession from websocket-friendly test messages."""

    session: CallSession
    persistence: FakeCallPersistence
    adapter: BrowserSimulatorTelephonyAdapter
    sent_messages: list[dict[str, Any]]

    @classmethod
    def create(
        cls,
        *,
        call_id: str,
        agent_outputs: list[dict[str, Any]] | None = None,
        real_audio: bool = False,
    ) -> "CallV2SimulatorHarness":
        adapter = BrowserSimulatorTelephonyAdapter()
        persistence = FakeCallPersistence()
        agent_runner = FakeAgentRunner(
            outputs=(agent_outputs or DEFAULT_AGENT_OUTPUTS).copy()
        )
        settings = get_settings()
        if real_audio:
            if not settings.DEEPGRAM_API_KEY:
                raise ValueError("DEEPGRAM_API_KEY is required for real audio simulator")
            stt_engine = DeepgramStreamingSttEngine(
                api_key=settings.DEEPGRAM_API_KEY,
                input_format=LINEAR16_8K_MONO,
                model=settings.DEEPGRAM_STT_MODEL,
                language=settings.DEEPGRAM_STT_LANGUAGE,
                endpointing_ms=max(200, settings.PIPELINE_STT_ENDPOINTING_MS),
                utterance_end_ms=max(500, settings.PIPELINE_STT_UTTERANCE_END_MS),
            )
            tts_provider = (settings.TTS_PROVIDER or "openai").lower()
            if tts_provider == "sarvam" and settings.SARVAM_API_KEY:
                from app.call_v2.tts.sarvam import sarvam_tts_engine_from_settings
                tts_engine = sarvam_tts_engine_from_settings()
            else:
                tts_engine = OpenAITtsEngine(
                    api_key=settings.OPENAI_API_KEY,
                    model=settings.OPENAI_TTS_MODEL,
                    voice=settings.OPENAI_TTS_VOICE,
                    speed=settings.OPENAI_TTS_SPEED,
                )
        else:
            stt_engine = FakeSttEngine(
                provider="fake",
                input_format=LINEAR16_8K_MONO,
            )
            tts_engine = FakeTtsEngine(payload=b"\x00\x01" * 160)
        session = CallSession(
            config=CallSessionConfig(
                agent_config=_default_agent_config(),
                call_id=call_id,
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
            stt_engine=stt_engine,
            agent_runner=agent_runner,
            audio_resolver=AudioSourceResolver(
                cache=InMemoryAudioCache(),
                primary_tts=tts_engine,
            ),
            persistence=persistence,
            endpointing_settings=EndpointingSettings(confirmation_window_ms=100),
        )
        return cls(
            session=session,
            persistence=persistence,
            adapter=adapter,
            sent_messages=[],
        )

    async def handle_message(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        now_ms = int(message.get("now_ms") or message.get("timestamp") or 0)
        result = CallSessionResult()
        event = message.get("event")
        if event == "stt.transcribe_buffer":
            result = await self._transcribe_buffer(message, now_ms=now_ms)
        elif event == "audio.reset_buffer":
            self._reset_stt_buffer()
        elif isinstance(event, str) and event.startswith("stt."):
            result = await self._handle_stt_control(message, now_ms=now_ms)
        elif event == "time.advance":
            result = await self.session.advance_time(now_ms)
        elif event == "tts.completed":
            await self.session.complete_tts(now_ms=now_ms)
        elif event == "trace.get":
            return [self._trace_message()]
        elif event == "persisted.get":
            return [self._persisted_message()]
        else:
            result = await self.session.handle_telephony_message(
                message,
                now_ms=now_ms,
                candidate_activity=bool(message.get("candidate_activity", True)),
            )
        return self._outbound_messages(result)

    async def _transcribe_buffer(
        self,
        message: dict[str, Any],
        *,
        now_ms: int,
    ) -> CallSessionResult:
        transcribe = getattr(self.session.stt_engine, "transcribe_buffer", None)
        if not callable(transcribe):
            raise ValueError("current STT engine does not support buffered transcription")

        result = CallSessionResult()
        stt_events = await transcribe(
            now_ms=now_ms,
            silence_ms=_optional_int(message.get("silence_ms")),
        )
        for stt_event in stt_events:
            stt_result = await self.session.handle_stt_event(stt_event, now_ms=now_ms)
            result.outbound_audio_frames.extend(stt_result.outbound_audio_frames)
            result.clear_audio_commands.extend(stt_result.clear_audio_commands)
            result.end_call = result.end_call or stt_result.end_call
        return result

    def _reset_stt_buffer(self) -> None:
        reset = getattr(self.session.stt_engine, "reset_buffer", None)
        if not callable(reset):
            raise ValueError("current STT engine does not support buffer reset")
        reset()

    async def _handle_stt_control(
        self,
        message: dict[str, Any],
        *,
        now_ms: int,
    ) -> CallSessionResult:
        event = message.get("event")
        if event == "stt.speech_started":
            return await self.session.handle_stt_event(
                SttSpeechStarted(
                    type="stt.speech_started",
                    timestamps=_timestamps(message, now_ms),
                ),
                now_ms=now_ms,
            )
        if event == "stt.interim":
            return await self.session.handle_stt_event(
                SttInterimTranscript(
                    type="stt.interim_transcript",
                    text=str(message.get("text") or ""),
                    confidence=_optional_float(message.get("confidence")),
                    timestamps=_timestamps(message, now_ms),
                    duration_ms=_optional_int(message.get("duration_ms")),
                ),
                now_ms=now_ms,
            )
        if event == "stt.final":
            return await self.session.handle_stt_event(
                SttFinalSegment(
                    type="stt.final_segment",
                    text=str(message.get("text") or ""),
                    confidence=_optional_float(message.get("confidence")) or 0.9,
                    segment_id=message.get("segment_id"),
                    timestamps=_timestamps(message, now_ms),
                    duration_ms=_optional_int(message.get("duration_ms")),
                ),
                now_ms=now_ms,
            )
        if event == "stt.endpoint":
            return await self.session.handle_stt_event(
                SttTentativeEndpoint(
                    type="stt.tentative_endpoint",
                    text=str(message.get("text") or ""),
                    confidence=_optional_float(message.get("confidence")),
                    silence_ms=_optional_int(message.get("silence_ms")),
                    timestamps=_timestamps(message, now_ms),
                    duration_ms=_optional_int(message.get("duration_ms")),
                ),
                now_ms=now_ms,
            )
        if event == "stt.utterance_end":
            return await self.session.handle_stt_event(
                SttUtteranceEnded(
                    type="stt.utterance_ended",
                    text=str(message.get("text") or ""),
                    confidence=_optional_float(message.get("confidence")),
                    timestamps=_timestamps(message, now_ms),
                ),
                now_ms=now_ms,
            )
        raise ValueError(f"unsupported v2 simulator STT event: {event!r}")

    def _outbound_messages(self, result: CallSessionResult) -> list[dict[str, Any]]:
        messages = [
            self.adapter.build_clear_audio(command)
            for command in result.clear_audio_commands
        ]
        messages.extend(
            self.adapter.build_send_audio(command)
            for command in result.outbound_audio_frames
        )
        if result.end_call:
            messages.append({"event": "v2.end_call"})
        if messages:
            messages.append(self._trace_message())
        self.sent_messages.extend(messages)
        return messages

    def _trace_message(self) -> dict[str, Any]:
        return {
            "event": "v2.trace",
            "trace": self.session.trace.to_list(),
            "state": self.session.state_machine.state.value,
        }

    def _persisted_message(self) -> dict[str, Any]:
        return {
            "event": "v2.persisted",
            "turns": [
                {
                    "generation_id": turn.generation_id,
                    "role": turn.role,
                    "message_id": turn.message_id,
                    "text": turn.text,
                    "committed_at_ms": turn.committed_at_ms,
                }
                for turn in self.persistence.turns
            ],
        }


async def run_call_v2_simulator_websocket(
    websocket: WebSocket,
    *,
    call_id: str,
    real_audio: bool = False,
) -> None:
    harness = CallV2SimulatorHarness.create(call_id=call_id, real_audio=real_audio)
    await websocket.accept()
    await websocket.send_json(
        {
            "event": "v2.ready",
            "call_id": call_id,
            "mode": "real_audio" if real_audio else "fake",
            "controls": [
                "stt.final",
                "stt.endpoint",
                "stt.transcribe_buffer",
                "audio.reset_buffer",
                "time.advance",
                "tts.completed",
                "trace.get",
                "persisted.get",
            ],
        }
    )
    try:
        while True:
            message = await websocket.receive_json()
            try:
                outbound_messages = await harness.handle_message(message)
            except (KeyError, TypeError, ValueError) as exc:
                await websocket.send_json(
                    {
                        "event": "v2.error",
                        "message": str(exc),
                    }
                )
                continue
            for outbound in outbound_messages:
                await websocket.send_json(outbound)
            if any(item.get("event") == "v2.end_call" for item in outbound_messages):
                await websocket.close()
                return
    except WebSocketDisconnect:
        return


def _default_agent_config() -> AgentConfig:
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


def _timestamps(message: dict[str, Any], now_ms: int) -> TimestampMetadata:
    return TimestampMetadata(
        backend_received_at_ms=now_ms,
        provider_timestamp_ms=_optional_int(message.get("provider_timestamp_ms")),
        audio_offset_ms=_optional_int(message.get("audio_offset_ms")),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
