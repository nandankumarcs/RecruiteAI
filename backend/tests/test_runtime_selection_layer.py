"""
Tests for RuntimeSelectionLayer data structures and matching behavior.
"""

from uuid import uuid4

from app.services.runtime_selection_layer import (
    PromptCategory,
    AudioSourceSelection,
    RuntimeSelectionLayer,
)
from app.models.question import InterviewQuestion


class TestPromptCategory:
    """Test PromptCategory enum."""

    def test_all_categories_defined(self):
        """Verify all required prompt categories are defined."""
        expected_categories = {
            "OPENER",
            "QUESTION",
            "REPROMPT",
            "CLARIFICATION",
            "OFF_TOPIC_REDIRECT",
            "CLOSING",
            "FILLER",
            "FALLBACK_DYNAMIC",
        }
        actual_categories = {cat.name for cat in PromptCategory}
        assert actual_categories == expected_categories

    def test_category_values(self):
        """Verify category enum values match expected string values."""
        assert PromptCategory.OPENER.value == "opener"
        assert PromptCategory.QUESTION.value == "question"
        assert PromptCategory.REPROMPT.value == "reprompt"
        assert PromptCategory.CLARIFICATION.value == "clarification"
        assert PromptCategory.OFF_TOPIC_REDIRECT.value == "off_topic_redirect"
        assert PromptCategory.CLOSING.value == "closing"
        assert PromptCategory.FILLER.value == "filler"
        assert PromptCategory.FALLBACK_DYNAMIC.value == "fallback_dynamic"

    def test_category_string_comparison(self):
        """Verify enum can be compared with strings."""
        assert PromptCategory.OPENER == "opener"
        assert PromptCategory.QUESTION == "question"


class TestAudioSourceSelection:
    """Test AudioSourceSelection dataclass."""

    def test_create_with_prebuilt_asset(self):
        """Test creating selection for prebuilt asset."""
        selection = AudioSourceSelection(
            source_type="prebuilt_asset",
            template_key="opener_consent",
            asset=None,  # Would be AudioPromptAsset instance in real usage
            fallback_text=None,
            filler_key=None,
        )
        assert selection.source_type == "prebuilt_asset"
        assert selection.template_key == "opener_consent"
        assert selection.asset is None
        assert selection.fallback_text is None
        assert selection.filler_key is None


class DummyPromptAudioService:
    async def get_ready_audio_asset(self, **kwargs):
        return None


class DummyFillerQueueManager:
    pass


def test_runtime_selection_matches_question_with_abbreviation_variation():
    layer = RuntimeSelectionLayer(DummyPromptAudioService(), DummyFillerQueueManager())
    question = InterviewQuestion(
        id=uuid4(),
        job_id=uuid4(),
        question_text="Can you explain the basic concepts of Object-Oriented Programming and how they apply to Python?",
        order_index=1,
    )

    matched = layer._match_question(
        "Can you explain the basic concepts of Object-Oriented Programming (OOP) and how they apply to Python?",
        [question],
    )

    assert matched is not None
    assert matched.id == question.id


def test_runtime_selection_maps_common_follow_up_variants_to_cached_templates():
    layer = RuntimeSelectionLayer(DummyPromptAudioService(), DummyFillerQueueManager())

    assert (
        layer._match_template(
            "Could you please elaborate on those five concepts in OOP?",
            PromptCategory.REPROMPT,
        )
        == "reprompt_elaborate"
    )
    assert (
        layer._match_template(
            "Can you explain each of those five concepts in detail?",
            PromptCategory.REPROMPT,
        )
        == "reprompt_detail"
    )

    def test_create_with_live_tts_fallback(self):
        """Test creating selection for live TTS fallback."""
        selection = AudioSourceSelection(
            source_type="live_tts_fallback",
            template_key="reprompt_clarify",
            asset=None,
            fallback_text="Could you clarify that?",
            filler_key=None,
        )
        assert selection.source_type == "live_tts_fallback"
        assert selection.template_key == "reprompt_clarify"
        assert selection.fallback_text == "Could you clarify that?"

    def test_create_with_filler(self):
        """Test creating selection for filler audio."""
        selection = AudioSourceSelection(
            source_type="filler_asset",
            template_key=None,
            asset=None,
            fallback_text=None,
            filler_key="filler_understood",
        )
        assert selection.source_type == "filler_asset"
        assert selection.filler_key == "filler_understood"

    def test_all_fields_optional_except_source_type(self):
        """Test that all fields except source_type can be None."""
        selection = AudioSourceSelection(
            source_type="live_tts",
            template_key=None,
            asset=None,
            fallback_text=None,
            filler_key=None,
        )
        assert selection.source_type == "live_tts"
        assert selection.template_key is None
        assert selection.asset is None
        assert selection.fallback_text is None
        assert selection.filler_key is None
