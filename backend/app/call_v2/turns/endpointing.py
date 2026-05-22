"""Endpointing controller for call v2 speculative turn detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.call_v2.events import (
    SttFinalSegment,
    SttInterimTranscript,
    SttSpeechStarted,
    SttTentativeEndpoint,
    SttUtteranceEnded,
    TelephonyAudioFrame,
    TentativeTurnCancelled,
    TentativeTurnStarted,
    TimestampMetadata,
    TurnConfirmed,
    TurnDiscarded,
)
from app.call_v2.ids import GenerationIdManager
from app.call_v2.stt.transcript_assembler import TranscriptAssembler


@dataclass(frozen=True, slots=True)
class EndpointingSettings:
    confirmation_window_ms: int = 800
    post_tts_guard_ms: int = 800


@dataclass(slots=True)
class PendingTurn:
    generation_id: int
    text: str
    tentative_event: SttTentativeEndpoint
    started_at_ms: int
    confirmation_deadline_ms: int
    endpoint_audio_end_ms: int | None


class EndpointingController:
    """Converts stable STT events into tentative and confirmed user turns."""

    def __init__(
        self,
        *,
        generation_ids: GenerationIdManager | None = None,
        assembler: TranscriptAssembler | None = None,
        settings: EndpointingSettings | None = None,
    ) -> None:
        self.generation_ids = generation_ids or GenerationIdManager()
        self.assembler = assembler or TranscriptAssembler()
        self.settings = settings or EndpointingSettings()
        self.pending_turn: PendingTurn | None = None
        self.last_candidate_audio_backend_received_at_ms: int | None = None
        self.last_candidate_audio_offset_ms: int | None = None
        self.assistant_speaking = False
        self.post_tts_guard_until_ms: int | None = None

    def on_audio_frame(
        self,
        event: TelephonyAudioFrame,
        *,
        candidate_activity: bool = True,
    ) -> list[TentativeTurnCancelled]:
        if not candidate_activity:
            return []

        self.last_candidate_audio_backend_received_at_ms = (
            event.timestamps.backend_received_at_ms
        )
        if event.timestamps.audio_offset_ms is not None:
            self.last_candidate_audio_offset_ms = event.timestamps.audio_offset_ms

        if self.assistant_speaking:
            return []
        if self.pending_turn and self._audio_invalidates_pending(event):
            return [self._cancel_pending("audio_after_tentative", None)]
        return []

    def on_speech_started(
        self,
        event: SttSpeechStarted,
    ) -> list[TentativeTurnCancelled]:
        if self.assistant_speaking:
            return []
        if self.pending_turn:
            return [self._cancel_pending("speech_started_after_tentative", None)]
        return []

    def on_interim_transcript(
        self,
        event: SttInterimTranscript,
    ) -> list[TentativeTurnCancelled]:
        if self.assistant_speaking:
            return []
        if self.pending_turn and self._clean(event.text) != self.pending_turn.text:
            return [self._cancel_pending("interim_changed_after_tentative", None)]
        return []

    def on_final_segment(
        self,
        event: SttFinalSegment,
    ) -> list[TentativeTurnCancelled]:
        accepted = self.assembler.add_final_segment(event)
        if not accepted:
            return []
        if self.assistant_speaking:
            return []
        if self.pending_turn:
            return [self._cancel_pending("final_segment_after_tentative", None)]
        return []

    def on_tentative_endpoint(
        self,
        event: SttTentativeEndpoint,
    ) -> list[TentativeTurnStarted | TentativeTurnCancelled | TurnDiscarded]:
        text = self.assembler.tentative_text(event)
        if not text:
            return [
                TurnDiscarded(
                    type="turn.discarded",
                    generation_id=None,
                    text="",
                    reason="empty_tentative_endpoint",
                    timestamps=event.timestamps,
                )
            ]

        if self.pending_turn and self.pending_turn.text == text:
            return []

        events: list[TentativeTurnStarted | TentativeTurnCancelled | TurnDiscarded] = []
        replacement_generation_id: int | None = None
        if self.pending_turn:
            replacement_generation_id = self.generation_ids.start_generation()
            events.append(
                self._cancel_pending(
                    "replaced_by_new_tentative_endpoint",
                    replacement_generation_id,
                )
            )
            generation_id = replacement_generation_id
        else:
            generation_id = self.generation_ids.start_generation()

        pending = PendingTurn(
            generation_id=generation_id,
            text=text,
            tentative_event=event,
            started_at_ms=event.timestamps.backend_received_at_ms,
            confirmation_deadline_ms=(
                event.timestamps.backend_received_at_ms
                + self.settings.confirmation_window_ms
            ),
            endpoint_audio_end_ms=self._event_audio_end_ms(event),
        )
        self.pending_turn = pending

        events.append(
            TentativeTurnStarted(
                type="turn.tentative_started",
                generation_id=generation_id,
                text=text,
                source="stt_endpoint",
                evidence=self._pending_evidence(pending),
                timestamps=event.timestamps,
            )
        )
        return events

    def on_utterance_ended(
        self,
        event: SttUtteranceEnded,
    ) -> list[TentativeTurnStarted | TentativeTurnCancelled | TurnDiscarded]:
        endpoint = SttTentativeEndpoint(
            type="stt.tentative_endpoint",
            text=event.text,
            confidence=event.confidence,
            silence_ms=None,
            timestamps=event.timestamps,
            duration_ms=None,
        )
        return self.on_tentative_endpoint(endpoint)

    def advance_time(
        self,
        now_ms: int,
    ) -> list[TurnConfirmed | TentativeTurnCancelled]:
        if self.pending_turn is None:
            return []
        if now_ms < self.pending_turn.confirmation_deadline_ms:
            return []
        if self._fresh_audio_after_pending():
            return [self._cancel_pending("audio_after_tentative", None)]

        pending = self.pending_turn
        transcript = self.assembler.flush(pending.tentative_event)
        text = transcript.text if transcript is not None else pending.text
        confidence = transcript.confidence if transcript is not None else None
        duration_ms = transcript.duration_ms if transcript is not None else None

        self.generation_ids.mark_confirmed(pending.generation_id)
        self.pending_turn = None
        return [
            TurnConfirmed(
                type="turn.confirmed",
                generation_id=pending.generation_id,
                text=text,
                confidence=confidence,
                duration_ms=duration_ms,
                evidence={
                    **self._pending_evidence(pending),
                    "confirmed_at_ms": now_ms,
                },
                timestamps=TimestampMetadata(backend_received_at_ms=now_ms),
            )
        ]

    def mark_assistant_speaking(self, speaking: bool) -> None:
        self.assistant_speaking = speaking

    def mark_tts_completed(self, at_ms: int) -> None:
        self.assistant_speaking = False
        self.post_tts_guard_until_ms = at_ms + self.settings.post_tts_guard_ms

    def in_post_tts_guard(self, at_ms: int) -> bool:
        return (
            self.post_tts_guard_until_ms is not None
            and at_ms <= self.post_tts_guard_until_ms
        )

    def _cancel_pending(
        self,
        reason: str,
        replacement_generation_id: int | None,
    ) -> TentativeTurnCancelled:
        if self.pending_turn is None:
            raise RuntimeError("no pending turn to cancel")
        pending = self.pending_turn
        self.generation_ids.mark_stale(pending.generation_id)
        self.pending_turn = None
        return TentativeTurnCancelled(
            type="turn.tentative_cancelled",
            generation_id=pending.generation_id,
            reason=reason,
            replacement_generation_id=replacement_generation_id,
            timestamps=TimestampMetadata(
                backend_received_at_ms=self._latest_backend_time(pending)
            ),
        )

    def _audio_invalidates_pending(self, event: TelephonyAudioFrame) -> bool:
        if self.pending_turn is None:
            return False
        event_offset = event.timestamps.audio_offset_ms
        if (
            event_offset is not None
            and self.pending_turn.endpoint_audio_end_ms is not None
        ):
            return event_offset > self.pending_turn.endpoint_audio_end_ms
        return event.timestamps.backend_received_at_ms > self.pending_turn.started_at_ms

    def _fresh_audio_after_pending(self) -> bool:
        if self.pending_turn is None:
            return False
        if (
            self.last_candidate_audio_offset_ms is not None
            and self.pending_turn.endpoint_audio_end_ms is not None
        ):
            return (
                self.last_candidate_audio_offset_ms
                > self.pending_turn.endpoint_audio_end_ms
            )
        if self.last_candidate_audio_backend_received_at_ms is None:
            return False
        return (
            self.last_candidate_audio_backend_received_at_ms
            > self.pending_turn.started_at_ms
        )

    def _event_audio_end_ms(self, event: SttTentativeEndpoint) -> int | None:
        start = event.timestamps.audio_offset_ms
        if start is None:
            return None
        if event.duration_ms is None:
            return start
        return start + event.duration_ms

    def _pending_evidence(self, pending: PendingTurn) -> dict[str, Any]:
        return {
            "last_audio_backend_received_at_ms": (
                self.last_candidate_audio_backend_received_at_ms
            ),
            "last_audio_offset_ms": self.last_candidate_audio_offset_ms,
            "stt_backend_received_at_ms": pending.started_at_ms,
            "stt_audio_offset_ms": pending.tentative_event.timestamps.audio_offset_ms,
            "endpoint_audio_end_ms": pending.endpoint_audio_end_ms,
            "confirmation_deadline_ms": pending.confirmation_deadline_ms,
            "post_tts_guard": self.in_post_tts_guard(pending.started_at_ms),
        }

    def _latest_backend_time(self, pending: PendingTurn) -> int:
        if self.last_candidate_audio_backend_received_at_ms is None:
            return pending.started_at_ms
        return max(
            self.last_candidate_audio_backend_received_at_ms,
            pending.started_at_ms,
        )

    def _clean(self, text: str) -> str:
        return " ".join((text or "").split())
