"""
Runtime Selection Layer for Audio Source Routing.

Classifies assistant turns and routes them to cached prompt audio when a ready
asset exists, otherwise falling back to live TTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from app.models.audio_prompt_asset import AudioPromptAsset
from app.models.question import InterviewQuestion
from app.services.prompt_templates import DEFAULT_OPENER_TEXT

if TYPE_CHECKING:
    from app.services.filler_queue_manager import FillerQueueManager
    from app.services.prompt_audio_service import PromptAudioService
    from app.services.realtime_bridge import ConversationState


class PromptCategory(str, Enum):
    OPENER = "opener"
    QUESTION = "question"
    REPROMPT = "reprompt"
    CLARIFICATION = "clarification"
    OFF_TOPIC_REDIRECT = "off_topic_redirect"
    CLOSING = "closing"
    FILLER = "filler"
    FALLBACK_DYNAMIC = "fallback_dynamic"


@dataclass
class AudioSourceSelection:
    source_type: str
    template_key: str | None
    asset: AudioPromptAsset | None
    fallback_text: str | None
    filler_key: str | None


class RuntimeSelectionLayer:
    def __init__(
        self,
        prompt_audio_service: "PromptAudioService",
        filler_queue_manager: "FillerQueueManager",
    ) -> None:
        self.prompt_audio = prompt_audio_service
        self.filler_queue = filler_queue_manager

    @staticmethod
    def _normalize_for_matching(text: str) -> str:
        return " ".join((text or "").lower().strip().split())

    def _classify_turn(
        self,
        assistant_text: str,
        conversation_state: "ConversationState",
        *,
        questions: list[InterviewQuestion] | None = None,
    ) -> PromptCategory:
        normalized = self._normalize_for_matching(assistant_text)
        if not conversation_state.consent_granted and not conversation_state.consent_prompt_delivered:
            return PromptCategory.OPENER
        if conversation_state.termination_requested or self._is_closing_phrase(normalized):
            return PromptCategory.CLOSING
        if conversation_state.off_topic_count > 0 and self._is_redirect_phrase(normalized):
            return PromptCategory.OFF_TOPIC_REDIRECT
        if self._is_reprompt_phrase(normalized):
            return PromptCategory.REPROMPT
        if self._is_clarification_phrase(normalized):
            return PromptCategory.CLARIFICATION
        if questions and self._match_question(assistant_text, questions) is not None:
            return PromptCategory.QUESTION
        return PromptCategory.FALLBACK_DYNAMIC

    @staticmethod
    def _is_closing_phrase(normalized_text: str) -> bool:
        return any(
            phrase in normalized_text
            for phrase in (
                "thank you for your time",
                "thanks for your time",
                "we'll be in touch",
                "we will be in touch",
                "have a great day",
                "goodbye",
            )
        )

    @staticmethod
    def _is_redirect_phrase(normalized_text: str) -> bool:
        return any(
            phrase in normalized_text
            for phrase in (
                "let's get back to",
                "let us get back to",
                "back to the question",
                "focus on",
                "stay on topic",
                "relevant to the position",
            )
        )

    @staticmethod
    def _is_reprompt_phrase(normalized_text: str) -> bool:
        return any(
            phrase in normalized_text
            for phrase in (
                "can you tell me more",
                "could you tell me more",
                "can you elaborate",
                "could you elaborate",
                "can you give me an example",
                "could you give me an example",
                "could you clarify",
                "can you clarify",
            )
        )

    @staticmethod
    def _is_clarification_phrase(normalized_text: str) -> bool:
        return any(
            phrase in normalized_text
            for phrase in (
                "could you repeat",
                "can you repeat",
                "say that again",
                "didn't catch that",
                "did not catch that",
                "didn't hear that",
                "did not hear that",
                "pardon",
                "sorry, what",
            )
        )

    def _match_template(
        self,
        assistant_text: str,
        category: PromptCategory,
    ) -> str | None:
        normalized = self._normalize_for_matching(assistant_text)
        if category == PromptCategory.OPENER:
            return "opener_consent"
        if category == PromptCategory.REPROMPT:
            if "example" in normalized:
                return "reprompt_example"
            if "clarify" in normalized:
                return "reprompt_clarify"
            return "reprompt_elaborate"
        if category == PromptCategory.CLARIFICATION:
            if "tell me more" in normalized:
                return "clarification_more"
            return "clarification_repeat"
        if category == PromptCategory.CLOSING:
            if "we'll be in touch" in normalized or "we will be in touch" in normalized:
                return "closing_next_steps"
            return "closing_thank_you"
        return None

    def _match_question(
        self,
        assistant_text: str,
        questions: list[InterviewQuestion],
    ) -> InterviewQuestion | None:
        normalized_assistant = self._normalize_for_matching(assistant_text).rstrip(".?!")
        for question in questions:
            normalized_question = self._normalize_for_matching(question.question_text).rstrip(".?!")
            if normalized_assistant == normalized_question:
                return question
        return None

    async def select_audio_source(
        self,
        *,
        assistant_text: str,
        conversation_state: "ConversationState",
        job_id: UUID | None = None,
        questions: list[InterviewQuestion] | None = None,
        current_question_id: UUID | None = None,
    ) -> AudioSourceSelection:
        category = self._classify_turn(
            assistant_text,
            conversation_state,
            questions=questions,
        )
        template_key = self._match_template(assistant_text, category)
        matched_question: InterviewQuestion | None = None
        if category == PromptCategory.QUESTION:
            if current_question_id and questions:
                matched_question = next((q for q in questions if q.id == current_question_id), None)
            if matched_question is None and questions:
                matched_question = self._match_question(assistant_text, questions)
            if matched_question is not None:
                template_key = f"question_{matched_question.id}"

        if not template_key:
            return AudioSourceSelection(
                source_type="live_tts",
                template_key=None,
                asset=None,
                fallback_text=assistant_text,
                filler_key=None,
            )

        asset = await self.prompt_audio.get_ready_audio_asset(
            template_key=template_key,
            job_id=job_id if category == PromptCategory.QUESTION else None,
            question_id=matched_question.id if matched_question else None,
        )
        if asset and matched_question and asset.text != matched_question.question_text:
            asset = None

        if category == PromptCategory.OPENER:
            normalized_text = self._normalize_for_matching(assistant_text)
            if normalized_text != self._normalize_for_matching(DEFAULT_OPENER_TEXT):
                return AudioSourceSelection(
                    source_type="live_tts_fallback",
                    template_key=template_key,
                    asset=None,
                    fallback_text=assistant_text,
                    filler_key=None,
                )

        if asset:
            return AudioSourceSelection(
                source_type="prebuilt_asset",
                template_key=template_key,
                asset=asset,
                fallback_text=None,
                filler_key=None,
            )

        source_type = "live_tts_fallback" if category != PromptCategory.FALLBACK_DYNAMIC else "live_tts"
        return AudioSourceSelection(
            source_type=source_type,
            template_key=template_key,
            asset=None,
            fallback_text=assistant_text,
            filler_key=None,
        )
