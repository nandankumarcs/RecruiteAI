"""Phase 7 tests for call v2 TTS and audio source resolution."""

import pytest

from app.call_v2.audio.formats import LINEAR16_8K_MONO, MULAW_8K_MONO
from app.call_v2.events import CallIdentity
from app.call_v2.ids import GenerationIdManager
from app.call_v2.tts.cache import InMemoryAudioCache, build_audio_cache_key
from app.call_v2.tts.eligibility import CachePolicy
from app.call_v2.tts.providers import FakeTtsEngine, TtsProviderError
from app.call_v2.tts.resolver import AudioSourceResolver


def _confirmed_ids(generation_id: int = 1) -> GenerationIdManager:
    ids = GenerationIdManager()
    started = ids.start_generation()
    assert started == generation_id
    ids.mark_confirmed(generation_id)
    return ids


def _identity() -> CallIdentity:
    return CallIdentity(provider="browser", stream_id="stream-1")


def _question_policy(*, store: bool = False) -> CachePolicy:
    return CachePolicy(
        category="known_question",
        variant_id="q1",
        allow_persistent_store=store,
    )


def _cache_key(
    *,
    text: str,
    audio_format=LINEAR16_8K_MONO,
    voice: str = "test",
    telephony_provider: str = "browser",
):
    return build_audio_cache_key(
        text=text,
        category="known_question",
        tts_provider="fake",
        tts_model="fake-tts",
        voice=voice,
        language="en",
        speaking_style=None,
        audio_format=audio_format,
        telephony_provider=telephony_provider,
        variant_id="q1",
    )


@pytest.mark.asyncio
async def test_known_question_exact_cache_hit_uses_cached_audio():
    cache = InMemoryAudioCache()
    text = "Tell me about a backend project you owned."
    cached_payload = b"\x01\x02" * 160
    cache.put(
        _cache_key(text=text),
        payload=cached_payload,
        audio_format=LINEAR16_8K_MONO,
    )
    primary = FakeTtsEngine(payload=b"\x09\x09" * 160)
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text=text,
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=_question_policy(),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "cache"
    assert plan.source_event.decision_reason == "approved_exact_audio_category"
    assert plan.audio.payload == cached_payload
    assert primary.requests == []
    assert len(plan.frames) == 1
    assert plan.frames[0].is_first_frame is True
    assert plan.frames[0].is_final_frame is True


@pytest.mark.asyncio
async def test_same_text_with_wrong_codec_misses_cache_and_uses_live_tts():
    cache = InMemoryAudioCache()
    text = "Tell me about a backend project you owned."
    cache.put(
        _cache_key(text=text, audio_format=MULAW_8K_MONO, telephony_provider="twilio"),
        payload=b"\xff" * 160,
        audio_format=MULAW_8K_MONO,
    )
    primary = FakeTtsEngine(payload=b"\x00\x01" * 160)
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text=text,
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=_question_policy(),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "live_tts"
    assert len(primary.requests) == 1
    assert primary.requests[0].output_format == LINEAR16_8K_MONO


@pytest.mark.asyncio
async def test_cache_miss_live_tts_can_store_only_when_policy_allows():
    cache = InMemoryAudioCache()
    text = "Tell me about a backend project you owned."
    primary = FakeTtsEngine(payload=b"\x00\x01" * 160)
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text=text,
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=_question_policy(store=True),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "live_tts"
    assert len(cache) == 1


@pytest.mark.asyncio
async def test_candidate_specific_text_is_not_persistently_cached():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine(payload=b"\x00\x01" * 160)
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text="Thanks Asha, your FastAPI project sounds relevant.",
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=CachePolicy(
            category="candidate_specific_followup",
            contains_candidate_data=True,
            allow_persistent_store=True,
        ),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "live_tts"
    assert plan.source_event.decision_reason == "candidate_specific_data"
    assert plan.source_event.cache_key is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_question_explanation_uses_live_tts_by_default():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine(payload=b"\x00\x01" * 160)
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text="I mean a project where you owned design or delivery.",
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=CachePolicy(category="question_explanation"),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "live_tts"
    assert plan.source_event.cache_category == "question_explanation"
    assert plan.source_event.decision_reason == "non_cacheable_category"
    assert plan.source_event.cache_key is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_live_tts_failure_uses_fallback_provider():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine(provider="primary", fail=True)
    fallback = FakeTtsEngine(provider="fallback", payload=b"\x03\x04" * 160)
    resolver = AudioSourceResolver(
        cache=cache,
        primary_tts=primary,
        fallback_tts=fallback,
    )

    plan = await resolver.resolve(
        generation_id=1,
        spoken_text="Thanks. Please continue.",
        identity=_identity(),
        output_format=LINEAR16_8K_MONO,
        telephony_provider="browser",
        cache_policy=CachePolicy(category="clarification_response"),
        generation_ids=_confirmed_ids(),
        now_ms=100,
    )

    assert plan.source_event.source == "fallback_tts"
    assert plan.audio.provider == "fallback"
    assert len(primary.requests) == 1
    assert len(fallback.requests) == 1


@pytest.mark.asyncio
async def test_cancelled_tts_generation_does_not_synthesize_audio():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine()
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)
    resolver.cancel(1)

    with pytest.raises(TtsProviderError, match="cancelled"):
        await resolver.resolve(
            generation_id=1,
            spoken_text="Thanks. Please continue.",
            identity=_identity(),
            output_format=LINEAR16_8K_MONO,
            telephony_provider="browser",
            cache_policy=CachePolicy(category="clarification_response"),
            generation_ids=_confirmed_ids(),
            now_ms=100,
        )


@pytest.mark.asyncio
async def test_speculative_or_stale_generation_cannot_trigger_playback():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine()
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    with pytest.raises(ValueError, match="not confirmed"):
        await resolver.resolve(
            generation_id=1,
            spoken_text="This should not speak yet.",
            identity=_identity(),
            output_format=LINEAR16_8K_MONO,
            telephony_provider="browser",
            cache_policy=CachePolicy(category="known_question"),
            generation_ids=GenerationIdManager(),
            now_ms=100,
        )

    assert primary.requests == []


@pytest.mark.asyncio
async def test_empty_tts_audio_is_rejected_before_playback_frames():
    cache = InMemoryAudioCache()
    primary = FakeTtsEngine(payload=b"")
    resolver = AudioSourceResolver(cache=cache, primary_tts=primary)

    with pytest.raises(ValueError, match="must not be empty"):
        await resolver.resolve(
            generation_id=1,
            spoken_text="Thanks. Please continue.",
            identity=_identity(),
            output_format=LINEAR16_8K_MONO,
            telephony_provider="browser",
            cache_policy=CachePolicy(category="clarification_response"),
            generation_ids=_confirmed_ids(),
            now_ms=100,
        )
