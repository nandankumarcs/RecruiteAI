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
    # Silence escalation thresholds (ms) — see app.config.Settings for the
    # corresponding env vars. silence_nudge_ms <= 0 disables the feature
    # (useful in unit tests that don't want time-based behaviour interfering).
    silence_nudge_ms: int = 5000
    silence_nudge_escalate_ms: int = 12000
    silence_endcall_ms: int = 20000


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


# Pre-canned silence-nudge phrases. Generic on purpose so their TTS can be
# cached across calls (no candidate-specific placeholders). The end-call
# phrase doubles as the spoken closer when we hit the hard timeout.
_SILENCE_NUDGE_PHRASES: dict[int, str] = {
    1: "Are you still there?",
    2: "I can't hear you. Are you able to continue?",
}
_SILENCE_ENDCALL_PHRASE = (
    "It seems we got disconnected. I'll end the call here. Thank you for your time."
)


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
        # In-flight speculative agent tasks, keyed by generation_id.
        # Launched fire-and-forget from _handle_turn_events so the caller's
        # state_lock can be released while the LLM call is in flight, which
        # keeps audio forwarding to STT unblocked during long agent runs.
        # _handle_confirmed_turn awaits the matching task before consuming
        # the result. _mark_agent_stale cancels it. end() cancels all.
        self._pending_agent_tasks: dict[int, asyncio.Task] = {}
        self._last_playback_plan: AudioPlaybackPlan | None = None
        self._end_after_speaking = False
        # When _end_after_speaking is True, this carries the reason passed to
        # self.end() once TTS completes. Default reason is the agent-driven
        # one; the silence escalation path overrides it to "silence_timeout".
        self._end_after_speaking_reason: str = "agent_end_call_after_speaking"
        self._stt_engine_has_audio = False
        self._pending_sentence_tasks: dict[int, list[asyncio.Task]] = {}
        # Silence-nudge state. _silence_started_at_ms is the wall-clock origin
        # of the current silence window — set when the AI finishes speaking
        # (POST_TTS_GUARD), cleared on any candidate STT event. _nudge_stage
        # tracks which nudges we've already fired this round (0/1/2) so we
        # don't re-fire the same level on every advance_time tick.
        self._silence_started_at_ms: int | None = None
        self._nudge_stage: int = 0
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
        # Reset the silence escalation only on EVENTS THAT REPRESENT REAL
        # CANDIDATE SPEECH. SttSpeechStarted is just Deepgram VAD — it
        # fires on TTS echo bleeding through the candidate microphone, on
        # background noise, and on any pulse Deepgram's voice detector
        # picks up. Likewise, Interim/Final events with confidence == 0
        # are Deepgram's signal for "I'm not confident this is real" — in
        # practice, that's what we get when the AI's own opener audio
        # ("junior AI engineer position") gets transcribed back as the
        # word "AI" with confidence 0. Filter those out so a silent
        # candidate's mic loopback doesn't keep wiping the silence timer.
        if self._is_real_candidate_speech(event):
            self._reset_silence_tracking()
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
        # Silence escalation has priority over turn-confirmation. If the
        # candidate has been silent past the configured threshold, fire the
        # nudge / escalate / end-call. Otherwise fall through to normal
        # endpointing-driven turn handling.
        silence_result = await self._maybe_fire_silence_action(now_ms)
        if silence_result is not None:
            return silence_result
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

    # -----------------------------------------------------------------------
    # Silence escalation: nudge / escalate / end-call when the candidate
    # is silent past configured thresholds. See _maybe_fire_silence_action
    # and the SILENCE_NUDGE_* settings in app.config.Settings.
    # -----------------------------------------------------------------------

    def _reset_silence_tracking(self) -> None:
        """Cancel any in-progress silence window.

        Called only when we have high-confidence evidence of real
        candidate speech (see _is_real_candidate_speech). _nudge_stage is
        reset to 0 so the next silence round starts fresh from stage 1.
        """
        self._silence_started_at_ms = None
        self._nudge_stage = 0

    def _is_real_candidate_speech(self, event) -> bool:
        """Return True if `event` represents real candidate speech.

        Filters out the two main sources of false positives we observed:

        * SttSpeechStarted — Deepgram VAD with no text. Fires on TTS echo
          and ambient noise. Cannot be trusted as a silence-cancel signal.
        * Interim/Final/TentativeEndpoint with confidence == 0 — Deepgram's
          own marker for "I'm not sure this is real". In our voice pipeline
          we see this when the AI's own audio bleeds into the candidate
          microphone via the speaker.

        SttUtteranceEnded always counts as real — it's an explicit signal
        that an utterance has ended, which means one happened.
        """
        if isinstance(event, SttSpeechStarted):
            return False
        if isinstance(event, SttUtteranceEnded):
            return True
        if isinstance(event, (
            SttInterimTranscript,
            SttFinalSegment,
            SttTentativeEndpoint,
        )):
            text = (getattr(event, "text", "") or "").strip()
            if not text:
                return False
            confidence = getattr(event, "confidence", None)
            if confidence is not None and confidence <= 0:
                return False
            return True
        return False

    async def _maybe_fire_silence_action(
        self, now_ms: int
    ) -> CallSessionResult | None:
        """Check if a silence nudge or end-call should fire on this tick.

        Returns a CallSessionResult containing the nudge / end-call audio if
        one is due, otherwise None (so the caller falls through to normal
        endpointing-driven turn handling).
        """
        if self.config.silence_nudge_ms <= 0:
            return None
        if self._silence_started_at_ms is None:
            return None
        # Only fire when we're genuinely waiting for the candidate. Don't
        # interrupt our own TTS, the agent, or a tentative turn that's
        # already in flight.
        if self.state_machine.state not in (
            CallRuntimeState.LISTENING,
            CallRuntimeState.POST_TTS_GUARD,
        ):
            return None
        if self.endpointing.pending_turn is not None:
            return None

        elapsed = now_ms - self._silence_started_at_ms
        # End-call has highest priority. Note we fire it independent of
        # _nudge_stage — even if we never got to stage 2, after 20s of total
        # silence the call should end politely.
        if elapsed >= self.config.silence_endcall_ms:
            return await self._speak_silence_endcall(now_ms=now_ms)
        if (
            elapsed >= self.config.silence_nudge_escalate_ms
            and self._nudge_stage < 2
        ):
            return await self._speak_silence_nudge(stage=2, now_ms=now_ms)
        if elapsed >= self.config.silence_nudge_ms and self._nudge_stage < 1:
            return await self._speak_silence_nudge(stage=1, now_ms=now_ms)
        return None

    async def _speak_silence_nudge(
        self, *, stage: int, now_ms: int
    ) -> CallSessionResult:
        """Fire a pre-canned silence nudge as a real assistant turn.

        Reuses the regular _speak_agent_output path so the nudge plays via
        the same TTS pipeline (including cache), is committed as an
        assistant message, and respects barge-in (a candidate speaking
        mid-nudge cancels the TTS via the existing transcript barge-in
        handler).
        """
        text = _SILENCE_NUDGE_PHRASES[stage]
        generation_id = self.generation_ids.start_generation()
        self.generation_ids.mark_confirmed(generation_id)
        self._nudge_stage = stage
        # NOTE: do not clear _silence_started_at_ms here. The escalation
        # thresholds (5s/12s/20s) are measured from the original silence
        # origin, not from each nudge's end. complete_tts will skip
        # re-arming so the origin persists through the nudge sequence.

        # POST_TTS_GUARD cannot transition directly to SPEAKING per the
        # state machine, so step through LISTENING first when needed.
        if self.state_machine.state == CallRuntimeState.POST_TTS_GUARD:
            self._transition(CallRuntimeState.LISTENING, "silence_nudge_prep")

        logger.info(
            "silence.nudge call=%s gen=%d stage=%d text_len=%d elapsed_ms=%d",
            self.config.call_id,
            generation_id,
            stage,
            len(text),
            now_ms - (self._silence_started_at_ms or now_ms),
        )

        await self._commit_assistant_turn(
            generation_id=generation_id,
            text=text,
            committed_at_ms=now_ms,
        )
        return await self._speak_agent_output(
            generation_id=generation_id,
            output=AgentOutput(spoken_text=text, action="continue"),
            now_ms=now_ms,
            cache_policy_override=CachePolicy(
                category=f"silence_nudge_stage_{stage}",
                allow_persistent_store=True,
            ),
        )

    async def _speak_silence_endcall(self, *, now_ms: int) -> CallSessionResult:
        """Speak the silence-timeout closer and schedule the call to end.

        Sets _end_after_speaking_reason so that complete_tts will call
        self.end() with reason='silence_timeout' (rather than the default
        agent-driven reason), giving analytics a way to distinguish
        silence-driven ends from agent-driven ones.
        """
        text = _SILENCE_ENDCALL_PHRASE
        generation_id = self.generation_ids.start_generation()
        self.generation_ids.mark_confirmed(generation_id)
        self._silence_started_at_ms = None  # halt the silence ladder

        if self.state_machine.state == CallRuntimeState.POST_TTS_GUARD:
            self._transition(CallRuntimeState.LISTENING, "silence_endcall_prep")

        logger.info(
            "silence.end_call call=%s gen=%d",
            self.config.call_id,
            generation_id,
        )

        # _speak_agent_output reads action='end_call_after_speaking' to set
        # _end_after_speaking. We override the reason it uses on completion.
        self._end_after_speaking_reason = "silence_timeout"
        await self._commit_assistant_turn(
            generation_id=generation_id,
            text=text,
            committed_at_ms=now_ms,
        )
        return await self._speak_agent_output(
            generation_id=generation_id,
            output=AgentOutput(
                spoken_text=text, action="end_call_after_speaking"
            ),
            now_ms=now_ms,
            cache_policy_override=CachePolicy(
                category="silence_endcall",
                allow_persistent_store=True,
            ),
        )

    async def complete_tts(self, *, now_ms: int) -> None:
        self.endpointing.mark_tts_completed(now_ms)
        if self.state_machine.state == CallRuntimeState.SPEAKING:
            if self._end_after_speaking:
                await self.end(reason=self._end_after_speaking_reason, now_ms=now_ms)
            else:
                self._transition(CallRuntimeState.POST_TTS_GUARD, "tts_completed")
                # Arm the silence window the moment the AI stops speaking,
                # BUT only when we're not mid-way through a nudge round.
                # During an active nudge sequence (_nudge_stage > 0), the
                # origin must stay anchored at the candidate's last real
                # activity so the 5s/12s/20s thresholds describe the total
                # silence budget — not "5s after each nudge ends".
                if self._nudge_stage == 0:
                    self._silence_started_at_ms = now_ms

    async def end(self, *, reason: str, now_ms: int) -> CallSessionResult:
        if self.state_machine.state != CallRuntimeState.ENDED:
            if self.state_machine.state != CallRuntimeState.ENDING:
                self._transition(CallRuntimeState.ENDING, reason)
            # Cancel any in-flight speculative agent tasks so they don't keep
            # running (and racing on session state) after the call has ended.
            for task in list(self._pending_agent_tasks.values()):
                if not task.done():
                    task.cancel()
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
                # Launch the speculative agent run as a background task so the
                # caller's state_lock is released while the LLM call is in
                # flight. Without this, the lock is held for the full agent
                # latency (~500–1700ms), during which inbound audio frames
                # cannot be forwarded to STT — and if the lockout exceeds the
                # endpointing threshold, Deepgram fires a false speech_final
                # mid-sentence. _handle_confirmed_turn awaits the matching
                # task before consuming its result.
                self._launch_speculative_agent_run(event, now_ms=now_ms)
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

    def _launch_speculative_agent_run(
        self,
        event: TentativeTurnStarted,
        *,
        now_ms: int,
    ) -> None:
        """Fire the speculative agent run as a background task.

        Caller can release its lock immediately. The task stores its result
        in self._agent_runs[generation_id] on completion. _handle_confirmed_turn
        awaits the matching entry in self._pending_agent_tasks before
        consuming the stored result.
        """
        generation_id = event.generation_id
        # If a task already exists for this generation_id, leave it alone:
        # the endpointing layer never re-emits TentativeTurnStarted for the
        # same generation_id (replacements get a fresh id), so this is purely
        # a defensive guard.
        existing = self._pending_agent_tasks.get(generation_id)
        if existing is not None and not existing.done():
            return

        task = asyncio.create_task(
            self._safe_speculative_agent_run(event, now_ms=now_ms)
        )
        self._pending_agent_tasks[generation_id] = task
        # Auto-prune so the dict doesn't grow without bound across a long call.
        task.add_done_callback(
            lambda _t, gid=generation_id: self._pending_agent_tasks.pop(gid, None)
        )

    async def _safe_speculative_agent_run(
        self,
        event: TentativeTurnStarted,
        *,
        now_ms: int,
    ) -> None:
        """Wrap _start_agent_run with clean error/cancel handling.

        On CancelledError (from _mark_agent_stale or end()): re-raise so
        asyncio marks the task cancelled. No stored run is written, so
        _handle_confirmed_turn will fall through to a fresh sync run if
        TurnConfirmed ever fires for this generation_id.

        On unexpected exceptions: log and swallow. The agent_runner already
        emits its own error traces. Same fallback applies.
        """
        try:
            await self._start_agent_run(event, speculative=True, now_ms=now_ms)
        except asyncio.CancelledError:
            logger.info(
                "agent.speculative_cancelled call=%s gen=%d",
                self.config.call_id,
                event.generation_id,
            )
            raise
        except Exception:
            logger.exception(
                "agent.speculative_failed call=%s gen=%d",
                self.config.call_id,
                event.generation_id,
            )

    async def _handle_confirmed_turn(
        self,
        event: TurnConfirmed,
        *,
        now_ms: int,
    ) -> CallSessionResult:
        # If a speculative agent run is still in flight for this generation,
        # wait for it before consuming the stored result. This restores the
        # invariant that _agent_runs[generation_id] is populated by the time
        # we check it. The wait does hold the caller's lock — but by this
        # point the user has been silent for confirmation_window_ms, so the
        # window for losing inbound audio is closed.
        pending = self._pending_agent_tasks.get(event.generation_id)
        if pending is not None and not pending.done():
            try:
                await pending
            except (asyncio.CancelledError, Exception):
                # Errors are logged inside _safe_speculative_agent_run.
                # Fall through to the no-run path which triggers a fresh
                # synchronous run below.
                pass

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
        # Cancel any in-flight speculative agent task for this generation.
        # Saves the wasted Groq API call (and the latency it adds to genuine
        # turns serialised behind it). The done_callback prunes the dict.
        pending = self._pending_agent_tasks.get(generation_id)
        if pending is not None and not pending.done():
            pending.cancel()
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
