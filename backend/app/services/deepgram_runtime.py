"""Deepgram STT/TTS + OpenAI text orchestration runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid

import websockets
from fastapi import WebSocket
from openai import AsyncOpenAI

from app.config import get_settings
from app.models.call import Call
from app.services.observability import append_latency_marker, summarize_text_model_usage
from app.services.pricing import (
    estimate_deepgram_stt_cost,
    estimate_deepgram_tts_cost,
    merge_cost_breakdown,
)
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

    async def _load_call_transcript(self, call_id: uuid.UUID) -> str:
        async with self._session_factory() as session:
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
        async with self._session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            call.cost_breakdown = merge_cost_breakdown(
                call.cost_breakdown,
                provider=call.provider or "unknown",
                llm_cost_usd=llm_cost_usd,
                stt_cost_usd=stt_cost_usd,
                tts_cost_usd=tts_cost_usd,
                usage=usage,
            )
            await session.commit()

    async def _mark_first_assistant_audio(self, call_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
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
        async with self._session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            if (call.latency_metrics or {}).get("first_user_transcript_at"):
                return
            call.latency_metrics = append_latency_marker(
                call.latency_metrics, key="first_user_transcript_at"
            )
            await session.commit()

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
                        "Return only the next spoken recruiter turn.\n\n"
                        f"{transcript}"
                    ),
                },
            ],
        )
        content = (completion.choices[0].message.content or "").strip()
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
        if not self.deepgram_api_key:
            return

        tts_url = (
            f"wss://api.deepgram.com/v1/speak?model={settings.DEEPGRAM_TTS_MODEL}"
            "&encoding=mulaw&sample_rate=8000"
        )
        headers = {"Authorization": f"Token {self.deepgram_api_key}"}
        async with websockets.connect(tts_url, additional_headers=headers) as tts_ws:
            await tts_ws.send(json.dumps({"type": "SpeakV1Text", "text": text}))
            await tts_ws.send(json.dumps({"type": "Flush"}))
            if call_id:
                await self._update_call_costs(
                    call_id=call_id,
                    tts_cost_usd=estimate_deepgram_tts_cost(characters=len(text)),
                )

            while True:
                message = await tts_ws.recv()
                if isinstance(message, bytes):
                    payload = base64.b64encode(message).decode("ascii")
                    if call_id:
                        await self._mark_first_assistant_audio(call_id)
                    await websocket.send_json(
                        self._build_audio_event(
                            provider=provider,
                            stream_id=stream_id,
                            payload=payload,
                        )
                    )
                    continue

                data = json.loads(message)
                event_type = data.get("type")
                if event_type in {"SpeakV1Audio", "Audio"}:
                    payload = data.get("audio")
                    if payload:
                        if call_id:
                            await self._mark_first_assistant_audio(call_id)
                        await websocket.send_json(
                            self._build_audio_event(
                                provider=provider,
                                stream_id=stream_id,
                                payload=payload,
                            )
                        )
                elif event_type in {"SpeakV1Flushed", "Flushed"}:
                    break

    async def handle(self, websocket: WebSocket, resume_id: uuid.UUID, provider: str = "twilio") -> None:
        if not self.api_key or not self.deepgram_api_key:
            await websocket.accept()
            await websocket.close(code=1011, reason="Voice runtime is not fully configured.")
            return

        resume, job, questions, call = await self._load_context(resume_id)
        call_id = call.id if call else None
        state = ConversationState()

        await websocket.accept()
        stream_id: str | None = None
        provider_call_id: str | None = call.provider_call_id if call else None
        stop_event = asyncio.Event()
        finalized_segments: list[str] = []

        stt_url = (
            f"wss://api.deepgram.com/v1/listen?model={settings.DEEPGRAM_STT_MODEL}"
            "&encoding=mulaw&sample_rate=8000&interim_results=true"
            "&vad_events=true&endpointing=300&utterance_end_ms=1000&punctuate=true&smart_format=true"
        )
        stt_headers = {"Authorization": f"Token {self.deepgram_api_key}"}

        async with websockets.connect(stt_url, additional_headers=stt_headers) as stt_ws:

            async def receive_stt_events() -> None:
                nonlocal finalized_segments
                try:
                    async for raw in stt_ws:
                        if isinstance(raw, bytes):
                            continue
                        data = json.loads(raw)
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

                        if data.get("is_final"):
                            finalized_segments.append(transcript)
                        if not data.get("speech_final"):
                            continue

                        utterance = " ".join(finalized_segments).strip() or transcript
                        finalized_segments = []
                        if not call_id:
                            continue
                        await self._append_message(
                            call_id,
                            "user",
                            utterance,
                            item_key=f"deepgram-user-{uuid.uuid4()}",
                        )
                        await self._mark_first_user_transcript(call_id)

                        state_changed = False
                        if self._is_end_intent(utterance) or self._is_negative_or_decline(utterance):
                            state.termination_requested = True
                            state_changed = True
                        elif not state.consent_granted:
                            if (
                                state.consent_prompt_delivered
                                and self._is_affirmative_consent(utterance)
                            ):
                                state.consent_granted = True
                                state_changed = True
                        if self._is_off_topic_request(utterance):
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
                            continue
                        if not state.consent_granted and self._is_consent_prompt(response_text):
                            state.consent_prompt_delivered = True
                        await self._append_message(
                            call_id,
                            "assistant",
                            response_text,
                            item_key=f"deepgram-assistant-{uuid.uuid4()}",
                        )
                        await self._speak_text(
                            websocket=websocket,
                            provider=provider,
                            stream_id=stream_id or "",
                            text=response_text,
                            call_id=call_id,
                        )
                        if state_changed and self._should_end_call(response_text) and provider_call_id:
                            await asyncio.to_thread(self.telephony.end_call, provider_call_id)
                            stop_event.set()
                            return
                finally:
                    stop_event.set()

            stt_task = asyncio.create_task(receive_stt_events())
            try:
                while not stop_event.is_set():
                    try:
                        payload = await websocket.receive_text()
                    except Exception:
                        break
                    data = json.loads(payload)
                    event = data.get("event")
                    if event == "start":
                        stream_id = self._extract_stream_id(data)
                        provider_call_id = self._extract_provider_call_id(
                            provider=provider,
                            payload=data,
                        ) or provider_call_id
                        if call_id:
                            await self._update_call_started(call_id, provider, provider_call_id)
                            async with self._session_factory() as session:
                                call_record = await session.get(Call, call_id)
                                if call_record is not None:
                                    call_record.latency_metrics = append_latency_marker(
                                        call_record.latency_metrics, key="stream_connected_at"
                                    )
                                    await session.commit()
                            opener = await self._generate_next_turn(
                                call_id=call_id,
                                resume=resume,
                                job=job,
                                questions=questions,
                                state=state,
                            )
                            if opener:
                                if self._is_consent_prompt(opener):
                                    state.consent_prompt_delivered = True
                                await self._append_message(
                                    call_id,
                                    "assistant",
                                    opener,
                                    item_key=f"deepgram-assistant-opener-{uuid.uuid4()}",
                                )
                                await self._speak_text(
                                    websocket=websocket,
                                    provider=provider,
                                    stream_id=stream_id or "",
                                    text=opener,
                                    call_id=call_id,
                                )
                    elif event == "media":
                        audio_payload = (data.get("media") or {}).get("payload")
                        if audio_payload:
                            await stt_ws.send(base64.b64decode(audio_payload))
                    elif event == "stop":
                        break
            finally:
                stop_event.set()
                stt_task.cancel()
                if call_id:
                    async with self._session_factory() as session:
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
                await websocket.close()
