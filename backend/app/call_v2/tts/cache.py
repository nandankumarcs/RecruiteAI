"""Exact audio cache primitives for call v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any

from app.call_v2.events import AudioFormat


CACHE_SCHEMA_VERSION = "audio-cache.v1"


@dataclass(frozen=True, slots=True)
class AudioCacheKey:
    normalized_text_hash: str
    category: str
    tts_provider: str
    tts_model: str
    voice: str
    language: str
    speaking_style: str | None
    codec: str
    sample_rate_hz: int
    channels: int
    telephony_provider: str
    variant_id: str | None
    cache_schema_version: str = CACHE_SCHEMA_VERSION

    def stable_key(self) -> str:
        values = [
            self.cache_schema_version,
            self.category,
            self.normalized_text_hash,
            self.tts_provider,
            self.tts_model,
            self.voice,
            self.language,
            self.speaking_style or "",
            self.codec,
            str(self.sample_rate_hz),
            str(self.channels),
            self.telephony_provider,
            self.variant_id or "",
        ]
        return "|".join(values)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CachedAudio:
    payload: bytes
    audio_format: AudioFormat
    key: AudioCacheKey


class InMemoryAudioCache:
    """Process-local exact audio cache used by tests and simulator wiring."""

    def __init__(self) -> None:
        self._items: dict[str, CachedAudio] = {}

    def get(self, key: AudioCacheKey) -> CachedAudio | None:
        item = self._items.get(key.stable_key())
        if item is None:
            return None
        if not item.audio_format.is_compatible_with(_format_from_key(key)):
            return None
        return item

    def put(
        self,
        key: AudioCacheKey,
        *,
        payload: bytes,
        audio_format: AudioFormat,
    ) -> None:
        if not audio_format.is_compatible_with(_format_from_key(key)):
            raise ValueError("cached audio format must match cache key")
        self._items[key.stable_key()] = CachedAudio(
            payload=payload,
            audio_format=audio_format,
            key=key,
        )

    def __len__(self) -> int:
        return len(self._items)


def build_audio_cache_key(
    *,
    text: str,
    category: str,
    tts_provider: str,
    tts_model: str,
    voice: str,
    language: str,
    speaking_style: str | None,
    audio_format: AudioFormat,
    telephony_provider: str,
    variant_id: str | None = None,
) -> AudioCacheKey:
    return AudioCacheKey(
        normalized_text_hash=text_fingerprint(text),
        category=category,
        tts_provider=tts_provider,
        tts_model=tts_model,
        voice=voice,
        language=language,
        speaking_style=speaking_style,
        codec=audio_format.codec,
        sample_rate_hz=audio_format.sample_rate_hz,
        channels=audio_format.channels,
        telephony_provider=telephony_provider,
        variant_id=variant_id,
    )


def normalize_tts_text(text: str) -> str:
    return " ".join((text or "").replace("\u2018", "'").replace("\u2019", "'").split())


def text_fingerprint(text: str) -> str:
    return sha256(normalize_tts_text(text).encode("utf-8")).hexdigest()


def _format_from_key(key: AudioCacheKey) -> AudioFormat:
    return AudioFormat(
        codec=key.codec,  # type: ignore[arg-type]
        sample_rate_hz=key.sample_rate_hz,
        channels=key.channels,
    )
