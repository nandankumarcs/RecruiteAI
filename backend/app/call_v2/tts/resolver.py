"""Resolve agent spoken text to cache, live TTS, or fallback TTS audio."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Literal

from app.call_v2.trace import monotonic_ms as _mono_ms

logger = logging.getLogger(__name__)

from app.call_v2.audio.formats import frame_size_bytes
from app.call_v2.audio.pacing import iter_audio_frames
from app.call_v2.events import (
    AudioFormat,
    AudioSourceSelected,
    CallIdentity,
    SendAudioFrame,
    TimestampMetadata,
)
from app.call_v2.ids import GenerationIdManager
from app.call_v2.tts.base import TtsAudio, TtsEngine, TtsRequest
from app.call_v2.tts.cache import (
    InMemoryAudioCache,
    build_audio_cache_key,
    text_fingerprint,
)
from app.call_v2.tts.eligibility import CachePolicy, decide_cache


def _frame_size(audio_format: AudioFormat, frame_duration_ms: int) -> int:
    return frame_size_bytes(audio_format, frame_duration_ms)


@dataclass(frozen=True, slots=True)
class AudioPlaybackPlan:
    source_event: AudioSourceSelected
    audio: TtsAudio
    frames: list[SendAudioFrame]


@dataclass(slots=True)
class AudioSourceResolver:
    cache: InMemoryAudioCache
    primary_tts: TtsEngine
    fallback_tts: TtsEngine | None = None
    frame_duration_ms: int = 20

    async def resolve(
        self,
        *,
        generation_id: int,
        spoken_text: str,
        identity: CallIdentity,
        output_format: AudioFormat,
        telephony_provider: str,
        cache_policy: CachePolicy,
        generation_ids: GenerationIdManager,
        now_ms: int,
    ) -> AudioPlaybackPlan:
        if not generation_ids.can_speak(generation_id):
            raise ValueError(f"generation {generation_id} is not confirmed to speak")

        decision = decide_cache(cache_policy)
        cache_key = build_audio_cache_key(
            text=spoken_text,
            category=decision.category,
            tts_provider=self.primary_tts.provider,
            tts_model=self.primary_tts.model,
            voice=self.primary_tts.voice,
            language=self.primary_tts.language,
            speaking_style=self.primary_tts.speaking_style,
            audio_format=output_format,
            telephony_provider=telephony_provider,
            variant_id=cache_policy.variant_id,
        )

        if decision.lookup_allowed:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "tts.cache_hit gen=%d provider=%s category=%s",
                    generation_id,
                    self.primary_tts.provider,
                    decision.category,
                )
                audio = TtsAudio(
                    payload=cached.payload,
                    audio_format=cached.audio_format,
                    provider=self.primary_tts.provider,
                    model=self.primary_tts.model,
                    voice=self.primary_tts.voice,
                    language=self.primary_tts.language,
                    speaking_style=self.primary_tts.speaking_style,
                )
                return self._plan(
                    generation_id=generation_id,
                    source="cache",
                    cache_key=cache_key.stable_key(),
                    cache_category=decision.category,
                    decision_reason=decision.reason,
                    spoken_text=spoken_text,
                    identity=identity,
                    audio=audio,
                    now_ms=now_ms,
                )

        tts_start_ms = _mono_ms()
        logger.info(
            "tts.start gen=%d provider=%s model=%s voice=%s text_len=%d",
            generation_id,
            self.primary_tts.provider,
            self.primary_tts.model,
            self.primary_tts.voice,
            len(spoken_text),
        )
        try:
            audio = await self.primary_tts.synthesize(
                self._request(
                    generation_id=generation_id,
                    spoken_text=spoken_text,
                    output_format=output_format,
                    engine=self.primary_tts,
                )
            )
            source = "live_tts"
            logger.info(
                "tts.complete gen=%d provider=%s latency_ms=%d bytes=%d",
                generation_id,
                self.primary_tts.provider,
                _mono_ms() - tts_start_ms,
                len(audio.payload),
            )
        except Exception as exc:
            logger.warning(
                "tts.primary_failed gen=%d provider=%s error=%s",
                generation_id,
                self.primary_tts.provider,
                exc,
            )
            if self.fallback_tts is None:
                raise
            fallback_start_ms = _mono_ms()
            audio = await self.fallback_tts.synthesize(
                self._request(
                    generation_id=generation_id,
                    spoken_text=spoken_text,
                    output_format=output_format,
                    engine=self.fallback_tts,
                )
            )
            source = "fallback_tts"
            logger.info(
                "tts.fallback_complete gen=%d provider=%s latency_ms=%d bytes=%d",
                generation_id,
                self.fallback_tts.provider,
                _mono_ms() - fallback_start_ms,
                len(audio.payload),
            )

        if decision.persistent_store_allowed and source == "live_tts":
            self.cache.put(
                cache_key,
                payload=audio.payload,
                audio_format=audio.audio_format,
            )

        return self._plan(
            generation_id=generation_id,
            source=source,
            cache_key=cache_key.stable_key() if decision.lookup_allowed else None,
            cache_category=decision.category,
            decision_reason=decision.reason,
            spoken_text=spoken_text,
            identity=identity,
            audio=audio,
            now_ms=now_ms,
        )

    async def resolve_stream(
        self,
        *,
        generation_id: int,
        spoken_text: str,
        identity: CallIdentity,
        output_format: AudioFormat,
        telephony_provider: str,
        cache_policy: CachePolicy,
        generation_ids: GenerationIdManager,
        now_ms: int,
    ) -> AsyncGenerator[list[SendAudioFrame], None]:
        """Yield SendAudioFrame batches as Sarvam HTTP chunks arrive.

        Falls back to the batch resolve() path for:
          - Cache hits (instant, no API call).
          - Engines that don't support synthesize_chunked().
        In both fallback cases all frames arrive in a single yield so the
        caller's code is the same regardless.
        """
        if not generation_ids.can_speak(generation_id):
            raise ValueError(f"generation {generation_id} is not confirmed to speak")

        decision = decide_cache(cache_policy)
        cache_key = build_audio_cache_key(
            text=spoken_text,
            category=decision.category,
            tts_provider=self.primary_tts.provider,
            tts_model=self.primary_tts.model,
            voice=self.primary_tts.voice,
            language=self.primary_tts.language,
            speaking_style=self.primary_tts.speaking_style,
            audio_format=output_format,
            telephony_provider=telephony_provider,
            variant_id=cache_policy.variant_id,
        )

        # ── Cache hit: yield all frames at once, no API call ─────────────────
        if decision.lookup_allowed:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.info(
                    "tts.cache_hit gen=%d provider=%s category=%s",
                    generation_id, self.primary_tts.provider, decision.category,
                )
                frames = list(self._frames(
                    generation_id=generation_id,
                    payload=cached.payload,
                    audio_format=cached.audio_format,
                    identity=identity,
                ))
                yield frames
                return

        # ── Engine supports chunk streaming: yield frames as chunks arrive ────
        chunked_fn = getattr(self.primary_tts, "synthesize_chunked", None)
        if callable(chunked_fn):
            request = self._request(
                generation_id=generation_id,
                spoken_text=spoken_text,
                output_format=output_format,
                engine=self.primary_tts,
            )
            frame_size = _frame_size(output_format, self.frame_duration_ms)
            buf = bytearray()
            accumulated = bytearray()
            t0 = _mono_ms()
            first_chunk = True

            async for raw_chunk in chunked_fn(request):
                buf.extend(raw_chunk)
                accumulated.extend(raw_chunk)
                if first_chunk:
                    logger.info(
                        "tts.stream_first_chunk gen=%d provider=%s ms_to_first=%d bytes=%d",
                        generation_id, self.primary_tts.provider,
                        _mono_ms() - t0, len(raw_chunk),
                    )
                    first_chunk = False
                # Yield complete frames from the buffer
                batch: list[SendAudioFrame] = []
                while len(buf) >= frame_size:
                    frame_bytes = bytes(buf[:frame_size])
                    buf = buf[frame_size:]
                    batch.append(SendAudioFrame(
                        type="telephony.send_audio_frame",
                        identity=identity,
                        payload=frame_bytes,
                        format=output_format,
                        generation_id=generation_id,
                        is_first_frame=False,   # updated below
                        is_final_frame=False,
                    ))
                if batch:
                    yield batch

            # Flush remainder
            if buf:
                yield [SendAudioFrame(
                    type="telephony.send_audio_frame",
                    identity=identity,
                    payload=bytes(buf),
                    format=output_format,
                    generation_id=generation_id,
                    is_first_frame=False,
                    is_final_frame=True,
                )]

            full_payload = bytes(accumulated)
            logger.info(
                "tts.stream_complete gen=%d provider=%s total_ms=%d bytes=%d",
                generation_id, self.primary_tts.provider,
                _mono_ms() - t0, len(full_payload),
            )
            if decision.persistent_store_allowed and full_payload:
                self.cache.put(
                    cache_key,
                    payload=full_payload,
                    audio_format=output_format,
                )
            return

        # ── Fallback: batch synthesize, yield all frames at once ─────────────
        plan = await self.resolve(
            generation_id=generation_id,
            spoken_text=spoken_text,
            identity=identity,
            output_format=output_format,
            telephony_provider=telephony_provider,
            cache_policy=cache_policy,
            generation_ids=generation_ids,
            now_ms=now_ms,
        )
        yield plan.frames

    def cancel(self, generation_id: int) -> None:
        self.primary_tts.cancel(generation_id)
        if self.fallback_tts is not None:
            self.fallback_tts.cancel(generation_id)

    def _request(
        self,
        *,
        generation_id: int,
        spoken_text: str,
        output_format: AudioFormat,
        engine: TtsEngine,
    ) -> TtsRequest:
        return TtsRequest(
            generation_id=generation_id,
            text=spoken_text,
            output_format=output_format,
            provider=engine.provider,
            model=engine.model,
            voice=engine.voice,
            language=engine.language,
            speaking_style=engine.speaking_style,
        )

    def _frames(
        self,
        *,
        generation_id: int,
        payload: bytes,
        audio_format: AudioFormat,
        identity: CallIdentity,
    ) -> list[SendAudioFrame]:
        raw_frames = list(iter_audio_frames(payload, audio_format=audio_format,
                                            frame_duration_ms=self.frame_duration_ms))
        return [
            SendAudioFrame(
                type="telephony.send_audio_frame",
                identity=identity,
                payload=f,
                format=audio_format,
                generation_id=generation_id,
                is_first_frame=(i == 0),
                is_final_frame=(i == len(raw_frames) - 1),
            )
            for i, f in enumerate(raw_frames)
        ]

    def _plan(
        self,
        *,
        generation_id: int,
        source: Literal["cache", "live_tts", "fallback_tts"],
        cache_key: str | None,
        cache_category: str,
        decision_reason: str,
        spoken_text: str,
        identity: CallIdentity,
        audio: TtsAudio,
        now_ms: int,
    ) -> AudioPlaybackPlan:
        audio_frames = list(
            iter_audio_frames(
                audio.payload,
                audio_format=audio.audio_format,
                frame_duration_ms=self.frame_duration_ms,
            )
        )
        if not audio_frames:
            raise ValueError("TTS audio payload must not be empty")
        return AudioPlaybackPlan(
            source_event=AudioSourceSelected(
                type="audio.source_selected",
                generation_id=generation_id,
                source=source,
                cache_key=cache_key,
                cache_category=cache_category,
                text_fingerprint=text_fingerprint(spoken_text),
                timestamps=TimestampMetadata(backend_received_at_ms=now_ms),
                decision_reason=decision_reason,
            ),
            audio=audio,
            frames=[
                SendAudioFrame(
                    type="telephony.send_audio_frame",
                    identity=identity,
                    payload=frame,
                    format=audio.audio_format,
                    generation_id=generation_id,
                    is_first_frame=index == 0,
                    is_final_frame=index == len(audio_frames) - 1,
                )
                for index, frame in enumerate(audio_frames)
            ],
        )
