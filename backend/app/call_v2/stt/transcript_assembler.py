"""Transcript assembly and deduplication for call v2 STT events."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.call_v2.events import SttFinalSegment, SttTentativeEndpoint, SttUtteranceEnded


@dataclass(frozen=True, slots=True)
class AssembledTranscript:
    text: str
    segment_count: int
    confidence: float | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class TranscriptAssembler:
    """Collects final STT segments into stable user-turn text."""

    _segments: list[SttFinalSegment] = field(default_factory=list)
    _segment_ids: set[str] = field(default_factory=set)

    def add_final_segment(self, event: SttFinalSegment) -> bool:
        text = self._clean(event.text)
        if not text:
            return False

        if event.segment_id and event.segment_id in self._segment_ids:
            return False

        if self._replace_overlapping_extension(event, text):
            return True

        if self._is_same_audio_duplicate(event, text):
            return False

        if self._is_suffix_duplicate(event, text):
            return False

        self._segments.append(event)
        if event.segment_id:
            self._segment_ids.add(event.segment_id)
        return True

    def _replace_overlapping_extension(
        self,
        event: SttFinalSegment,
        text: str,
    ) -> bool:
        overlapping_segments = [
            segment
            for segment in self._segments
            if self._audio_ranges_overlap(segment, event)
        ]
        if not overlapping_segments:
            return False

        overlapping_text = " ".join(
            self._clean(segment.text) for segment in overlapping_segments
        )
        normalized_existing = self._normalize(overlapping_text)
        normalized_new = self._normalize(text)
        if (
            not normalized_existing
            or normalized_existing == normalized_new
            or not normalized_new.startswith(normalized_existing)
        ):
            return False

        self._segments = [
            segment
            for segment in self._segments
            if not self._audio_ranges_overlap(segment, event)
        ]
        for segment in overlapping_segments:
            if segment.segment_id:
                self._segment_ids.discard(segment.segment_id)
        self._segments.append(event)
        if event.segment_id:
            self._segment_ids.add(event.segment_id)
        return True

    def tentative_text(self, event: SttTentativeEndpoint | None = None) -> str:
        assembled = self.current_text()
        if assembled:
            return assembled
        if event is None:
            return ""
        return self._clean(event.text)

    def flush(
        self,
        event: SttTentativeEndpoint | SttUtteranceEnded | None = None,
    ) -> AssembledTranscript | None:
        text = self.tentative_text(event if isinstance(event, SttTentativeEndpoint) else None)
        if not text and isinstance(event, SttUtteranceEnded):
            text = self._clean(event.text)
        if not text:
            self.reset()
            return None

        transcript = AssembledTranscript(
            text=text,
            segment_count=len(self._segments),
            confidence=self._average_confidence(),
            duration_ms=self._total_duration_ms(),
        )
        self.reset()
        return transcript

    def current_text(self) -> str:
        return " ".join(self._clean(segment.text) for segment in self._segments).strip()

    def reset(self) -> None:
        self._segments.clear()
        self._segment_ids.clear()

    def _is_same_audio_duplicate(self, event: SttFinalSegment, text: str) -> bool:
        normalized_text = self._normalize(text)
        return any(
            self._normalize(segment.text) == normalized_text
            and self._audio_ranges_overlap(segment, event)
            for segment in self._segments
        )

    def _is_suffix_duplicate(self, event: SttFinalSegment, text: str) -> bool:
        current = self.current_text()
        if not current:
            return False
        normalized_current = self._normalize(current)
        normalized_text = self._normalize(text)
        return normalized_current.endswith(normalized_text) and any(
            self._audio_ranges_overlap(segment, event) for segment in self._segments
        )

    def _audio_ranges_overlap(
        self,
        first: SttFinalSegment,
        second: SttFinalSegment,
    ) -> bool:
        first_start = first.timestamps.audio_offset_ms
        second_start = second.timestamps.audio_offset_ms
        if first_start is None or second_start is None:
            return False

        first_end = self._segment_end_ms(first)
        second_end = self._segment_end_ms(second)
        if first_end is None or second_end is None:
            return first_start == second_start

        return first_start < second_end and second_start < first_end

    def _segment_end_ms(self, segment: SttFinalSegment) -> int | None:
        if segment.timestamps.audio_offset_ms is None or segment.duration_ms is None:
            return None
        return segment.timestamps.audio_offset_ms + segment.duration_ms

    def _average_confidence(self) -> float | None:
        confidences = [
            segment.confidence
            for segment in self._segments
            if segment.confidence is not None
        ]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def _total_duration_ms(self) -> int | None:
        durations = [
            segment.duration_ms
            for segment in self._segments
            if segment.duration_ms is not None
        ]
        if not durations:
            return None
        return sum(durations)

    def _clean(self, text: str) -> str:
        return " ".join((text or "").split())

    def _normalize(self, text: str) -> str:
        return self._clean(text).lower()
