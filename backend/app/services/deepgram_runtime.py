"""Deepgram STT/TTS + OpenAI text orchestration runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from time import perf_counter
import uuid

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from langsmith import traceable
from openai import AsyncOpenAI
import httpx
from deepgram import (
    DeepgramClient,
)

from app.debug_log import log_debug

# Providers that speak the L16 8kHz PCM wire format (vs Twilio's μ-law).
_L16_PROVIDERS = ("exotel", "browser")

from app.config import get_settings
from app.models.call import Call
from app.services.observability import (
    append_latency_marker,
    increment_metric,
    log_audio_source_event,
    merge_latency_metric,
    summarize_text_model_usage,
)
from app.services.prompt_audio_service import get_prompt_audio_service
from app.services.pricing import (
    _safe_float,
    estimate_deepgram_stt_cost,
    estimate_tts_cost,
    merge_cost_breakdown,
)
from app.services.runtime_selection_layer import RuntimeSelectionLayer
from app.services.tts_providers import get_tts_provider
from app.services.filler_queue_manager import FillerQueueManager

from app.services.realtime_bridge import ConversationState, RealtimeBridge

settings = get_settings()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deepgram nova-3 Keyterm Prompting
# ---------------------------------------------------------------------------
# These universal terms are always passed regardless of call context.
_BASE_KEYTERMS: tuple[str, ...] = (
    # Common tech stack mentioned in Indian AI/ML engineering interviews
    "FastAPI", "LangChain", "LangGraph", "ChromaDB", "FAISS", "RAG",
    "PyTorch", "TensorFlow", "Scikit-learn", "Hugging Face",
    "Docker", "Kubernetes", "PostgreSQL", "Redis", "Celery",
    "GPT", "LLM", "embedding", "vector database", "fine-tuning",
    "retrieval augmented generation", "multi-agent", "microservices",
    # Recruiting context
    "RecruiteAI", "Crownstack",
)

def _build_deepgram_keyterms(
    *,
    resume,
    job,
    questions: list | None = None,
    max_terms: int = 50,
) -> list[str]:
    """Build a deduplicated keyterm list from resume skills + job context.

    Nova-3 keyterm prompting boosts recognition of domain-specific vocabulary.
    Candidate names + tech stack from their own resume are the highest-value
    terms — Deepgram often mispronounces/misrecognises Indian names and
    niche framework names without hints.
    """
    seen: set[str] = set()
    result: list[str] = []

    def add(term: str) -> None:
        cleaned = term.strip()
        if not cleaned or len(result) >= max_terms:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        result.append(cleaned)

    # 1. Candidate first name — highest priority (Indian names often misrecognised)
    if resume and resume.candidate_name:
        first = resume.candidate_name.strip().split()[0]
        if len(first) > 2:
            add(first)

    # 2. Resume skills (what the candidate will actually say)
    if resume and resume.parsed_data:
        raw_skills = resume.parsed_data.get("skills", [])
        for s in raw_skills:
            name = s if isinstance(s, str) else (s.get("name") if isinstance(s, dict) else "")
            if name:
                add(name)

    # 3. Job title keywords
    if job and job.title:
        for word in job.title.split():
            if len(word) > 3:
                add(word)

    # 4. Base universal tech terms (fill remaining budget)
    for term in _BASE_KEYTERMS:
        add(term)

    return result


class DeepgramOpenAIPipelineRuntime(RealtimeBridge):
    """Voice runtime that uses Deepgram for STT/TTS and OpenAI for turn reasoning."""

    def __init__(self):
        super().__init__()
        self.deepgram_api_key = settings.DEEPGRAM_API_KEY
        self.openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.text_model = settings.OPENAI_TEXT_MODEL or settings.OPENAI_MODEL
        self._current_tts_task: asyncio.Task | None = None
        self._assistant_audio_active = False
        self._pending_barge_in = False
        self._tts_provider = get_tts_provider()
        self._tts_fallback_provider = None
        # Initialize fallback if using Sarvam
        if settings.TTS_PROVIDER.lower() == "sarvam":
            from app.services.tts_providers import DeepgramTTSProvider
            self._tts_fallback_provider = DeepgramTTSProvider()
        self._storage = get_prompt_audio_service().storage
        self._prompt_audio = get_prompt_audio_service()
        self._filler_queue = FillerQueueManager(self._prompt_audio)
        self.runtime_selection = RuntimeSelectionLayer(self._prompt_audio, self._filler_queue)
        self._last_filler_played_at: datetime | None = None
        self._last_filler_key: str | None = None

    async def _load_call_transcript(self, call_id: uuid.UUID) -> str:
        async with self._session_factory()() as session:
            call = await session.get(Call, call_id)
            return call.transcript or "" if call else ""

    def _session_factory(self):
        from app.database import async_session_factory

        return async_session_factory

    async def _update_call_costs(
        self,
        *,
        call_id: uuid.UUID,
        llm_cost_usd: float | None = None,
        stt_cost_usd: float | None = None,
        tts_cost_usd: float | None = None,
        usage: dict | None = None,
    ) -> None:
        async with self._session_factory()() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            
            # Accumulate instead of overwrite
            existing_costs = (call.cost_breakdown or {}).get("costs") or {}
            
            new_llm = _safe_float(existing_costs.get("llm_usd")) + _safe_float(llm_cost_usd) if llm_cost_usd is not None else None
            new_stt = _safe_float(existing_costs.get("stt_usd")) + _safe_float(stt_cost_usd) if stt_cost_usd is not None else None
            new_tts = _safe_float(existing_costs.get("tts_usd")) + _safe_float(tts_cost_usd) if tts_cost_usd is not None else None

            call.cost_breakdown = merge_cost_breakdown(
                call.cost_breakdown,
                provider=call.provider or "unknown",
                llm_cost_usd=new_llm,
                stt_cost_usd=new_stt,
                tts_cost_usd=new_tts,
                usage=usage, # We might want to merge usage too, but for now we'll overwrite it
            )
            await session.commit()


    async def _mark_first_assistant_audio(self, call_id: uuid.UUID) -> None:
        async with self._session_factory()() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            if (call.latency_metrics or {}).get("first_assistant_audio_at"):
                return
            call.latency_metrics = append_latency_marker(
                call.latency_metrics, key="first_assistant_audio_at"
            )
            await session.commit()

    async def _mark_first_user_transcript(self, call_id: uuid.UUID) -> None:
        async with self._session_factory()() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            if (call.latency_metrics or {}).get("first_user_transcript_at"):
                return
            call.latency_metrics = append_latency_marker(
                call.latency_metrics, key="first_user_transcript_at"
            )
            await session.commit()

    @staticmethod
    def _audio_frame_settings(provider: str) -> tuple[int, float]:
        if provider in _L16_PROVIDERS:
            return 320, 0.020
        return 160, 0.020

    async def _send_audio_payload(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        payload: str,
        tts_run_id: str,
    ) -> bool:
        if websocket.application_state != WebSocketState.CONNECTED:
            log_debug(
                f"[{tts_run_id}] Websocket is {websocket.application_state.name}; stopping audio send"
            )
            return False
        try:
            event_payload = self._build_audio_event(
                provider=provider,
                stream_id=stream_id,
                payload=payload,
            )
            await websocket.send_json(event_payload)
            return True
        except Exception as exc:
            log_debug(f"[{tts_run_id}] Error sending to websocket: {exc}")
            return False

    async def _record_audio_turn_metrics(
        self,
        *,
        call_id: uuid.UUID,
        audio_source: str,
        main_prompt_ready_after_ms: int | None = None,
    ) -> None:
        async with self._session_factory()() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            metrics = call.latency_metrics or {}
            if audio_source == "prebuilt_asset":
                metrics = increment_metric(metrics, key="prebuilt_turn_count")
            elif audio_source == "filler_asset":
                metrics = increment_metric(metrics, key="filler_turn_count")
            elif audio_source == "live_tts":
                metrics = increment_metric(metrics, key="live_tts_turn_count")
            elif audio_source == "live_tts_fallback":
                metrics = increment_metric(metrics, key="live_tts_fallback_count")
            if main_prompt_ready_after_ms is not None:
                metrics = merge_latency_metric(
                    metrics,
                    key="last_main_prompt_ready_after_ms",
                    value=main_prompt_ready_after_ms,
                )
            call.latency_metrics = metrics
            await session.commit()

    async def _play_audio_bytes(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        audio_bytes: bytes,
        call_id: uuid.UUID | None,
        tts_run_id: str,
    ) -> None:
        chunk_size, sleep_time = self._audio_frame_settings(provider)
        audio_chunks_sent = 0
        for offset in range(0, len(audio_bytes), chunk_size):
            chunk = audio_bytes[offset : offset + chunk_size]
            if not chunk:
                continue
            payload = base64.b64encode(chunk).decode("ascii")
            if call_id and audio_chunks_sent == 0:
                await self._mark_first_assistant_audio(call_id)
            if audio_chunks_sent == 0:
                self._assistant_audio_active = True
                log_debug(f"[{tts_run_id}] First cached audio chunk sent")
            if not await self._send_audio_payload(
                websocket=websocket,
                provider=provider,
                stream_id=stream_id,
                payload=payload,
                tts_run_id=tts_run_id,
            ):
                break
            audio_chunks_sent += 1
            await asyncio.sleep(sleep_time)
        self._assistant_audio_active = False
        self._pending_barge_in = False

    async def _play_cached_audio(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        asset,
        call_id: uuid.UUID | None,
    ) -> None:
        tts_run_id = str(uuid.uuid4())[:8]
        audio_bytes = await self._storage.get_file_content(asset.file_path)
        await self._play_audio_bytes(
            websocket=websocket,
            provider=provider,
            stream_id=stream_id,
            audio_bytes=audio_bytes,
            call_id=call_id,
            tts_run_id=tts_run_id,
        )

    async def _play_assistant_turn(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        text: str,
        call_id: uuid.UUID,
        state: ConversationState,
        job_id: uuid.UUID | None,
        questions: list,
    ) -> None:
        lookup_started = perf_counter()
        selection = await self.runtime_selection.select_audio_source(
            assistant_text=text,
            conversation_state=state,
            job_id=job_id,
            questions=questions,
        )
        asset_lookup_ms = int((perf_counter() - lookup_started) * 1000)
        main_prompt_ready = selection.source_type == "prebuilt_asset" and selection.asset is not None
        estimated_latency_ms = 0 if main_prompt_ready else 800

        should_play_filler, filler_key = await self._filler_queue.should_play_filler(
            estimated_latency_ms=estimated_latency_ms,
            last_filler_played_at=self._last_filler_played_at,
            main_prompt_ready=main_prompt_ready,
            last_filler_key=self._last_filler_key,
        )
        filler_played = False
        if should_play_filler and filler_key:
            filler_asset = await self._filler_queue.get_filler_asset(filler_key)
            if filler_asset is not None:
                try:
                    await self._play_cached_audio(
                        websocket=websocket,
                        provider=provider,
                        stream_id=stream_id,
                        asset=filler_asset,
                        call_id=call_id,
                    )
                    filler_played = True
                    self._last_filler_played_at = datetime.now(timezone.utc)
                    self._last_filler_key = filler_key
                    await self._record_audio_turn_metrics(
                        call_id=call_id,
                        audio_source="filler_asset",
                    )
                except Exception as exc:
                    log_audio_source_event(
                        call_id=str(call_id),
                        audio_source="filler_asset",
                        template_key=filler_key,
                        asset_id=str(filler_asset.id),
                        asset_lookup_ms=asset_lookup_ms,
                        filler_played=False,
                        filler_key=filler_key,
                        main_prompt_ready_after_ms=estimated_latency_ms,
                        error=str(exc),
                    )

        await self._record_audio_turn_metrics(
            call_id=call_id,
            audio_source=selection.source_type,
            main_prompt_ready_after_ms=estimated_latency_ms,
        )
        log_audio_source_event(
            call_id=str(call_id),
            audio_source=selection.source_type,
            template_key=selection.template_key,
            asset_id=str(selection.asset.id) if selection.asset else None,
            asset_lookup_ms=asset_lookup_ms,
            filler_played=filler_played,
            filler_key=filler_key if filler_played else None,
            main_prompt_ready_after_ms=estimated_latency_ms,
        )

        if selection.source_type == "prebuilt_asset" and selection.asset is not None:
            try:
                await self._play_cached_audio(
                    websocket=websocket,
                    provider=provider,
                    stream_id=stream_id,
                    asset=selection.asset,
                    call_id=call_id,
                )
                return
            except Exception as exc:
                log_audio_source_event(
                    call_id=str(call_id),
                    audio_source="live_tts_fallback",
                    template_key=selection.template_key,
                    asset_id=str(selection.asset.id),
                    asset_lookup_ms=asset_lookup_ms,
                    filler_played=filler_played,
                    filler_key=filler_key if filler_played else None,
                    main_prompt_ready_after_ms=estimated_latency_ms,
                    error=str(exc),
                )

        await self._speak_text(
            websocket=websocket,
            provider=provider,
            stream_id=stream_id,
            text=selection.fallback_text or text,
            call_id=call_id,
        )

    async def _play_terminal_message_and_end_call(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        text: str,
        call_id: uuid.UUID,
        state: ConversationState,
        job_id: uuid.UUID | None,
        questions: list,
        provider_call_id: str | None,
    ) -> None:
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            await websocket.send_json(
                self._build_clear_audio_event(provider=provider, stream_id=stream_id)
            )
            try:
                await self._current_tts_task
            except asyncio.CancelledError:
                pass

        await self._play_assistant_turn(
            websocket=websocket,
            provider=provider,
            stream_id=stream_id,
            text=text,
            call_id=call_id,
            state=state,
            job_id=job_id,
            questions=questions,
        )
        await asyncio.sleep(0.2)
        if provider_call_id:
            await asyncio.to_thread(self.telephony.end_call, provider_call_id)

    @traceable(run_type="llm", name="voice_turn_generator")
    async def _generate_next_turn(
        self,
        *,
        call_id: uuid.UUID,
        resume,
        job,
        questions,
        state: ConversationState,
    ) -> str:
        transcript = await self._load_call_transcript(call_id)
        instructions = self._build_instructions(
            resume=resume,
            job=job,
            questions=questions,
            state=state,
        )
        completion = await self.openai_client.chat.completions.create(
            model=self.text_model,
            temperature=0.2,
            max_tokens=48,
            messages=[
                {"role": "system", "content": instructions},
                {
                    "role": "user",
                    "content": (
                        "Here is the conversation transcript so far.\n"
                        "Return only the next spoken recruiter turn.\n"
                        "Interpret the latest candidate turn from context; if it is a clarification or a request to repeat, answer briefly and restate the active question instead of ending the call.\n\n"
                        f"{transcript}"
                    ),
                },
            ],
        )
        content = self._clean_assistant_spoken_text(completion.choices[0].message.content)
        content = self._compress_assistant_spoken_text(content)
        usage = {
            "input_tokens": getattr(completion.usage, "prompt_tokens", 0),
            "output_tokens": getattr(completion.usage, "completion_tokens", 0),
            "total_tokens": getattr(completion.usage, "total_tokens", 0),
        }
        usage_summary = summarize_text_model_usage(
            agent_name="voice_pipeline_turn_generator",
            model=self.text_model,
            usage=usage,
            metadata={"call_id": str(call_id), "runtime": "deepgram_openai_pipeline"},
        )
        await self._update_call_costs(
            call_id=call_id,
            llm_cost_usd=usage_summary["estimated_cost_usd"],
            usage=usage_summary["usage"],
        )
        return content

    async def _speak_text(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        text: str,
        call_id: uuid.UUID | None,
    ) -> None:
        tts_run_id = str(uuid.uuid4())[:8]
        text = self._clean_assistant_spoken_text(text)
        if not text:
            return
        log_debug(f"[{tts_run_id}] Starting TTS for text: {text[:50]}... (stream_id={stream_id})")
        self._assistant_audio_active = False
        self._pending_barge_in = False
        tts_cost_recorded = False

        async def record_tts_cost(provider_name: str) -> None:
            nonlocal tts_cost_recorded
            if not call_id or tts_cost_recorded:
                return
            log_debug(f"[{tts_run_id}] Updating call costs for {provider_name} TTS...")
            await self._update_call_costs(
                call_id=call_id,
                tts_cost_usd=estimate_tts_cost(
                    provider=provider_name,
                    characters=len(text),
                ),
            )
            tts_cost_recorded = True

        async def reset_primary_tts_stream() -> None:
            reset_stream = getattr(self._tts_provider, "reset_stream", None)
            if reset_stream:
                await reset_stream()

        try:
            audio_chunks_sent = 0
            send_failed = False
            log_debug(
                f"[{tts_run_id}] Requesting TTS from {self._tts_provider.provider_name} "
                f"(streaming={self._tts_provider.supports_streaming})..."
            )

            # Use streaming if provider supports it
            use_streaming = getattr(self._tts_provider, "supports_streaming", False)

            try:
                if use_streaming:
                    # STREAMING MODE: Send audio chunks as they arrive
                    log_debug(f"[{tts_run_id}] Using streaming mode for progressive audio delivery")
                    chunk_size, sleep_time = self._audio_frame_settings(provider)
                    prebuffer_chunks = max(
                        1,
                        int(settings.PIPELINE_TTS_JITTER_BUFFER_MS / (sleep_time * 1000)),
                    )
                    prebuffer_bytes = chunk_size * prebuffer_chunks
                    log_debug(
                        f"[{tts_run_id}] TTS jitter buffer target: "
                        f"{settings.PIPELINE_TTS_JITTER_BUFFER_MS}ms ({prebuffer_bytes} bytes)"
                    )

                    # Producer keeps reading TTS while the consumer paces audio
                    # to the telephony websocket. This prevents playback from
                    # outrunning Sarvam chunk delivery and creating mid-turn gaps.
                    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
                    buffer = bytearray()
                    producer_error: BaseException | None = None

                    async def produce_audio() -> None:
                        nonlocal producer_error
                        try:
                            async for audio_chunk in self._tts_provider.synthesize_stream(
                                text=text,
                                telephony_provider=provider,
                            ):
                                if audio_chunk:
                                    await audio_queue.put(audio_chunk)
                        except asyncio.CancelledError:
                            raise
                        except BaseException as e:
                            producer_error = e
                        finally:
                            await audio_queue.put(None)

                    producer_task = asyncio.create_task(produce_audio())

                    try:
                        producer_done = False
                        while not send_failed:
                            target_bytes = (
                                prebuffer_bytes if audio_chunks_sent == 0 else chunk_size
                            )
                            while len(buffer) < target_bytes and not producer_done:
                                audio_chunk = await audio_queue.get()
                                if audio_chunk is None:
                                    producer_done = True
                                    break
                                buffer.extend(audio_chunk)

                            if producer_error and not buffer:
                                raise producer_error
                            if len(buffer) < chunk_size:
                                if producer_done:
                                    break
                                continue

                            chunk_to_send = bytes(buffer[:chunk_size])
                            del buffer[:chunk_size]
                            payload = base64.b64encode(chunk_to_send).decode("ascii")

                            if call_id and audio_chunks_sent == 0:
                                await record_tts_cost(self._tts_provider.provider_name)
                                await self._mark_first_assistant_audio(call_id)
                            if audio_chunks_sent == 0:
                                self._assistant_audio_active = True
                                log_debug(f"[{tts_run_id}] First audio chunk sent (streaming)")

                            if not await self._send_audio_payload(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id,
                                payload=payload,
                                tts_run_id=tts_run_id,
                            ):
                                send_failed = True
                                break
                            audio_chunks_sent += 1
                            await asyncio.sleep(sleep_time)

                        # Send remaining buffer when generation is complete.
                        while buffer and not send_failed:
                            chunk_to_send = bytes(buffer[:chunk_size])
                            del buffer[:chunk_size]
                            payload = base64.b64encode(chunk_to_send).decode("ascii")
                            if call_id and audio_chunks_sent == 0:
                                await record_tts_cost(self._tts_provider.provider_name)
                                await self._mark_first_assistant_audio(call_id)
                            if audio_chunks_sent == 0:
                                self._assistant_audio_active = True
                                log_debug(f"[{tts_run_id}] First audio chunk sent (streaming)")
                            if not await self._send_audio_payload(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id,
                                payload=payload,
                                tts_run_id=tts_run_id,
                            ):
                                send_failed = True
                                break
                            audio_chunks_sent += 1
                            if buffer:
                                await asyncio.sleep(sleep_time)
                    finally:
                        if not producer_task.done():
                            producer_task.cancel()
                            try:
                                await producer_task
                            except asyncio.CancelledError:
                                pass

                    log_debug(
                        f"[{tts_run_id}] Streaming TTS complete. Sent {audio_chunks_sent} chunks."
                    )
                    if send_failed:
                        await reset_primary_tts_stream()

                else:
                    # NON-STREAMING MODE: Wait for complete audio then send
                    log_debug(f"[{tts_run_id}] Using non-streaming mode (legacy)")
                    audio_bytes = await self._tts_provider.synthesize(
                        text=text,
                        telephony_provider=provider,
                    )
                    log_debug(
                        f"[{tts_run_id}] {self._tts_provider.provider_name} TTS success: {len(audio_bytes)} bytes"
                    )

                    if not audio_bytes:
                        log_debug(f"[{tts_run_id}] No audio bytes generated")
                        return

                    log_debug(f"[{tts_run_id}] Sending {len(audio_bytes)} audio bytes in chunks...")
                    chunk_size, sleep_time = self._audio_frame_settings(provider)

                    for i in range(0, len(audio_bytes), chunk_size):
                        chunk = audio_bytes[i : i + chunk_size]
                        if not chunk:
                            continue
                        payload = base64.b64encode(chunk).decode("ascii")

                        if call_id and audio_chunks_sent == 0:
                            await record_tts_cost(self._tts_provider.provider_name)
                            await self._mark_first_assistant_audio(call_id)
                        if audio_chunks_sent == 0:
                            self._assistant_audio_active = True

                        if not await self._send_audio_payload(
                            websocket=websocket,
                            provider=provider,
                            stream_id=stream_id,
                            payload=payload,
                            tts_run_id=tts_run_id,
                        ):
                            break
                        audio_chunks_sent += 1
                        await asyncio.sleep(sleep_time)

                    log_debug(f"[{tts_run_id}] TTS complete. Sent {audio_chunks_sent} chunks.")

            except Exception as e:
                log_debug(
                    f"[{tts_run_id}] {self._tts_provider.provider_name} TTS failed: {e}"
                )
                # Try fallback if available
                if self._tts_fallback_provider:
                    log_debug(
                        f"[{tts_run_id}] Falling back to {self._tts_fallback_provider.provider_name}..."
                    )
                    try:
                        audio_bytes = await self._tts_fallback_provider.synthesize(
                            text=text,
                            telephony_provider=provider,
                        )
                        log_debug(
                            f"[{tts_run_id}] Fallback TTS success: {len(audio_bytes)} bytes"
                        )

                        # Send fallback audio
                        chunk_size, sleep_time = self._audio_frame_settings(provider)

                        for i in range(0, len(audio_bytes), chunk_size):
                            chunk = audio_bytes[i : i + chunk_size]
                            if not chunk:
                                continue
                            payload = base64.b64encode(chunk).decode("ascii")

                            if call_id and audio_chunks_sent == 0:
                                await record_tts_cost(self._tts_fallback_provider.provider_name)
                                await self._mark_first_assistant_audio(call_id)
                            if audio_chunks_sent == 0:
                                self._assistant_audio_active = True

                            if not await self._send_audio_payload(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id,
                                payload=payload,
                                tts_run_id=tts_run_id,
                            ):
                                break
                            audio_chunks_sent += 1
                            await asyncio.sleep(sleep_time)

                    except Exception as fallback_error:
                        log_debug(f"[{tts_run_id}] Fallback TTS also failed: {fallback_error}")
                        raise
                else:
                    raise

            self._assistant_audio_active = False
            self._pending_barge_in = False

        except asyncio.CancelledError:
            log_debug(f"[{tts_run_id}] TTS cancelled")
            await reset_primary_tts_stream()
            self._assistant_audio_active = False
            self._pending_barge_in = False
            raise
        except Exception as e:
            log_debug(f"[{tts_run_id}] FATAL ERROR in _speak_text: {e}")
            self._assistant_audio_active = False
            self._pending_barge_in = False
            import traceback
            log_debug(traceback.format_exc())

    async def _start_tts_task(
        self,
        *,
        websocket: WebSocket,
        provider: str,
        stream_id: str,
        text: str,
        call_id: uuid.UUID,
        state: ConversationState,
        job_id: uuid.UUID | None,
        questions: list,
    ) -> None:
        if self._current_tts_task and not self._current_tts_task.done():
            self._current_tts_task.cancel()
            await websocket.send_json(
                self._build_clear_audio_event(provider=provider, stream_id=stream_id)
            )
            try:
                await self._current_tts_task
            except asyncio.CancelledError:
                pass

        self._current_tts_task = asyncio.create_task(
            self._play_assistant_turn(
                websocket=websocket,
                provider=provider,
                stream_id=stream_id,
                text=text,
                call_id=call_id,
                state=state,
                job_id=job_id,
                questions=questions,
            )
        )

    async def handle(self, websocket: WebSocket, resume_id: uuid.UUID, provider: str = "twilio") -> None:
        import sys
        sys.stderr.write(f"START handle: resume_id={resume_id} provider={provider}\n")
        sys.stderr.flush()
        if not self.api_key or not self.deepgram_api_key:
            log_debug("ERROR: Missing API keys")
            if websocket.application_state == WebSocketState.CONNECTING:
                await websocket.accept()
            await websocket.close(code=1011, reason="Voice runtime is not fully configured.")
            return

        try:
            resume, job, questions, call = await self._load_context(resume_id)
            log_debug(f"Context loaded: job_id={job.id} questions_count={len(questions)}")
        except Exception as e:
            log_debug(f"ERROR: _load_context failed: {e}")
            raise

        call_id = call.id if call else None
        state = ConversationState()

        try:
            if websocket.application_state == WebSocketState.CONNECTING:
                await websocket.accept()
                log_debug("Websocket accepted")
            else:
                log_debug(f"Websocket already in state: {websocket.application_state.name}")
        except Exception as e:
            log_debug(f"ERROR: websocket.accept failed: {e}")
            raise

        stream_id: str | None = None
        provider_call_id: str | None = call.provider_call_id if call else None
        stop_event = asyncio.Event()
        finalized_segments: list[str] = []

        encoding = "linear16" if provider in _L16_PROVIDERS else "mulaw"

        # Build nova-3 keyterms from resume skills + job context.
        # Up to 50 terms keeps us well under the 500-token limit.
        keyterms = _build_deepgram_keyterms(
            resume=resume,
            job=job,
            questions=questions,
        )
        keyterm_params = "".join(
            f"&keyterm={t.replace(' ', '%20')}" for t in keyterms
        )

        stt_url = (
            f"wss://api.deepgram.com/v1/listen?model={settings.DEEPGRAM_STT_MODEL}"
            f"&language={settings.DEEPGRAM_STT_LANGUAGE}"
            f"&encoding={encoding}&sample_rate=8000&interim_results=true"
            f"&vad_events=true&endpointing={settings.PIPELINE_STT_ENDPOINTING_MS}"
            f"&utterance_end_ms={settings.PIPELINE_STT_UTTERANCE_END_MS}"
            f"&punctuate=true&smart_format=true"
            f"{keyterm_params}"
        )
        stt_headers = {"Authorization": f"Token {self.deepgram_api_key}"}

        log_debug("Connecting to Deepgram STT...")
        try:
            async with websockets.connect(stt_url, additional_headers=stt_headers) as stt_ws:
                log_debug("Deepgram STT connected")

                async def receive_stt_events() -> None:
                    nonlocal finalized_segments
                    pending_fragment_text = ""
                    pending_fragment_task: asyncio.Task | None = None
                    pending_fragment_generation = 0

                    async def process_user_utterance(utterance: str) -> None:
                        nonlocal finalized_segments
                        if not call_id:
                            return

                        logger.info("User turn completed (Deepgram, call=%s): %s", call_id, utterance)
                        await self._append_message(
                            call_id,
                            "user",
                            utterance,
                            item_key=f"deepgram-user-{uuid.uuid4()}",
                        )
                        await self._mark_first_user_transcript(call_id)

                        analysis = await self._analyze_candidate_turn(
                            transcript=utterance,
                            state=state,
                        )

                        state_changed = False
                        if analysis.request_termination:
                            state.termination_requested = True
                            state_changed = True
                        elif analysis.grant_consent and not state.consent_granted:
                            state.consent_granted = True
                            state_changed = True
                        if analysis.off_topic_request:
                            state.off_topic_count += 1
                            state_changed = True

                        if state.termination_requested:
                            response_text = "Understood. Thank you for your time today. Goodbye."
                            logger.info("Assistant turn completed (Deepgram, call=%s): %s", call_id, response_text)
                            await self._append_message(
                                call_id,
                                "assistant",
                                response_text,
                                item_key=f"deepgram-assistant-{uuid.uuid4()}",
                            )
                            await self._play_terminal_message_and_end_call(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id or "",
                                text=response_text,
                                call_id=call_id,
                                state=state,
                                job_id=job.id if job else None,
                                questions=questions,
                                provider_call_id=provider_call_id,
                            )
                            stop_event.set()
                            return
                        if state.off_topic_count >= 2:
                            response_text = (
                                "It sounds like now is not the right time for this screening. "
                                "Thank you for your time. Goodbye."
                            )
                            logger.info("Assistant turn completed (Deepgram, call=%s): %s", call_id, response_text)
                            await self._append_message(
                                call_id,
                                "assistant",
                                response_text,
                                item_key=f"deepgram-assistant-{uuid.uuid4()}",
                            )
                            await self._play_terminal_message_and_end_call(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id or "",
                                text=response_text,
                                call_id=call_id,
                                state=state,
                                job_id=job.id if job else None,
                                questions=questions,
                                provider_call_id=provider_call_id,
                            )
                            stop_event.set()
                            return

                        response_text = await self._generate_next_turn(
                            call_id=call_id,
                            resume=resume,
                            job=job,
                            questions=questions,
                            state=state,
                        )
                        if not response_text:
                            return

                        if not state.consent_granted and self._is_consent_prompt(response_text):
                            state.consent_prompt_delivered = True

                        logger.info("Assistant turn completed (Deepgram, call=%s): %s", call_id, response_text)
                        await self._append_message(
                            call_id,
                            "assistant",
                            response_text,
                            item_key=f"deepgram-assistant-{uuid.uuid4()}",
                        )

                        should_end_after_playback = state_changed and self._should_end_call(response_text)
                        if should_end_after_playback:
                            await self._play_terminal_message_and_end_call(
                                websocket=websocket,
                                provider=provider,
                                stream_id=stream_id or "",
                                text=response_text,
                                call_id=call_id,
                                state=state,
                                job_id=job.id if job else None,
                                questions=questions,
                                provider_call_id=provider_call_id,
                            )
                            stop_event.set()
                            return

                        await self._start_tts_task(
                            websocket=websocket,
                            provider=provider,
                            stream_id=stream_id or "",
                            text=response_text,
                            call_id=call_id,
                            state=state,
                            job_id=job.id if job else None,
                            questions=questions,
                        )

                    async def flush_pending_fragment(expected_generation: int) -> None:
                        nonlocal pending_fragment_text, pending_fragment_task
                        await asyncio.sleep(settings.PIPELINE_USER_FRAGMENT_GRACE_MS / 1000)
                        if expected_generation != pending_fragment_generation:
                            return
                        utterance = pending_fragment_text.strip()
                        pending_fragment_text = ""
                        pending_fragment_task = None
                        if utterance:
                            await process_user_utterance(utterance)

                    async def queue_or_process_user_utterance(utterance: str) -> None:
                        nonlocal pending_fragment_generation, pending_fragment_task, pending_fragment_text
                        cleaned = utterance.strip()
                        if not cleaned:
                            return

                        if self._looks_like_incomplete_user_fragment(cleaned):
                            pending_fragment_text = " ".join(
                                segment
                                for segment in (pending_fragment_text, cleaned)
                                if segment
                            ).strip()
                            pending_fragment_generation += 1
                            if pending_fragment_task and not pending_fragment_task.done():
                                pending_fragment_task.cancel()
                            pending_fragment_task = asyncio.create_task(
                                flush_pending_fragment(pending_fragment_generation)
                            )
                            return

                        if pending_fragment_task and not pending_fragment_task.done():
                            pending_fragment_task.cancel()
                        if pending_fragment_text:
                            cleaned = f"{pending_fragment_text} {cleaned}".strip()
                            pending_fragment_text = ""
                        pending_fragment_task = None
                        await process_user_utterance(cleaned)

                    ai_interruption_count: int = 0  # Fix 4a: track AI interruptions

                    try:
                        async for raw in stt_ws:
                            if isinstance(raw, bytes):
                                continue
                            data = json.loads(raw)
                            # Handle VAD events for interruption
                            if data.get("type") == "SpeechStarted":
                                logger.info("SpeechStarted from Deepgram (call=%s)", call_id)
                                if self._assistant_audio_active:
                                    self._pending_barge_in = True
                                continue

                            if data.get("type") == "UtteranceEnd":
                                utterance = " ".join(finalized_segments).strip()
                                finalized_segments = []
                                if utterance:
                                    await queue_or_process_user_utterance(utterance)
                                continue

                            if data.get("type") != "Results":
                                continue

                            transcript = (
                                data.get("channel", {})
                                .get("alternatives", [{}])[0]
                                .get("transcript", "")
                                .strip()
                            )
                            if not transcript:
                                continue

                            if self._pending_barge_in and self._assistant_audio_active:
                                normalized = " ".join(transcript.split())
                                word_count = len(normalized.split())
                                if len(normalized) >= 8 or word_count >= 2:
                                    log_debug(
                                        f"Confirmed barge-in from transcript while assistant speaking: {normalized[:80]}"
                                    )
                                    if self._current_tts_task and not self._current_tts_task.done():
                                        self._current_tts_task.cancel()
                                        await websocket.send_json(
                                            self._build_clear_audio_event(
                                                provider=provider, stream_id=stream_id or ""
                                            )
                                        )
                                    self._pending_barge_in = False

                            if data.get("is_final"):
                                finalized_segments.append(transcript)
                            if not data.get("speech_final"):
                                continue

                            utterance = " ".join(finalized_segments).strip() or transcript
                            finalized_segments = []
                            self._pending_barge_in = False

                            # Fix 2: Duration-based turn gate.
                            # Deepgram includes start/duration on each Results event.
                            # If the candidate spoke for < PIPELINE_MIN_TURN_SECONDS AND
                            # produced < 4 words AND didn't end with terminal punctuation,
                            # treat as fragment regardless of the word-list check.
                            speech_duration = data.get("duration", 0.0)
                            words = len(utterance.split())
                            ends_with_punct = utterance.rstrip().endswith((".", "?", "!", "..."))
                            is_short_burst = (
                                speech_duration > 0
                                and speech_duration < settings.PIPELINE_MIN_TURN_SECONDS
                                and words < 4
                                and not ends_with_punct
                            )
                            if is_short_burst:
                                logger.debug(
                                    "Duration gate: %.2fs / %d words — treating as fragment (call=%s)",
                                    speech_duration, words, call_id,
                                )
                                # Fix 4a: count as a potential interruption
                                ai_interruption_count += 1
                                pending_fragment_text = " ".join(
                                    s for s in (pending_fragment_text, utterance) if s
                                ).strip()
                                pending_fragment_generation += 1
                                if pending_fragment_task and not pending_fragment_task.done():
                                    pending_fragment_task.cancel()
                                pending_fragment_task = asyncio.create_task(
                                    flush_pending_fragment(pending_fragment_generation)
                                )
                                if stop_event.is_set():
                                    return
                                continue

                            await queue_or_process_user_utterance(utterance)
                            if stop_event.is_set():
                                return

                    finally:
                        if pending_fragment_task and not pending_fragment_task.done():
                            pending_fragment_task.cancel()
                        log_debug("STT receiver task finished")

                stt_task = asyncio.create_task(receive_stt_events())
                try:
                    while not stop_event.is_set():
                        try:
                            payload = await websocket.receive_text()
                        except Exception as e:
                            log_debug(f"Websocket receive error: {e}")
                            break
                        
                        # Log the raw payload for debugging
                        print(f"RAW EXOTEL MESSAGE: {payload}", file=sys.stderr, flush=True)
                        log_debug(f"RAW EXOTEL MESSAGE: {payload}")

                        
                        data = json.loads(payload)
                        event = data.get("event")
                        
                        if event == "connected":
                            log_debug(f"Event CONNECTED received: call_id={call_id}")
                            continue

                        if event == "start":
                            log_debug(f"Event {event.upper()} received: call_id={call_id}")
                            stream_id = self._extract_stream_id(data)
                            provider_call_id = self._extract_provider_call_id(
                                provider=provider,
                                payload=data,
                            ) or provider_call_id

                            if not stream_id:
                                log_debug("Exotel start event did not include stream id; deferring opener.")
                                continue
                            
                            if call_id:
                                await self._update_call_started(call_id, provider, provider_call_id)
                                async with self._session_factory()() as session:
                                    call_record = await session.get(Call, call_id)
                                    if call_record is not None:
                                        call_record.latency_metrics = append_latency_marker(
                                            call_record.latency_metrics, key="stream_connected_at"
                                        )
                                        await session.commit()
                                
                                # Check if we already sent the opener to avoid double greeting
                                if not hasattr(state, "opener_sent"):
                                    opener = self._build_initial_consent_prompt(
                                        resume=resume,
                                        job=job,
                                    )
                                    log_debug(f"Opener generated: {opener[:50]}...")
                                    if opener:
                                        if self._is_consent_prompt(opener):
                                            state.consent_prompt_delivered = True
                                        await self._append_message(
                                            call_id,
                                            "assistant",
                                            opener,
                                            item_key=f"deepgram-assistant-opener-{uuid.uuid4()}",
                                        )
                                        await self._start_tts_task(
                                            websocket=websocket,
                                            provider=provider,
                                            stream_id=stream_id or "",
                                            text=opener,
                                            call_id=call_id,
                                            state=state,
                                            job_id=job.id if job else None,
                                            questions=questions,
                                        )
                                        state.opener_sent = True
                                else:
                                    log_debug("Opener already sent, skipping.")

                        elif event == "media":
                            audio_payload = (data.get("media") or {}).get("payload")
                            if audio_payload:
                                await stt_ws.send(base64.b64decode(audio_payload))
                                # Yield so assistant-side tasks (like TTS) can run even
                                # under sustained media load.
                                await asyncio.sleep(0)
                        elif event == "stop":
                            log_debug(f"Event STOP received for call_id={call_id}")
                            if self._current_tts_task and not self._current_tts_task.done():
                                self._current_tts_task.cancel()
                                try:
                                    await self._current_tts_task
                                except asyncio.CancelledError:
                                    pass
                            break
                        elif event == "dtmf":
                            log_debug(f"DTMF received: {data.get('dtmf', {}).get('digit')}")
                        else:
                            log_debug(f"Other event received: {event}")

                finally:
                    stt_task.cancel()

                if call_id:
                    async with self._session_factory()() as session:
                        call_record = await session.get(Call, call_id)
                        if call_record and call_record.duration_seconds:
                            call_record.cost_breakdown = merge_cost_breakdown(
                                call_record.cost_breakdown,
                                provider=call_record.provider or provider,
                                stt_cost_usd=estimate_deepgram_stt_cost(
                                    duration_seconds=call_record.duration_seconds
                                ),
                            )
                            await session.commit()
                    # Fix 4a: persist interruption count for fair evaluation
                    if call_id and ai_interruption_count > 0:
                        async with self._session_factory()() as session:
                            call_record = await session.get(Call, call_id)
                            if call_record is not None:
                                metrics = dict(call_record.latency_metrics or {})
                                metrics["ai_interruption_count"] = ai_interruption_count
                                call_record.latency_metrics = metrics
                                await session.commit()
                        logger.info(
                            "Persisted ai_interruption_count=%d (call=%s)",
                            ai_interruption_count, call_id,
                        )
                    await self._update_call_finished(call_id)
                try:
                    await websocket.close()
                except RuntimeError:
                    log_debug("Websocket already closed before runtime cleanup")
                log_debug("Handle loop cleanup DONE")
        except Exception as e:
            log_debug(f"FATAL ERROR outside handle loop: {e}")
            import traceback
            log_debug(traceback.format_exc())
            raise
