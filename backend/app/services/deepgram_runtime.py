"""Deepgram STT/TTS + OpenAI text orchestration runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
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

from app.config import get_settings
from app.models.call import Call
from app.services.observability import append_latency_marker, summarize_text_model_usage
from app.services.pricing import (
    _safe_float,
    estimate_deepgram_stt_cost,
    estimate_tts_cost,
    merge_cost_breakdown,
)
from app.services.tts_providers import get_tts_provider

from app.services.realtime_bridge import ConversationState, RealtimeBridge

settings = get_settings()
logger = logging.getLogger(__name__)


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

        def audio_frame_settings() -> tuple[int, float]:
            if provider == "exotel":
                # 20 ms of 8 kHz signed 16-bit mono PCM.
                return 320, 0.020
            # 20 ms of 8 kHz mu-law.
            return 160, 0.020

        async def reset_primary_tts_stream() -> None:
            reset_stream = getattr(self._tts_provider, "reset_stream", None)
            if reset_stream:
                await reset_stream()

        async def send_audio_payload(payload: str) -> bool:
            if websocket.application_state != WebSocketState.CONNECTED:
                log_debug(
                    f"[{tts_run_id}] Websocket is {websocket.application_state.name}; stopping TTS send"
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
            except Exception as e:
                log_debug(f"[{tts_run_id}] Error sending to websocket: {e}")
                return False

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
                    chunk_size, sleep_time = audio_frame_settings()

                    # Buffer to accumulate small chunks before sending
                    buffer = bytearray()

                    async for audio_chunk in self._tts_provider.synthesize_stream(
                        text=text,
                        telephony_provider=provider,
                    ):
                        if send_failed:
                            break
                        if not audio_chunk:
                            continue

                        # Add to buffer
                        buffer.extend(audio_chunk)

                        # Send buffered data in appropriate chunk sizes
                        while len(buffer) >= chunk_size:
                            chunk_to_send = bytes(buffer[:chunk_size])
                            buffer = buffer[chunk_size:]

                            payload = base64.b64encode(chunk_to_send).decode("ascii")

                            if call_id and audio_chunks_sent == 0:
                                await record_tts_cost(self._tts_provider.provider_name)
                                await self._mark_first_assistant_audio(call_id)
                            if audio_chunks_sent == 0:
                                self._assistant_audio_active = True
                                log_debug(f"[{tts_run_id}] First audio chunk sent (streaming)")

                            if not await send_audio_payload(payload):
                                send_failed = True
                                break
                            audio_chunks_sent += 1
                            await asyncio.sleep(sleep_time)

                    # Send remaining buffer
                    if buffer and not send_failed:
                        payload = base64.b64encode(bytes(buffer)).decode("ascii")
                        if call_id and audio_chunks_sent == 0:
                            await record_tts_cost(self._tts_provider.provider_name)
                            await self._mark_first_assistant_audio(call_id)
                        if audio_chunks_sent == 0:
                            self._assistant_audio_active = True
                        if await send_audio_payload(payload):
                            audio_chunks_sent += 1
                        else:
                            send_failed = True

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
                    chunk_size, sleep_time = audio_frame_settings()

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

                        if not await send_audio_payload(payload):
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
                        chunk_size, sleep_time = audio_frame_settings()

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

                            if not await send_audio_payload(payload):
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
            self._speak_text(
                websocket=websocket,
                provider=provider,
                stream_id=stream_id,
                text=text,
                call_id=call_id,
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

        encoding = "linear16" if provider == "exotel" else "mulaw"
        stt_url = (
            f"wss://api.deepgram.com/v1/listen?model={settings.DEEPGRAM_STT_MODEL}"
            f"&encoding={encoding}&sample_rate=8000&interim_results=true"
            "&vad_events=true&endpointing=300&utterance_end_ms=1000&punctuate=true&smart_format=true"
        )
        stt_headers = {"Authorization": f"Token {self.deepgram_api_key}"}

        log_debug("Connecting to Deepgram STT...")
        try:
            async with websockets.connect(stt_url, additional_headers=stt_headers) as stt_ws:
                log_debug("Deepgram STT connected")

                async def receive_stt_events() -> None:
                    nonlocal finalized_segments

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
                            await self._close_call_with_message(
                                call_id=call_id,
                                provider_call_id=provider_call_id,
                                message="Understood. Thank you for your time today. Goodbye.",
                            )
                            stop_event.set()
                            return
                        if state.off_topic_count >= 2:
                            await self._close_call_with_message(
                                call_id=call_id,
                                provider_call_id=provider_call_id,
                                message="It sounds like now is not the right time for this screening. Thank you for your time. Goodbye.",
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

                        await self._start_tts_task(
                            websocket=websocket,
                            provider=provider,
                            stream_id=stream_id or "",
                            text=response_text,
                            call_id=call_id,
                        )

                        if state_changed and self._should_end_call(response_text) and provider_call_id:
                            await asyncio.to_thread(self.telephony.end_call, provider_call_id)
                            stop_event.set()

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
                                    await process_user_utterance(utterance)
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
                            await process_user_utterance(utterance)
                            if stop_event.is_set():
                                return

                    finally:
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
