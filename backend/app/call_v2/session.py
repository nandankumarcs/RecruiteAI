"""Call v2 session orchestration with fake-provider friendly boundaries."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

from app.call_v2.trace import monotonic_ms as _mono_ms

logger = logging.getLogger(__name__)

from app.call_v2.agent.config import (
    AgentConfig,
    AgentInput,
    AgentVisibleCallState,
    ConversationMessage,
)
from app.call_v2.agent.fingerprint import agent_input_fingerprint
from app.call_v2.agent.output import AgentOutput
from app.call_v2.agent.runner import AgentRunner
from app.call_v2.events import (
    AudioFormat,
    AgentRunCompleted,
    AgentRunStarted,
    CallIdentity,
    ClearOutboundAudio,
    SendAudioFrame,
    SttConnected,
    SttError,
    SttFinalSegment,
    SttInterimTranscript,
    SttSpeechStarted,
    SttTentativeEndpoint,
    SttUtteranceEnded,
    TelephonyAudioFrame,
    TelephonyStreamStarted,
    TelephonyStreamStopped,
    TentativeTurnCancelled,
    TentativeTurnStarted,
    TimestampMetadata,
    TurnConfirmed,
    TurnDiscarded,
)
from app.call_v2.ids import GenerationIdManager
from app.call_v2.persistence import CallPersistence, FakeCallPersistence
from app.call_v2.state import CallRuntimeState, CallStateMachine
from app.call_v2.stt.base import SttEngine, SttEvent
from app.call_v2.telephony.base import TelephonyAdapter, TelephonyInboundEvent
from app.call_v2.trace import TraceLogger
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.resolver import AudioPlaybackPlan, AudioSourceResolver
from app.call_v2.tts.sentence import split_sentences
from app.call_v2.turns.endpointing import EndpointingController, EndpointingSettings


CachePolicySelector = Callable[[AgentOutput], CachePolicy]


@dataclass(slots=True)
class CallSessionConfig:
    agent_config: AgentConfig
    call_id: str
    initial_call_state: AgentVisibleCallState
    cache_policy_selector: CachePolicySelector = lambda _output: CachePolicy()
    raw_audio_cancels_tentative_turns: bool = True
    opener_text: str | None = None
    # Pre-rendered opener text. When set, start_runtime_opener() speaks this
    # directly without running the LLM. Rendered from AgentConfig.opener_template
    # by the runtime factory. None means the agent generates the opener.


@dataclass(slots=True)
class CallSessionResult:
    outbound_audio_frames: list[SendAudioFrame] = field(default_factory=list)
    clear_audio_commands: list[ClearOutboundAudio] = field(default_factory=list)
    end_call: bool = False
    pending_sentences: list[asyncio.Task] = field(default_factory=list)
    stream_frames: object = None   # AsyncGenerator[list[SendAudioFrame], None] | None
    # Each task resolves to list[SendAudioFrame] for one subsequent sentence.
    # The runtime plays them in order after outbound_audio_frames finish.
    # Empty list means single-sentence response (existing behaviour).


@dataclass(slots=True)
class _StoredAgentRun:
    input_fingerprint: str
    output: AgentOutput
    stale: bool = False


class CallSession:
    """Orchestrates one call using normalized v2 boundaries."""

    def __init__(
        self,
        *,
        config: CallSessionConfig,
        telephony_adapter: TelephonyAdapter,
        stt_engine: SttEngine,
        agent_runner: AgentRunner,
        audio_resolver: AudioSourceResolver,
        persistence: CallPersistence | None = None,
        endpointing_settings: EndpointingSettings | None = None,
        trace: TraceLogger | None = None,
    ) -> None:
        self.config = config
        self.telephony_adapter = telephony_adapter
        self.stt_engine = stt_engine
        self.agent_runner = agent_runner
        self.audio_resolver = audio_resolver
        self.persistence = persistence or FakeCallPersistence()
        self.trace = trace or TraceLogger()
        self.generation_ids = GenerationIdManager()
        self.endpointing = EndpointingController(
            generation_ids=self.generation_ids,
            settings=endpointing_settings,
        )
        self.state_machine = CallStateMachine()
        self.identity: CallIdentity | None = None
        self.outbound_format: AudioFormat | None = None
        self.conversation: list[ConversationMessage] = []
        self.call_state = config.initial_call_state
        self._agent_runs: dict[int, _StoredAgentRun] = {}
        self._last_playback_plan: AudioPlaybackPlan | None = None
        self._end_after_speaking = False
        self._stt_engine_has_audio = False
        self._pending_sentence_tasks: dict[int, list[asyncio.Task]] = {}
        self._transition(CallRuntimeState.WAITING_FOR_STREAM, "session_created")

    async def handle_telephony_message(
        self,
        message: str | dict,
        *,
        now_ms: int,
        candidate_activity: bool = True,
    ) -> CallSessionResult:
        event = self.telephony_adapter.parse_inbound_message(
            message,
            backend_received_at_ms=now_ms,
        )
        if event is None:
            return CallSessionResult()
        return await self.handle_telephony_event(
            event,
            now_ms=now_ms,
            candidate_activity=candidate_activity,
        )

    async def handle_telephony_event(
        self,
        event: TelephonyInboundEvent,
        *,
        now_ms: int,
        candidate_activity: bool = True,
    ) -> CallSessionResult:
        self._trace_payload(event)
        if isinstance(event, TelephonyStreamStarted):
            self.identity = event.identity
            self.outbound_format = event.outbound_format
            await self.persistence.mark_call_started(
                identity=event.identity,
                started_at_ms=now_ms,
            )
            self._transition(CallRuntimeState.LISTENING, "stream_started")
            return CallSessionResult()
        if isinstance(event, TelephonyAudioFrame):
            self.identity = event.identity
            await self.stt_engine.send_audio(event)
            self._stt_engine_has_audio = True
            candidate_activity = (
                candidate_activity
                and self.config.raw_audio_cancels_tentative_turns
                and _frame_has_candidate_activity(event)
            )
            turn_events = self.endpointing.on_audio_frame(
                event,
                candidate_activity=candidate_activity,
            )
            return await self._handle_turn_events(turn_events, now_ms=now_ms)
        if isinstance(event, TelephonyStreamStopped):
            return await self.end(reason=event.reason or "provider_stop", now_ms=now_ms)
        return CallSessionResult()

    async def handle_stt_event(
        self,
        event: SttEvent,
        *,
        now_ms: int,
    ) -> CallSessionResult:
        self._trace_payload(event)
        if isinstance(event, SttConnected):
            return CallSessionResult()
        if isinstance(event, SttSpeechStarted):
            return await self._handle_turn_events(
                self.endpointing.on_speech_started(event),
                now_ms=now_ms,
            )
        if isinstance(event, SttInterimTranscript):
            return await self._handle_turn_events(
                self.endpointing.on_interim_transcript(event),
                now_ms=now_ms,
            )
        if isinstance(event, SttFinalSegment):
            if self.state_machine.state == CallRuntimeState.SPEAKING and event.text.strip():
                return await self._handle_transcript_barge_in(event, now_ms=now_ms)
            return await self._handle_turn_events(
                self.endpointing.on_final_segment(event),
                now_ms=now_ms,
            )
        if isinstance(event, SttTentativeEndpoint):
            return await self._handle_turn_events(
                self.endpointing.on_tentative_endpoint(event),
                now_ms=now_ms,
            )
        if isinstance(event, SttUtteranceEnded):
            return await self._handle_turn_events(
                self.endpointing.on_utterance_ended(event),
                now_ms=now_ms,
            )
        if isinstance(event, SttError):
            self._transition(CallRuntimeState.RECOVERING, "stt_error")
            if not event.recoverable:
                return await self.end(reason="stt_unrecoverable", now_ms=now_ms)
            return CallSessionResult()
        return CallSessionResult()

    async def advance_time(self, now_ms: int) -> CallSessionResult:
        return await self._handle_turn_events(
            self.endpointing.advance_time(now_ms),
            now_ms=now_ms,
        )

    async def start_runtime_opener(self, *, now_ms: int) -> CallSessionResult:
        """Speak the opener without committing a user turn.

        When config.opener_text is set the agent is bypassed entirely — the
        text is spoken directly and its TTS may already be cached.  When it is
        None the agent generates the opener dynamically (slower, but flexible).
        """
        if self.identity is None:
            raise RuntimeError("cannot start opener before telephony stream starts")

        generation_id = self.generation_ids.start_generation()
        self.generation_ids.mark_confirmed(generation_id)
        self._transition(CallRuntimeState.AGENT_RUNNING, "runtime_opener")

        if self.config.opener_text:
            logger.info(
                "opener.template call=%s gen=%d text_len=%d",
                self.config.call_id,
                generation_id,
                len(self.config.opener_text),
            )
            output = AgentOutput(
                spoken_text=self.config.opener_text,
                action="continue",
            )
        else:
            logger.info(
                "opener.agent_generated call=%s gen=%d",
                self.config.call_id,
                generation_id,
            )
            output = await self._start_agent_run(
                TurnConfirmed(
                    type="turn.confirmed",
                    generation_id=generation_id,
                    text=(
                        "The call media stream has connected. Greet the candidate, "
                        "briefly identify the purpose of the call, mention recording "
                        "if appropriate, and ask for consent to continue."
                    ),
                    confidence=None,
                    duration_ms=None,
                    evidence={"source": "runtime_opener"},
                    timestamps=TimestampMetadata(backend_received_at_ms=now_ms),
                ),
                speculative=False,
                now_ms=now_ms,
            )

        await self._commit_assistant_turn(
            generation_id=generation_id,
            text=output.spoken_text,
            committed_at_ms=now_ms,
        )
        return await self._speak_agent_output(
            generation_id=generation_id,
            output=output,
            now_ms=now_ms,
            cache_policy_override=CachePolicy(
                category="consent_opener",
                allow_persistent_store=True,
            ),
        )

    async def complete_tts(self, *, now_ms: int) -> None:
        self.endpointing.mark_tts_completed(now_ms)
        if self.state_machine.state == CallRuntimeState.SPEAKING:
            if self._end_after_speaking:
                await self.end(reason="agent_end_call_after_speaking", now_ms=now_ms)
            else:
                self._transition(CallRuntimeState.POST_TTS_GUARD, "tts_completed")

    async def end(self, *, reason: str, now_ms: int) -> CallSessionResult:
        if self.state_machine.state != CallRuntimeState.ENDED:
            if self.state_machine.state != CallRuntimeState.ENDING:
                self._transition(CallRuntimeState.ENDING, reason)
            await self.stt_engine.close()
            await self.persistence.mark_call_ended(
                ended_at_ms=now_ms,
                reason=reason,
            )
            self._transition(CallRuntimeState.ENDED, reason)
        return CallSessionResult(end_call=True)

    async def _handle_transcript_barge_in(
        self,
        event: SttFinalSegment,
        *,
        now_ms: int,
    ) -> CallSessionResult:
        command: ClearOutboundAudio | None = None
        if self.identity is not None:
            generation_id = self.generation_ids.latest_confirmed_generation_id
            command = ClearOutboundAudio(
                type="telephony.clear_outbound_audio",
                identity=self.identity,
                generation_id=generation_id,
                reason="candidate_barge_in",
            )
            self._trace_payload(command)
            if generation_id is not None:
                self.audio_resolver.cancel(generation_id)

        self.endpointing.mark_assistant_speaking(False)
        self._transition(CallRuntimeState.LISTENING, "candidate_barge_in")
        result = await self._handle_turn_events(
            self.endpointing.on_final_segment(event),
            now_ms=now_ms,
        )
        if command is not None:
            result.clear_audio_commands.append(command)
        return result

    async def _handle_turn_events(
        self,
        events: list[
            TentativeTurnStarted
            | TentativeTurnCancelled
            | TurnConfirmed
            | TurnDiscarded
        ],
        *,
        now_ms: int,
    ) -> CallSessionResult:
        result = CallSessionResult()
        for event in events:
            self._trace_payload(event)
            if isinstance(event, TentativeTurnStarted):
                self._transition(CallRuntimeState.SPECULATING, "tentative_turn")
                await self._start_agent_run(event, speculative=True, now_ms=now_ms)
            elif isinstance(event, TentativeTurnCancelled):
                self._mark_agent_stale(event.generation_id)
                if self.state_machine.state == CallRuntimeState.SPECULATING:
                    self._transition(CallRuntimeState.LISTENING, event.reason)
            elif isinstance(event, TurnConfirmed):
                playback = await self._handle_confirmed_turn(event, now_ms=now_ms)
                result.outbound_audio_frames.extend(playback.outbound_audio_frames)
                result.end_call = result.end_call or playback.end_call
                result.pending_sentences.extend(playback.pending_sentences)
                if playback.stream_frames is not None:
                    result.stream_frames = playback.stream_frames
            elif isinstance(event, TurnDiscarded):
                if self.state_machine.state == CallRuntimeState.SPECULATING:
                    self._transition(CallRuntimeState.LISTENING, event.reason)
        return result

    async def _start_agent_run(
        self,
        event: TentativeTurnStarted | TurnConfirmed,
        *,
        speculative: bool,
        now_ms: int,
    ) -> AgentOutput:
        agent_input = self._agent_input(
            generation_id=event.generation_id,
            text=event.text,
            speculative=speculative,
            created_at_ms=event.timestamps.backend_received_at_ms,
        )
        fingerprint = agent_input_fingerprint(agent_input)
        self._trace_payload(
            AgentRunStarted(
                type="agent.run_started",
                generation_id=event.generation_id,
                speculative=speculative,
                input_fingerprint=fingerprint,
                timestamps=TimestampMetadata(backend_received_at_ms=now_ms),
            )
        )
        logger.info(
            "agent.run_started call=%s gen=%d speculative=%s",
            self.config.call_id,
            event.generation_id,
            speculative,
        )
        agent_start_ms = _mono_ms()
        output = await self.agent_runner.run(agent_input)
        agent_latency_ms = _mono_ms() - agent_start_ms

        self._agent_runs[event.generation_id] = _StoredAgentRun(
            input_fingerprint=fingerprint,
            output=output,
            stale=False,
        )
        self._trace_payload(
            AgentRunCompleted(
                type="agent.run_completed",
                generation_id=event.generation_id,
                speculative=speculative,
                result=output.to_dict(),
                usage=None,
                latency_ms=agent_latency_ms,
                timestamps=TimestampMetadata(backend_received_at_ms=now_ms),
            )
        )
        logger.info(
            "agent.run_completed call=%s gen=%d speculative=%s latency_ms=%d action=%s",
            self.config.call_id,
            event.generation_id,
            speculative,
            agent_latency_ms,
            output.action,
        )
        return output

    async def _handle_confirmed_turn(
        self,
        event: TurnConfirmed,
        *,
        now_ms: int,
    ) -> CallSessionResult:
        run = self._agent_runs.get(event.generation_id)
        expected_fingerprint = agent_input_fingerprint(
            self._agent_input(
                generation_id=event.generation_id,
                text=event.text,
                speculative=False,
                created_at_ms=event.timestamps.backend_received_at_ms,
            )
        )
        if (
            run is None
            or run.stale
            or run.input_fingerprint != expected_fingerprint
        ):
            self._transition(CallRuntimeState.AGENT_RUNNING, "agent_run_required")
            output = await self._start_agent_run(event, speculative=False, now_ms=now_ms)
            run = self._agent_runs[event.generation_id]
        else:
            output = run.output

        if not self.generation_ids.can_speak(event.generation_id):
            self._mark_agent_stale(event.generation_id)
            logger.warning(
                "turn.stale_discarded call=%s gen=%d",
                self.config.call_id,
                event.generation_id,
            )
            return CallSessionResult()

        logger.info(
            "turn.confirmed call=%s gen=%d text_len=%d",
            self.config.call_id,
            event.generation_id,
            len(event.text),
        )
        user_commit = await self.persistence.commit_transcript_turn(
            generation_id=event.generation_id,
            role="user",
            text=event.text,
            committed_at_ms=now_ms,
        )
        self._trace_payload(user_commit)
        self.conversation.append(
            ConversationMessage(
                role="user",
                content=event.text,
                message_id=user_commit.message_id,
                generation_id=event.generation_id,
                committed=True,
                interrupted=False,
                created_at_ms=now_ms,
            )
        )

        await self._commit_assistant_turn(
            generation_id=event.generation_id,
            text=output.spoken_text,
            committed_at_ms=now_ms,
        )

        return await self._speak_agent_output(
            generation_id=event.generation_id,
            output=output,
            now_ms=now_ms,
        )

    async def _commit_assistant_turn(
        self,
        *,
        generation_id: int,
        text: str,
        committed_at_ms: int,
    ) -> None:
        assistant_commit = await self.persistence.commit_transcript_turn(
            generation_id=generation_id,
            role="assistant",
            text=text,
            committed_at_ms=committed_at_ms,
        )
        self._trace_payload(assistant_commit)
        self.conversation.append(
            ConversationMessage(
                role="assistant",
                content=text,
                message_id=assistant_commit.message_id,
                generation_id=generation_id,
                committed=True,
                interrupted=False,
                created_at_ms=committed_at_ms,
            )
        )

    async def _speak_agent_output(
        self,
        *,
        generation_id: int,
        output: AgentOutput,
        now_ms: int,
        cache_policy_override: CachePolicy | None = None,
    ) -> CallSessionResult:
        if self.identity is None:
            raise RuntimeError("cannot speak before telephony stream starts")

        cache_policy = (
            cache_policy_override
            if cache_policy_override is not None
            else self.config.cache_policy_selector(output)
        )
        # split_sentences only used by the batch path (non-streaming engines).
        sentences = split_sentences(output.spoken_text)

        self._transition(CallRuntimeState.SPEAKING, "assistant_audio_ready")
        self.endpointing.mark_assistant_speaking(True)
        self._end_after_speaking = output.action == "end_call_after_speaking"

        # Use chunk streaming when the TTS engine supports it (SarvamTtsEngine).
        # Non-streaming engines (FakeTtsEngine, OpenAITtsEngine) use the batch path.
        engine_supports_chunked = callable(
            getattr(self.audio_resolver.primary_tts, "synthesize_chunked", None)
        )

        if engine_supports_chunked:
            # ── Streaming path: send full response text as one HTTP stream ────
            # No sentence splitting needed — Sarvam yields chunks within ~500ms
            # regardless of text length, and maintains natural prosody across the
            # full response. The complete audio is cached after streaming completes
            # so future identical responses are instant cache hits.
            stream_cache_policy = cache_policy_override or CachePolicy(
                category="sentence_audio",
                allow_persistent_store=True,
            )
            stream = self.audio_resolver.resolve_stream(
                generation_id=generation_id,
                spoken_text=output.spoken_text,
                identity=self.identity,
                output_format=self.identity_audio_format(),
                telephony_provider=self.identity.provider,
                cache_policy=stream_cache_policy,
                generation_ids=self.generation_ids,
                now_ms=now_ms,
            )
            logger.info(
                "tts.stream gen=%d provider=%s text_len=%d",
                generation_id,
                self.audio_resolver.primary_tts.provider,
                len(output.spoken_text),
            )
            return CallSessionResult(
                stream_frames=stream,
                end_call=output.action == "end_call_after_speaking",
            )

        # ── Batch path: sentence splitting + parallel synthesis ────────────────
        # Still used for non-streaming engines (OpenAI TTS, FakeTtsEngine).
        if len(sentences) <= 1:
            plan = await self._resolve_sentence(
                index=0, total=1,
                text=output.spoken_text,
                generation_id=generation_id,
                cache_policy=cache_policy,
                now_ms=now_ms,
            )
            self._last_playback_plan = plan
            self._trace_payload(plan.source_event)
            return CallSessionResult(
                outbound_audio_frames=plan.frames,
                end_call=output.action == "end_call_after_speaking",
            )

        sentence_tasks = [
            asyncio.create_task(
                self._resolve_sentence(
                    index=i, total=len(sentences), text=s,
                    generation_id=generation_id,
                    cache_policy=cache_policy, now_ms=now_ms,
                )
            )
            for i, s in enumerate(sentences)
        ]
        self._pending_sentence_tasks[generation_id] = sentence_tasks
        plan_0 = await sentence_tasks[0]
        self._last_playback_plan = plan_0
        self._trace_payload(plan_0.source_event)
        return CallSessionResult(
            outbound_audio_frames=plan_0.frames,
            end_call=output.action == "end_call_after_speaking",
            pending_sentences=sentence_tasks[1:],
        )

    async def _resolve_sentence(
        self,
        *,
        index: int,
        total: int,
        text: str,
        generation_id: int,
        cache_policy: CachePolicy,
        now_ms: int,
    ) -> AudioPlaybackPlan:
        """Resolve one sentence to audio frames, logging latency and source."""
        from app.call_v2.trace import monotonic_ms as _mono_ms_local
        t0 = _mono_ms_local()
        plan = await self.audio_resolver.resolve(
            generation_id=generation_id,
            spoken_text=text,
            identity=self.identity,  # type: ignore[arg-type]
            output_format=self.identity_audio_format(),
            telephony_provider=self.identity.provider,  # type: ignore[union-attr]
            cache_policy=cache_policy,
            generation_ids=self.generation_ids,
            now_ms=now_ms,
        )
        logger.info(
            "sentence.tts_ready gen=%d sentence=%d/%d latency_ms=%d bytes=%d source=%s text_len=%d",
            generation_id, index, total,
            _mono_ms_local() - t0,
            len(plan.audio.payload),
            plan.source_event.source,
            len(text),
        )
        return plan

    def identity_audio_format(self) -> AudioFormat:
        if self.outbound_format is None:
            raise RuntimeError("telephony stream has not started")
        return self.outbound_format

    @property
    def stt_engine_has_audio(self) -> bool:
        return self._stt_engine_has_audio

    def _agent_input(
        self,
        *,
        generation_id: int,
        text: str,
        speculative: bool,
        created_at_ms: int,
    ) -> AgentInput:
        latest_user_turn = ConversationMessage(
            role="user",
            content=text,
            message_id=f"turn-{generation_id}-tentative"
            if speculative
            else f"turn-{generation_id}-confirmed",
            generation_id=generation_id,
            committed=not speculative,
            interrupted=False,
            created_at_ms=created_at_ms,
        )
        return AgentInput(
            call_id=self.config.call_id,
            generation_id=generation_id,
            speculative=speculative,
            agent_config=self.config.agent_config,
            call_state=self.call_state,
            conversation=self.conversation.copy(),
            latest_user_turn=latest_user_turn,
            available_tools=[],
        )

    def _mark_agent_stale(self, generation_id: int) -> None:
        run = self._agent_runs.get(generation_id)
        if run is not None:
            run.stale = True
        self.audio_resolver.cancel(generation_id)
        for task in self._pending_sentence_tasks.pop(generation_id, []):
            task.cancel()

    def _transition(self, next_state: CallRuntimeState, reason: str) -> None:
        if self.state_machine.state == next_state:
            return
        transition = self.state_machine.transition_to(next_state, reason=reason)
        self.trace.emit(
            "state.transition",
            call_id=self.config.call_id,
            data={
                "previous_state": transition.previous_state.value,
                "next_state": transition.next_state.value,
                "reason": transition.reason,
            },
        )

    def _trace_payload(self, payload) -> None:
        generation_id = getattr(payload, "generation_id", None)
        payload_type = getattr(payload, "type", payload.__class__.__name__)
        data = payload.to_dict() if hasattr(payload, "to_dict") else {}
        self.trace.emit(
            payload_type,
            call_id=self.config.call_id,
            generation_id=generation_id,
            data=data,
            at_ms=getattr(
                getattr(payload, "timestamps", None),
                "backend_received_at_ms",
                None,
            ),
        )


def _frame_has_candidate_activity(event: TelephonyAudioFrame) -> bool:
    if event.format.codec != "linear16":
        return bool(event.payload)
    if len(event.payload) < 2:
        return False

    sample_count = len(event.payload) // 2
    total_square = 0
    max_abs = 0
    for index in range(sample_count):
        start = index * 2
        sample = int.from_bytes(
            event.payload[start : start + 2],
            byteorder="little",
            signed=True,
        )
        abs_sample = abs(sample)
        max_abs = max(max_abs, abs_sample)
        total_square += sample * sample
    rms = (total_square / sample_count) ** 0.5
    return max_abs >= 1000 or rms >= 300
