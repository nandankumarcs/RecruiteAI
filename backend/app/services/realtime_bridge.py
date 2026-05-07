"""
Twilio <-> OpenAI Realtime bridge for phone interviews.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import websockets
from fastapi import WebSocket
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.call import Call
from app.models.call_message import CallMessage
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.services.call_evaluation import auto_evaluate_call_if_ready
from app.services.observability import append_latency_marker, merge_latency_metric
from app.services.pricing import estimate_telephony_cost, merge_cost_breakdown
from app.services.telephony import get_telephony_service

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ConversationState:
    consent_granted: bool = False
    termination_requested: bool = False
    off_topic_count: int = 0
    consent_prompt_delivered: bool = False


class RealtimeBridge:
    """Bridge Twilio media streams to the OpenAI Realtime API."""

    def __init__(self):
        self.model = settings.OPENAI_REALTIME_MODEL
        self.voice = settings.OPENAI_REALTIME_VOICE
        self.api_key = settings.OPENAI_API_KEY
        self.transcription_model = settings.OPENAI_TRANSCRIPTION_MODEL
        self.telephony = get_telephony_service()
        self._last_message_keys: dict[uuid.UUID, tuple[str, str]] = {}

    @staticmethod
    def _is_terminal_status(status: str | None) -> bool:
        return status in {"completed", "failed", "no_answer"}

    async def _load_context(
        self, resume_id: uuid.UUID
    ) -> tuple[Resume, Job, list[InterviewQuestion], Call | None]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Resume, Job)
                .join(Job, Resume.job_id == Job.id)
                .where(Resume.id == resume_id)
            )
            row = result.one()
            resume, job = row
            questions_result = await session.execute(
                select(InterviewQuestion)
                .where(InterviewQuestion.resume_id == resume_id)
                .order_by(InterviewQuestion.order_index.asc())
            )
            call_result = await session.execute(
                select(Call)
                .where(Call.resume_id == resume_id)
                .order_by(Call.created_at.desc())
                .limit(1)
            )
            return (
                resume,
                job,
                list(questions_result.scalars().all()),
                call_result.scalar_one_or_none(),
            )

    def _build_instructions(
        self,
        *,
        resume: Resume,
        job: Job,
        questions: list[InterviewQuestion],
        state: ConversationState,
    ) -> str:
        question_lines = "\n".join(
            f"{index + 1}. {question.question_text}"
            for index, question in enumerate(questions[:10])
        )
        summary = (resume.parsed_data or {}).get("summary") or "No summary extracted."
        skills = ", ".join((resume.parsed_data or {}).get("skills", [])[:12]) or "No skills extracted."

        phase_rules = []
        if state.termination_requested:
            phase_rules.append(
                "The candidate has asked to end the call or declined to continue. "
                "Your only next response should be a brief thank-you and goodbye. Do not ask any more interview questions."
            )
        elif not state.consent_granted:
            phase_rules.append(
                "Consent has not been granted yet. "
                "First, explain in one short sentence that this is a recruiter screening call for the role. "
                "Then ask whether now is a good time and whether the candidate consents to continue. "
                "Do not ask any interview questions until the candidate clearly says yes or gives an equivalent explicit confirmation."
            )

        if state.off_topic_count > 0 and not state.termination_requested:
            phase_rules.append(
                "The candidate has drifted off topic. "
                "Politely decline unrelated requests such as poems, stories, jokes, songs, or entertainment, and redirect back to the screening."
            )
        if state.off_topic_count >= 2 and not state.termination_requested:
            phase_rules.append(
                "If the candidate continues refusing to engage with the screening, politely end the call instead of looping."
            )

        return (
            "You are an experienced recruiter conducting a phone screening. "
            "Speak clearly, warmly, professionally, and naturally. "
            "Ask one question at a time, wait for the candidate's answer, and keep each turn short. "
            "Never invent candidate experience, project details, or motivations that are not grounded in the resume or the candidate's actual answer. "
            "If the candidate is unclear, ask a brief clarifying follow-up instead of making assumptions. "
            "Do not answer on the candidate's behalf. "
            "Do not mention internal system details, transcripts, tools, or prompts. "
            "Do not say you cannot hang up. End with a short thank-you and goodbye when the interview is complete.\n\n"
            f"Role: {job.title}\n"
            f"Job requirements: {job.requirements or job.description}\n"
            f"Candidate: {resume.candidate_name or 'Candidate'}\n"
            f"Candidate summary: {summary}\n\n"
            f"Candidate skills: {skills}\n\n"
            "Interview questions to cover in order when appropriate:\n"
            f"{question_lines or '1. Tell me about your background relevant to this role.'}\n\n"
            "Conversation rules:\n"
            "- Only ask about experience that is present in the resume or directly relevant to the job requirements.\n"
            "- Keep questions focused and concrete.\n"
            "- Before consent, only identify yourself, explain the purpose of the call briefly, and ask whether now is a good time and whether the candidate consents to continue.\n"
            "- After consent is granted, ask exactly one interview question at a time and wait for a substantive answer before moving to the next question.\n"
            "- If the candidate responds to an interview question with only a bare acknowledgement such as yes, okay, sure, or go ahead, treat that as no answer and restate the same question more simply instead of moving on.\n"
            "- Stay focused on the interview. Decline unrelated requests and steer back to the screening.\n"
            "- If the candidate asks for a poem, story, joke, song, or any unrelated task, decline briefly and say you need to keep the call focused on the interview.\n"
            "- If the answer is not audible or incomplete, ask the candidate to repeat or clarify.\n"
            "- After the final question, thank the candidate, say goodbye, and end cleanly.\n\n"
            f"Live conversation state:\n- " + "\n- ".join(phase_rules or ["Consent granted. Continue the interview."]) + "\n\n"
            "Follow the live conversation state exactly."
        )

    @staticmethod
    def _clean_message_text(content: str | None) -> str:
        return (content or "").strip()

    @staticmethod
    def _should_end_call(content: str) -> bool:
        lowered = content.lower()
        closing_signals = [
            "thank you for your time",
            "we'll be in touch",
            "have a great day",
            "goodbye",
        ]
        return sum(1 for signal in closing_signals if signal in lowered) >= 2

    @staticmethod
    def _normalize_text(content: str) -> str:
        return " ".join(content.lower().strip().split())

    @classmethod
    def _is_affirmative_consent(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        if not text:
            return False
        phrases = [
            "yes",
            "yeah",
            "yep",
            "sure",
            "okay",
            "ok",
            "go ahead",
            "let's do it",
            "lets do it",
            "continue",
            "i consent",
            "you can start",
            "now is a good time",
        ]
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _is_negative_or_decline(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        phrases = [
            "no",
            "not now",
            "not interested",
            "busy",
            "call later",
            "another time",
            "i don't want",
            "do not continue",
            "don't continue",
            "no thanks",
        ]
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _is_end_intent(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        phrases = [
            "disconnect",
            "end the call",
            "hang up",
            "stop the call",
            "i'm not interested",
            "im not interested",
            "we'll disconnect",
            "we will disconnect",
            "bye",
            "goodbye",
        ]
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _is_clarification_request(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        phrases = [
            "what is this",
            "who is this",
            "can you tell me a bit",
            "what is this again",
            "i did not understand",
            "what role",
            "which role",
        ]
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _is_off_topic_request(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        phrases = [
            "write a poem",
            "tell me a story",
            "tell the story",
            "tell me a joke",
            "sing a song",
            "write a song",
        ]
        return any(phrase in text for phrase in phrases)

    @classmethod
    def _looks_like_incomplete_assistant_fragment(cls, content: str) -> bool:
        text = cls._clean_message_text(content)
        if not text:
            return False
        if text.endswith((".", "?", "!")):
            return False
        if len(text) > 180:
            return False
        lowered = text.lower().rstrip(",")
        trailing_words = (
            "and",
            "or",
            "if",
            "when",
            "which",
            "what",
            "how",
            "why",
            "because",
            "for example",
            "could you",
            "would you",
        )
        return any(lowered.endswith(word) for word in trailing_words)

    @classmethod
    def _is_consent_prompt(cls, content: str) -> bool:
        text = cls._normalize_text(content)
        if not text:
            return False
        return (
            ("good time" in text or "consent" in text)
            and ("screening" in text or "recruit" in text or "role" in text)
        )

    async def _close_call_with_message(
        self,
        *,
        call_id: uuid.UUID | None,
        provider_call_id: str | None,
        message: str,
    ) -> None:
        cleaned = self._clean_message_text(message)
        if call_id:
            await self._append_message(
                call_id,
                "assistant",
                cleaned,
                item_key=f"closing-{uuid.uuid4()}",
            )
        if provider_call_id:
            await asyncio.to_thread(self.telephony.say_and_hangup, provider_call_id, cleaned)

    async def _update_session_instructions(
        self,
        openai_ws,
        *,
        resume: Resume,
        job: Job,
        questions: list[InterviewQuestion],
        state: ConversationState,
    ) -> None:
        await openai_ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "instructions": self._build_instructions(
                            resume=resume, job=job, questions=questions, state=state
                        ),
                        "output_modalities": ["audio"],
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcmu"},
                                "turn_detection": {"type": "server_vad"},
                                "transcription": {
                                    "model": self.transcription_model,
                                },
                            },
                            "output": {
                                "format": {"type": "audio/pcmu"},
                                "voice": self.voice,
                            },
                        },
                    },
                }
            )
        )

    @staticmethod
    def _extract_item_id(event: dict) -> str | None:
        return (
            event.get("item_id")
            or event.get("item", {}).get("id")
            or event.get("response", {}).get("item_id")
        )

    @classmethod
    def _extract_transcript_text(cls, event: dict) -> str:
        direct = cls._clean_message_text(event.get("transcript"))
        if direct:
            return direct

        item = event.get("item") or {}
        for content in item.get("content", []) or []:
            transcript = cls._clean_message_text(content.get("transcript"))
            if transcript:
                return transcript
            text = cls._clean_message_text(content.get("text"))
            if text:
                return text

        delta = event.get("delta")
        if isinstance(delta, dict):
            transcript = cls._clean_message_text(delta.get("transcript"))
            if transcript:
                return transcript

        return ""

    async def _append_message(
        self,
        call_id: uuid.UUID,
        role: str,
        content: str,
        *,
        item_key: str | None = None,
    ) -> None:
        cleaned = self._clean_message_text(content)
        if not cleaned:
            return

        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return

            latest_message = await session.execute(
                select(CallMessage)
                .where(CallMessage.call_id == call_id)
                .order_by(CallMessage.sequence_number.desc())
                .limit(1)
            )
            previous = latest_message.scalar_one_or_none()
            last_message_key = self._last_message_keys.get(call_id)
            merge_with_previous = (
                previous is not None
                and previous.role == role
                and item_key is not None
                and last_message_key == (role, item_key)
            )
            if merge_with_previous:
                if cleaned == previous.content:
                    return
                if cleaned.startswith(previous.content):
                    previous.content = cleaned
                    lines = (call.transcript or "").splitlines()
                    if lines:
                        lines[-1] = f"{role.title()}: {cleaned}"
                        call.transcript = "\n".join(lines)
                    else:
                        call.transcript = f"{role.title()}: {cleaned}"
                    await session.commit()
                    return

            existing = await session.execute(
                select(CallMessage.sequence_number)
                .where(CallMessage.call_id == call_id)
                .order_by(CallMessage.sequence_number.desc())
                .limit(1)
            )
            last_sequence = existing.scalar_one_or_none() or 0
            session.add(
                CallMessage(
                    call_id=call_id,
                    role=role,
                    content=cleaned,
                    sequence_number=last_sequence + 1,
                )
            )
            if item_key is not None:
                self._last_message_keys[call_id] = (role, item_key)
            call.transcript = (
                f"{call.transcript}\n{role.title()}: {cleaned}".strip()
                if call.transcript
                else f"{role.title()}: {cleaned}"
            )
            await session.commit()

    async def _mark_call_status(self, call_id: uuid.UUID, status: str) -> None:
        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            call.status = status
            await session.commit()

    async def _update_call_started(
        self,
        call_id: uuid.UUID,
        provider: str,
        provider_call_id: str | None,
    ) -> None:
        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            call.status = "in_progress"
            call.started_at = call.started_at or datetime.now(timezone.utc)
            call.provider = call.provider or provider
            if provider_call_id and not call.provider_call_id:
                call.provider_call_id = provider_call_id
            if provider == "twilio" and provider_call_id and not call.twilio_call_sid:
                call.twilio_call_sid = provider_call_id
            call.latency_metrics = append_latency_marker(
                call.latency_metrics, key="call_answered_at"
            )
            await session.commit()

    async def _update_call_finished(self, call_id: uuid.UUID) -> None:
        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            if not self._is_terminal_status(call.status):
                call.status = "completed"
            call.ended_at = call.ended_at or datetime.now(timezone.utc)
            if call.started_at:
                call.duration_seconds = max(
                    1, int((call.ended_at - call.started_at).total_seconds())
                )
            call.cost_breakdown = merge_cost_breakdown(
                call.cost_breakdown,
                provider=call.provider or "unknown",
                telephony_cost_usd=estimate_telephony_cost(
                    provider=call.provider or "",
                    duration_seconds=call.duration_seconds,
                ),
            )
            await session.commit()
        await auto_evaluate_call_if_ready(call_id)

    async def handle(self, websocket: WebSocket, resume_id: uuid.UUID, provider: str = "twilio") -> None:
        if not self.api_key:
            await websocket.accept()
            await websocket.close(code=1011, reason="OpenAI API key is not configured.")
            return

        resume, job, questions, call = await self._load_context(resume_id)
        call_id = call.id if call else None
        state = ConversationState()

        await websocket.accept()
        stream_id: str | None = None
        provider_call_id: str | None = call.provider_call_id if call else call.twilio_call_sid if call else None
        stop_event = asyncio.Event()
        should_hang_up = False
        assistant_response_active = False
        assistant_cancel_requested = False
        initial_prompt_sent = False
        first_assistant_audio_sent = False
        first_user_transcript_seen = False

        realtime_url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async with websockets.connect(realtime_url, additional_headers=headers) as openai_ws:
            await self._update_session_instructions(
                openai_ws,
                resume=resume,
                job=job,
                questions=questions,
                state=state,
            )

            async def forward_openai_to_twilio() -> None:
                nonlocal assistant_cancel_requested, assistant_response_active, should_hang_up, stream_id
                nonlocal first_assistant_audio_sent, first_user_transcript_seen
                try:
                    async for message in openai_ws:
                        data = json.loads(message)
                        event_type = data.get("type")

                        if event_type in {"response.created", "response.output_audio.delta"}:
                            assistant_response_active = True
                        if event_type == "response.output_audio.delta" and stream_id:
                            delta = data.get("delta")
                            if delta:
                                if call_id and not first_assistant_audio_sent:
                                    first_assistant_audio_sent = True
                                    async with async_session_factory() as session:
                                        call_record = await session.get(Call, call_id)
                                        if call_record is not None:
                                            call_record.latency_metrics = append_latency_marker(
                                                call_record.latency_metrics,
                                                key="first_assistant_audio_at",
                                            )
                                            await session.commit()
                                await websocket.send_json(
                                    self._build_audio_event(
                                        provider=provider,
                                        stream_id=stream_id,
                                        payload=delta,
                                    )
                                )
                        elif event_type == "input_audio_buffer.speech_started" and stream_id:
                            await websocket.send_json(
                                self._build_clear_audio_event(provider=provider, stream_id=stream_id)
                            )
                            if assistant_response_active:
                                assistant_cancel_requested = True
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                        elif (
                            event_type.endswith("input_audio_transcription.completed")
                            and call_id
                        ):
                            transcript = self._extract_transcript_text(data)
                            item_key = self._extract_item_id(data) or f"user-{event_type}"
                            await self._append_message(
                                call_id, "user", transcript, item_key=item_key
                            )
                            if not first_user_transcript_seen:
                                first_user_transcript_seen = True
                                async with async_session_factory() as session:
                                    call_record = await session.get(Call, call_id)
                                    if call_record is not None:
                                        call_record.latency_metrics = append_latency_marker(
                                            call_record.latency_metrics,
                                            key="first_user_transcript_at",
                                        )
                                        await session.commit()
                            state_changed = False
                            if self._is_end_intent(transcript) or self._is_negative_or_decline(transcript):
                                if not state.termination_requested:
                                    state.termination_requested = True
                                    state_changed = True
                            elif not state.consent_granted:
                                if (
                                    state.consent_prompt_delivered
                                    and self._is_affirmative_consent(transcript)
                                ):
                                    state.consent_granted = True
                                    state_changed = True
                                elif self._is_clarification_request(transcript):
                                    state_changed = False
                            if self._is_off_topic_request(transcript):
                                state.off_topic_count += 1
                                state_changed = True

                            if state.termination_requested:
                                await self._close_call_with_message(
                                    call_id=call_id,
                                    provider_call_id=provider_call_id,
                                    message="Understood. Thank you for your time today. Goodbye.",
                                )
                                stop_event.set()
                                continue
                            if state.off_topic_count >= 2:
                                await self._close_call_with_message(
                                    call_id=call_id,
                                    provider_call_id=provider_call_id,
                                    message="It sounds like now is not the right time for this screening. Thank you for your time. Goodbye.",
                                )
                                stop_event.set()
                                continue

                            if state_changed:
                                await self._update_session_instructions(
                                    openai_ws,
                                    resume=resume,
                                    job=job,
                                    questions=questions,
                                    state=state,
                                )
                        elif event_type in {
                            "response.output_audio_transcript.done",
                            "response.audio_transcript.done",
                        } and call_id:
                            transcript = self._extract_transcript_text(data)
                            item_key = self._extract_item_id(data) or f"assistant-{event_type}"
                            if (
                                assistant_cancel_requested
                                and self._looks_like_incomplete_assistant_fragment(transcript)
                            ):
                                continue
                            if not state.consent_granted and self._is_consent_prompt(transcript):
                                state.consent_prompt_delivered = True
                            await self._append_message(
                                call_id, "assistant", transcript, item_key=item_key
                            )
                            if state.termination_requested or (
                                state.off_topic_count >= 2 and self._should_end_call(transcript)
                            ):
                                should_hang_up = True
                            elif self._should_end_call(self._clean_message_text(transcript)):
                                should_hang_up = True
                        elif event_type == "response.done" and call_id and should_hang_up:
                            assistant_response_active = False
                            assistant_cancel_requested = False
                            if provider_call_id:
                                await asyncio.to_thread(self.telephony.end_call, provider_call_id)
                            stop_event.set()
                        elif event_type == "response.done":
                            assistant_response_active = False
                            assistant_cancel_requested = False
                        elif event_type == "error" and call_id:
                            error_code = data.get("error", {}).get("code")
                            if error_code == "response_cancel_not_active":
                                logger.warning(
                                    "Ignoring non-fatal Realtime cancel error: %s",
                                    json.dumps(data),
                                )
                                continue
                            logger.error("OpenAI Realtime error event: %s", json.dumps(data))
                            await self._append_message(
                                call_id,
                                "assistant",
                                "I ran into a technical issue during the interview. Thank you for your time today.",
                            )
                            stop_event.set()
                finally:
                    stop_event.set()

            openai_task = asyncio.create_task(forward_openai_to_twilio())

            try:
                while not stop_event.is_set():
                    try:
                        payload = await websocket.receive_text()
                    except Exception:
                        break
                    data = json.loads(payload)
                    event = data.get("event")

                    if event == "start":
                        start = data.get("start", {})
                        stream_id = self._extract_stream_id(data)
                        provider_call_id = self._extract_provider_call_id(
                            provider=provider,
                            payload=data,
                        ) or provider_call_id
                        if call_id:
                            await self._update_call_started(
                                call_id,
                                provider,
                                provider_call_id,
                            )
                            async with async_session_factory() as session:
                                call_record = await session.get(Call, call_id)
                                if call_record is not None:
                                    call_record.latency_metrics = append_latency_marker(
                                        call_record.latency_metrics, key="stream_connected_at"
                                    )
                                    await session.commit()
                        if not initial_prompt_sent:
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                            initial_prompt_sent = True
                    elif event == "media":
                        media = data.get("media", {})
                        audio_payload = media.get("payload")
                        if audio_payload:
                            await openai_ws.send(
                                json.dumps(
                                    {
                                        "type": "input_audio_buffer.append",
                                        "audio": audio_payload,
                                    }
                                )
                            )
                    elif event == "stop":
                        break
            finally:
                stop_event.set()
                openai_task.cancel()
                if call_id:
                    await self._update_call_finished(call_id)
                await websocket.close()

    @staticmethod
    def _extract_stream_id(payload: dict) -> str | None:
        return payload.get("streamSid") or payload.get("streamId") or payload.get("start", {}).get("streamId")

    @staticmethod
    def _build_audio_event(*, provider: str, stream_id: str, payload: str) -> dict:
        if provider == "plivo":
            return {
                "event": "playAudio",
                "media": {
                    "contentType": "audio/x-mulaw",
                    "sampleRate": "8000",
                    "payload": payload,
                },
            }
        return {
            "event": "media",
            "streamSid": stream_id,
            "media": {"payload": payload},
        }

    @staticmethod
    def _build_clear_audio_event(*, provider: str, stream_id: str) -> dict:
        if provider == "plivo":
            return {"event": "clearAudio", "streamId": stream_id}
        return {"event": "clear", "streamSid": stream_id}

    @staticmethod
    def _extract_provider_call_id(*, provider: str, payload: dict) -> str | None:
        if provider == "plivo":
            return payload.get("start", {}).get("callId")
        return payload.get("start", {}).get("callSid")


def get_realtime_bridge() -> RealtimeBridge:
    return RealtimeBridge()
