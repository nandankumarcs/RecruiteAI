"""TTS and audio source resolution for call v2."""

from app.call_v2.tts.base import TtsAudio, TtsEngine, TtsRequest
from app.call_v2.tts.cache import AudioCacheKey, InMemoryAudioCache
from app.call_v2.tts.eligibility import CacheCategory, CacheDecision, CachePolicy
from app.call_v2.tts.openai import OpenAITtsEngine
from app.call_v2.tts.providers import FakeTtsEngine
from app.call_v2.tts.resolver import AudioPlaybackPlan, AudioSourceResolver

__all__ = [
    "AudioCacheKey",
    "AudioPlaybackPlan",
    "AudioSourceResolver",
    "CacheCategory",
    "CacheDecision",
    "CachePolicy",
    "FakeTtsEngine",
    "InMemoryAudioCache",
    "OpenAITtsEngine",
    "TtsAudio",
    "TtsEngine",
    "TtsRequest",
]
