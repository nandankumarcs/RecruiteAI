"""
Twilio <-> OpenAI Realtime bridge for phone interviews.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
try:
    import audioop
except ImportError:
    import audioop_lts as audioop
import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketState
from openai import AsyncOpenAI
from sqlalchemy import select

# Providers that speak the L16 8kHz PCM wire format (vs Twilio's μ-law).
# Twilio is the only non-L16 provider; everything else uses Exotel's framing.
_L16_PROVIDERS = ("exotel", "browser")

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


@dataclass
class CandidateTurnAnalysis:
    grant_consent: bool = False
    request_termination: bool = False
    off_topic_request: bool = False


class RealtimeBridge:
    """Bridge Twilio media streams to the OpenAI Realtime API."""

    def __init__(self):
        self.model = settings.OPENAI_REALTIME_MODEL
        self.voice = settings.OPENAI_REALTIME_VOICE
        self.api_key = settings.OPENAI_API_KEY
        self.transcription_model = settings.OPENAI_TRANSCRIPTION_MODEL
        self.text_model = settings.OPENAI_TEXT_MODEL or settings.OPENAI_MODEL
        self._analysis_client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        self.telephony = get_telephony_service()
        self._last_message_keys: dict[uuid.UUID, tuple[str, str]] = {}

    @staticmethod
    def _is_terminal_status(status: str | None) -> bool:
        return status in {"completed", "failed", "no_answer"}

    async def _load_context(
        self, resume_id: uuid.UUID
    ) -> tuple[Resume, Job, list[InterviewQuestion], Call | None]:
        async with async_session_factory() as session:
            try:
                result = await session.execute(
                    select(Resume, Job)
                    .join(Job, Resume.job_id == Job.id)
                    .where(Resume.id == resume_id)
                )
                row = result.one()
                resume, job = row
                
                questions_result = await session.execute(
                    select(InterviewQuestion)
                    .where(InterviewQuestion.job_id == job.id)
                    .order_by(InterviewQuestion.order_index.asc())
                )
                questions = list(questions_result.scalars().all())
                
                call_result = await session.execute(
                    select(Call)
                    .where(Call.resume_id == resume_id)
                    .order_by(Call.created_at.desc())
                    .limit(1)
                )
                call = call_result.scalar_one_or_none()
                
                return resume, job, questions, call
                
            except Exception as e:
                import sys
                print(f"!!! FALLBACK CONTEXT TRIGGERED !!! Error: {e}", file=sys.stderr, flush=True)
                
                # Create a minimal mock resume/job for testing
                # Need a valid user_id to satisfy Job constraint if we were to persist
                dummy_user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
                
                mock_job = Job(
                    id=uuid.uuid4(),
                    user_id=dummy_user_id,
                    title="Exotel Test Position",
                    description="Test call for Exotel integration",
                    requirements="Willingness to talk to a robot"
                )
                mock_resume = Resume(
                    id=resume_id,
                    candidate_name="Candidate (Dev/Test)",
                    email="test@example.com",
                    job_id=mock_job.id,
                    file_path="mock/test.pdf",
                    file_type="pdf"
                )
                mock_questions = [
                    InterviewQuestion(
                        id=uuid.uuid4(),
                        job_id=mock_job.id,
                        question_text="Could you please introduce yourself and tell me what you're looking for?",
                        order_index=0
                    )
                ]
                # We return None for call to avoid DB persistence issues in mock mode
                return mock_resume, mock_job, mock_questions, None

    @staticmethod
    def _candidate_first_name(resume: Resume) -> str:
        name = (resume.candidate_name or "there").strip()
        return name.split()[0] if name else "there"

    def _build_initial_consent_prompt(self, *, resume: Resume, job: Job) -> str:
        first_name = self._candidate_first_name(resume)
        return (
            f"Hi {first_name}, this is RecruiteAI calling about your application. "
            "Is now a good time for a short screening?"
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
            phase_rules.append("Candidate declined/ended. Say thank you and goodbye. No more questions.")
        elif not state.consent_granted:
            phase_rules.append(
                f"Identify yourself as a RecruiteAI assistant for the {job.title} role. "
                "Ask for consent to continue the screening. Do NOT ask interview questions yet."
            )
        else:
            phase_rules.append("Consent granted. Ask exactly ONE interview question from the list below and wait for a full answer.")

        if state.off_topic_count > 0 and not state.termination_requested:
            phase_rules.append("Candidate is off-topic. Politely redirect to the interview.")
        if state.off_topic_count >= 2 and not state.termination_requested:
            phase_rules.append("Refusal to engage. Politely end the call.")

        return (
            "Persona: Warm, professional recruiter. Speak naturally and clearly.\n"
            "Process: Ask 1 question at a time. Wait for answer. Keep turns short. Do not invent details.\n"
            "Voice constraints: Reply in one sentence, under 12 words, unless ending the call.\n"
            f"Role: {job.title} | Req: {job.requirements or job.description[:200]}\n"
            f"Candidate: {resume.candidate_name or 'Candidate'} | Skills: {skills}\n"
            f"Summary: {summary}\n\n"
            "Questions:\n"
            f"{question_lines or '1. Tell me about your background.'}\n\n"
            "Critical Rules:\n"
            "- No consent = No interview questions.\n"
            "- If answer is too short (yes/ok), ask for details/restate question.\n"
            "- If the candidate sounds mid-sentence, incomplete, or paused briefly, wait for continuation instead of interrupting.\n"
            "- Ask at most one concise follow-up before moving on. Do not stack multiple follow-ups on a partial answer.\n"
            "- If the candidate says hello or asks if you are there, acknowledge once and repeat only the core question.\n"
            "- If the candidate asks a clarifying or meta question, answer it briefly and then restate only the core question.\n"
            "- Treat clarification, confusion, or requests to repeat as continued engagement, not refusal or completion.\n"
            "- Decline non-interview requests (poems/stories/jokes) once, then hang up if they persist.\n"
            "- Do not end the call unless the candidate clearly refuses, asks to stop, or all interview questions are complete.\n"
            "- After final question, say goodbye and end.\n\n"
            "Current State:\n- " + "\n- ".join(phase_rules)
        )


    @staticmethod
    def _clean_message_text(content: str | None) -> str:
        return (content or "").strip()

    @classmethod
    def _clean_assistant_spoken_text(cls, content: str | None) -> str:
        text = cls._clean_message_text(content)
        labels = ("assistant:", "recruiter:", "ai recruiter:", "recruiteai assistant:")
        while True:
            lowered = text.lower()
            for label in labels:
                if lowered.startswith(label):
                    text = text[len(label):].strip()
                    break
            else:
                return text

    @classmethod
    def _compress_assistant_spoken_text(cls, content: str | None) -> str:
        text = cls._clean_assistant_spoken_text(content)
        lowered = text.lower()
        asks_intro_and_interest = (
            "introduce yourself" in lowered
            and ("why you are interested" in lowered or "why this role interests" in lowered)
        )
        if asks_intro_and_interest:
            if "clarification" in lowered or "confusion" in lowered or "hello" in lowered:
                return "I'm here. Tell me about yourself and why this role interests you."
            return "Tell me about yourself and why this role interests you."

        words = text.split()
        if len(words) <= 18:
            return text

        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
        if first_sentence and len(first_sentence.split()) <= 18:
            return first_sentence
        return " ".join(words[:18]).rstrip(".,;:") + "."

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

    async def _analyze_candidate_turn(
        self,
        *,
        transcript: str,
        state: ConversationState,
    ) -> CandidateTurnAnalysis:
        cleaned = self._clean_message_text(transcript)
        if not cleaned or self._analysis_client is None:
            return CandidateTurnAnalysis()

        heuristic = self._analyze_candidate_turn_fast(cleaned, state)
        if heuristic is not None:
            return heuristic

        try:
            completion = await self._analysis_client.chat.completions.create(
                model=self.text_model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You classify the latest candidate utterance in a phone screening. "
                            "Return strict JSON with boolean keys: "
                            "grant_consent, request_termination, off_topic_request. "
                            "Be conservative. Clarification, confusion, requests to repeat, silence checks, "
                            "or short answers are continued engagement, not refusal. "
                            "Only set grant_consent=true if the candidate clearly agrees to continue the screening "
                            "after being asked for consent. "
                            "Only set request_termination=true if the candidate clearly refuses, asks to stop, "
                            "asks to disconnect, or says they are not interested in continuing. "
                            "Only set off_topic_request=true for clearly unrelated entertainment or side-task requests."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "candidate_utterance": cleaned,
                                "consent_prompt_delivered": state.consent_prompt_delivered,
                                "consent_already_granted": state.consent_granted,
                                "termination_already_requested": state.termination_requested,
                                "off_topic_count": state.off_topic_count,
                            }
                        ),
                    },
                ],
            )
            payload = json.loads((completion.choices[0].message.content or "{}").strip() or "{}")
            return CandidateTurnAnalysis(
                grant_consent=bool(payload.get("grant_consent")),
                request_termination=bool(payload.get("request_termination")),
                off_topic_request=bool(payload.get("off_topic_request")),
            )
        except Exception:
            logger.exception("Failed to analyze candidate turn; defaulting to neutral interpretation.")
            return CandidateTurnAnalysis()

    @classmethod
    def _analyze_candidate_turn_fast(
        cls,
        transcript: str,
        state: ConversationState,
    ) -> CandidateTurnAnalysis | None:
        text = cls._normalize_text(transcript)
        if not text:
            return CandidateTurnAnalysis()
        text_for_match = f" {text} "
        for punctuation in (".", ",", "!", "?", ";", ":"):
            text_for_match = text_for_match.replace(punctuation, " ")
        text_for_match = " ".join(text_for_match.split())
        text_for_match = f" {text_for_match} "

        termination_phrases = (
            "bye",
            "goodbye",
            "bye bye",
            "okay bye",
            "ok bye",
            "thank you bye",
            "not interested",
            "don't call",
            "do not call",
            "stop calling",
            "disconnect",
            "hang up",
            "end the call",
            "cut the call",
            "remove my number",
            "call me later",
            "busy right now",
            "not a good time",
        )
        if any(phrase in text for phrase in termination_phrases):
            return CandidateTurnAnalysis(request_termination=True)

        off_topic_phrases = (
            "tell me a joke",
            "sing a song",
            "write a poem",
            "tell me a story",
            "play music",
        )
        if any(phrase in text for phrase in off_topic_phrases):
            return CandidateTurnAnalysis(off_topic_request=True)

        if state.consent_prompt_delivered and not state.consent_granted:
            consent_phrases = (
                "yes",
                "yeah",
                "yep",
                "sure",
                "okay",
                "ok",
                "go ahead",
                "continue",
                "i agree",
                "i consent",
                "good time",
                "you can continue",
                "please continue",
            )
            if text.strip(".,!?;:") in consent_phrases or any(
                f" {phrase} " in text_for_match for phrase in consent_phrases
            ):
                return CandidateTurnAnalysis(grant_consent=True)

        clarification_phrases = (
            "who is this",
            "can you repeat",
            "please repeat",
            "what role",
            "which company",
            "i did not understand",
            "i didn't understand",
        )
        if any(phrase in text for phrase in clarification_phrases):
            return CandidateTurnAnalysis()

        return None

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
    def _looks_like_incomplete_user_fragment(cls, content: str) -> bool:
        text = cls._clean_message_text(content)
        if not text:
            return False

        normalized = " ".join(text.split())
        lowered = normalized.lower()
        stripped = lowered.rstrip()

        # Strong signals — always fragment
        if normalized.endswith(","):
            return True
        if normalized.endswith(("...", "…")):
            return True
        if len(normalized.split()) <= 2 and not normalized.endswith((".", "?", "!")):
            return True

        # Medium confidence — no terminal punctuation AND last word suggests continuation.
        # Evidence-based list derived from call ea395892 and common Indian-English
        # conversational patterns. "the" alone caught "I built one of the" → triggers.
        _CONTINUATION_WORDS = frozenset({
            # Conjunctions / connectors (original)
            "and", "or", "because", "so", "for", "but", "then", "like",
            "which", "that",
            # Common sentence-ending fragments from real calls
            "the", "a", "an", "of", "to", "in", "on", "at", "by", "with",
            "not", "no", "was", "were", "is", "are", "it",
            # First-person mid-thought breaks
            "i", "i'm", "i've", "i'd", "i'll",
            "you", "we", "they", "he", "she",
            # Hedging / discourse markers
            "basically", "essentially", "generally", "actually",
            "you know", "kind of", "sort of", "type of",
            "part of", "one of", "some of",
            "such as", "for example", "for instance",
            "so i", "so we", "so it", "so that",
            "and then", "and also", "and we", "and i",
            "related to",
            "something like",
            # Pause fillers
            "let me think", "one second", "um", "uh", "hmm",
            # Domain-specific trailing patterns from recruitment calls
            "these are the few things that we generally look for",
            "so on python",
        })
        if not normalized.rstrip().endswith((".", "?", "!", "...")):
            last_word = stripped.split()[-1] if stripped.split() else ""
            if last_word in _CONTINUATION_WORDS:
                return True
            # Check last two words for multi-word trailing phrases
            words = stripped.split()
            if len(words) >= 2:
                last_two = f"{words[-2]} {words[-1]}"
                if last_two in _CONTINUATION_WORDS:
                    return True

        return False

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
        import sys
        print("=== OPENAI HANDLE CALLED ===", file=sys.stderr, flush=True)
        if not self.api_key:
            if websocket.application_state == WebSocketState.CONNECTING:
                await websocket.accept()
            await websocket.close(code=1011, reason="OpenAI API key is not configured.")
            return

        resume, job, questions, call = await self._load_context(resume_id)
        call_id = call.id if call else None
        state = ConversationState()

        if websocket.application_state == WebSocketState.CONNECTING:
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

        # --- Coalescing buffers ---
        assistant_text_buffer: str = ""
        current_response_id: str | None = None

        realtime_url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        logger.info("=== [0] Connecting to OpenAI Realtime (call=%s) ===", call_id)

        try:
            async with websockets.connect(realtime_url, additional_headers=headers) as openai_ws:
                logger.info("=== [1] OpenAI Realtime CONNECTED (call=%s) ===", call_id)
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
                    nonlocal assistant_text_buffer, current_response_id
                    try:
                        async for message in openai_ws:
                            data = json.loads(message)
                            event_type = data.get("type")

                            # --- Audio Deltas ---
                            if event_type in {"response.created", "response.output_audio.delta"}:
                                assistant_response_active = True
                                if event_type == "response.created":
                                    current_response_id = data.get("response", {}).get("id")
                                    assistant_text_buffer = ""

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
                                    payload = delta
                                    if provider in _L16_PROVIDERS:
                                        try:
                                            pcmu_bytes = base64.b64decode(delta)
                                            # Transcode PCMU (8kHz) to L16 (8kHz, Mono)
                                            l16_bytes = audioop.ulaw2lin(pcmu_bytes, 2)
                                            payload = base64.b64encode(l16_bytes).decode('ascii')
                                            
                                            # Debug log for audio flow
                                            if not hasattr(self, '_audio_log_count'): self._audio_log_count = 0
                                            self._audio_log_count += 1
                                            if self._audio_log_count % 50 == 0:
                                                logger.debug(
                                                    "[TRANSCODE] PCMU size: %d -> L16 size: %d (call=%s)", 
                                                    len(pcmu_bytes), len(l16_bytes), call_id
                                                )
                                        except Exception as e:
                                            logger.warning("Failed to transcode PCMU to L16: %s", e)
                                    
                                    await websocket.send_json(
                                        self._build_audio_event(
                                            provider=provider,
                                            stream_id=stream_id,
                                            payload=payload,
                                        )
                                    )

                            # --- Transcript Deltas (Coalescing) ---
                            elif event_type in {"response.audio_transcript.delta", "response.output_audio_transcript.delta"}:
                                delta = data.get("delta") or ""
                                assistant_text_buffer += delta

                            # --- User Interruption (Barge-in) ---
                            elif event_type == "input_audio_buffer.speech_started" and stream_id:
                                logger.info("User started speaking (call=%s), cancelling assistant output.", call_id)
                                await websocket.send_json(
                                    self._build_clear_audio_event(provider=provider, stream_id=stream_id)
                                )
                                if assistant_response_active:
                                    assistant_cancel_requested = True
                                    await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                    assistant_text_buffer = "" # Clear buffer on interruption

                            # --- User Transcript Finalized ---
                            elif (
                                event_type.endswith("input_audio_transcription.completed")
                                and call_id
                            ):
                                transcript = self._extract_transcript_text(data)
                                if not transcript:
                                    continue

                                logger.info("User transcript completed (call=%s): %s", call_id, transcript)
                                item_key = self._extract_item_id(data) or f"user-{event_type}-{uuid.uuid4()}"
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

                                analysis = await self._analyze_candidate_turn(
                                    transcript=transcript,
                                    state=state,
                                )

                                state_changed = False
                                if analysis.request_termination:
                                    if not state.termination_requested:
                                        logger.info("Termination requested by candidate (call=%s)", call_id)
                                        state.termination_requested = True
                                        state_changed = True
                                elif analysis.grant_consent and not state.consent_granted:
                                    logger.info("Consent granted by candidate (call=%s)", call_id)
                                    state.consent_granted = True
                                    state_changed = True

                                if analysis.off_topic_request:
                                    state.off_topic_count += 1
                                    logger.warning("Off-topic count increased (call=%s, count=%s)", call_id, state.off_topic_count)
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

                            # --- Assistant Response Finalized (Coalescing Flush) ---
                            elif event_type == "response.done" and call_id:
                                assistant_response_active = False
                                assistant_cancel_requested = False
                                
                                response_data = data.get("response", {})
                                status = response_data.get("status")
                                
                                if status == "cancelled":
                                    logger.info("Assistant response cancelled (call=%s)", call_id)
                                    assistant_text_buffer = ""
                                    continue

                                # Get finalized transcript if available in response.done, otherwise use buffer
                                final_transcript = ""
                                for item in response_data.get("output", []):
                                    if item.get("type") == "message":
                                        for content in item.get("content", []):
                                            if content.get("type") == "audio":
                                                final_transcript += content.get("transcript", "")
                                            elif content.get("type") == "text":
                                                final_transcript += content.get("text", "")
                                
                                transcript = (final_transcript or assistant_text_buffer).strip()
                                
                                if transcript:
                                    logger.info("Assistant turn completed (call=%s): %s", call_id, transcript)
                                    item_key = current_response_id or f"assistant-resp-{uuid.uuid4()}"
                                    
                                    if not state.consent_granted and self._is_consent_prompt(transcript):
                                        state.consent_prompt_delivered = True
                                        
                                    await self._append_message(
                                        call_id, "assistant", transcript, item_key=item_key
                                    )
                                    
                                    if state.termination_requested or (
                                        state.off_topic_count >= 2 and self._should_end_call(transcript)
                                    ):
                                        should_hang_up = True
                                    elif self._should_end_call(transcript):
                                        should_hang_up = True

                                assistant_text_buffer = "" # Clear for next response
                                
                                if should_hang_up:
                                    logger.info("Hanging up call after assistant closing (call=%s)", call_id)
                                    if provider_call_id:
                                        await asyncio.to_thread(self.telephony.end_call, provider_call_id)
                                    stop_event.set()

                            elif event_type == "error":
                                error_data = data.get("error", {})
                                error_code = error_data.get("code")
                                error_msg = error_data.get("message")
                                if error_code == "response_cancel_not_active":
                                    continue
                                logger.error("OpenAI Realtime error (call=%s): %s (%s)", call_id, error_msg, error_code)
                                if call_id:
                                    await self._append_message(
                                        call_id,
                                        "assistant",
                                        "I ran into a technical issue during the interview. Thank you for your time today.",
                                    )
                                stop_event.set()
                        
                        logger.info("OpenAI receive loop ended (call=%s)", call_id)
                    except Exception as e:
                        logger.exception("Exception in forward_openai_to_twilio (call=%s): %s", call_id, e)
                    finally:
                        stop_event.set()

                openai_task = asyncio.create_task(forward_openai_to_twilio())

                try:
                    while not stop_event.is_set():
                        try:
                            # Use wait_for to allow checking stop_event periodically if needed, 
                            # though receive_text is usually fine.
                            payload = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                        except asyncio.TimeoutError:
                            # Heartbeat check/Keepalive logic could go here if needed for Twilio
                            continue
                        except Exception as e:
                            logger.info("Twilio/Client websocket closed (call=%s): %s", call_id, e)
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
                            logger.info("Stream START received (call=%s, stream=%s)", call_id, stream_id)
                            
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
                                if provider in _L16_PROVIDERS:
                                    try:
                                        l16_bytes = base64.b64decode(audio_payload)
                                        pcmu_bytes = audioop.lin2ulaw(l16_bytes, 2)
                                        audio_payload = base64.b64encode(pcmu_bytes).decode('ascii')
                                    except Exception as e:
                                        logger.warning("Failed to transcode L16 to PCMU: %s", e)
                                await openai_ws.send(
                                    json.dumps(
                                        {
                                            "type": "input_audio_buffer.append",
                                            "audio": audio_payload,
                                        }
                                    )
                                )
                        elif event == "stop":
                            logger.info("Stream STOP received (call=%s)", call_id)
                            break
                finally:
                    stop_event.set()
                    if not openai_task.done():
                        openai_task.cancel()
                        try:
                            await openai_task
                        except asyncio.CancelledError:
                            pass
                    
                    if call_id:
                        await self._update_call_finished(call_id)
                    
                    try:
                        await websocket.close()
                    except Exception:
                        pass
                    
                    logger.info("=== [X] Bridge lifecycle ended (call=%s) ===", call_id)

        except Exception as e:
            logger.exception("Failed to establish or maintain OpenAI Realtime connection (call=%s): %s", call_id, e)
            if call_id:
                await self._mark_call_status(call_id, "failed")
            try:
                await websocket.close(code=1011, reason="Upstream AI connection failed")
            except Exception:
                pass


    @staticmethod
    def _extract_stream_id(payload: dict) -> str | None:
        return (
            payload.get("streamSid") 
            or payload.get("stream_sid") 
            or payload.get("start", {}).get("streamId")
            or payload.get("start", {}).get("stream_sid")
        )

    @staticmethod
    def _build_audio_event(*, provider: str, stream_id: str, payload: str) -> dict:
        if provider in _L16_PROVIDERS:
            return {
                "event": "media",
                "stream_sid": stream_id,
                "media": {
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
        if provider in _L16_PROVIDERS:
            return {"event": "clear", "stream_sid": stream_id}
        return {"event": "clear", "streamSid": stream_id}

    @staticmethod
    def _extract_provider_call_id(*, provider: str, payload: dict) -> str | None:
        start = payload.get("start", {})
        return start.get("callSid") or start.get("call_sid") or start.get("leg_sid")


def get_realtime_bridge() -> RealtimeBridge:
    return RealtimeBridge()
