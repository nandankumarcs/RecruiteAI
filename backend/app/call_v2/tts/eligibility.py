"""Explicit cache eligibility policy for call v2 audio resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CacheCategory = Literal[
    "consent_opener",
    "known_question",
    "standard_goodbye",
    "technical_recovery",
    "neutral_filler",
    "standard_transition",
    "sentence_audio",          # any sentence synthesised via chunk streaming
    "question_explanation",
    "clarification_response",
    "candidate_specific_followup",
    "objection_handling",
    "conversation_summary",
    "answer_reflection",
    "tool_result_response",
    "conversation_turn",
    "unknown",
]


CACHEABLE_CATEGORIES = frozenset(
    {
        "consent_opener",
        "known_question",
        "standard_goodbye",
        "technical_recovery",
        "neutral_filler",
        "standard_transition",
        "sentence_audio",      # text-hash keyed → different text = different key, safe to cache
    }
)

NON_CACHEABLE_CATEGORIES = frozenset(
    {
        "question_explanation",
        "clarification_response",
        "candidate_specific_followup",
        "objection_handling",
        "conversation_summary",
        "answer_reflection",
        "tool_result_response",
        "unknown",
    }
)


@dataclass(frozen=True, slots=True)
class CachePolicy:
    category: CacheCategory = "unknown"
    variant_id: str | None = None
    contains_candidate_data: bool = False
    allow_lookup: bool = True
    allow_persistent_store: bool = False


@dataclass(frozen=True, slots=True)
class CacheDecision:
    category: str
    lookup_allowed: bool
    persistent_store_allowed: bool
    reason: str


def decide_cache(policy: CachePolicy) -> CacheDecision:
    if policy.contains_candidate_data:
        return CacheDecision(
            category=policy.category,
            lookup_allowed=False,
            persistent_store_allowed=False,
            reason="candidate_specific_data",
        )
    if not policy.allow_lookup:
        return CacheDecision(
            category=policy.category,
            lookup_allowed=False,
            persistent_store_allowed=False,
            reason="lookup_disabled",
        )
    if policy.category in NON_CACHEABLE_CATEGORIES:
        return CacheDecision(
            category=policy.category,
            lookup_allowed=False,
            persistent_store_allowed=False,
            reason="non_cacheable_category",
        )
    if policy.category not in CACHEABLE_CATEGORIES:
        return CacheDecision(
            category=policy.category,
            lookup_allowed=False,
            persistent_store_allowed=False,
            reason="unapproved_category",
        )
    return CacheDecision(
        category=policy.category,
        lookup_allowed=True,
        persistent_store_allowed=policy.allow_persistent_store,
        reason="approved_exact_audio_category",
    )
