"""Audio format helpers for call v2."""

from __future__ import annotations

from app.call_v2.events import AudioFormat

LINEAR16_8K_MONO = AudioFormat(codec="linear16", sample_rate_hz=8000, channels=1)
MULAW_8K_MONO = AudioFormat(codec="mulaw", sample_rate_hz=8000, channels=1)
L16_PROVIDERS = frozenset({"browser", "exotel"})
MULAW_PROVIDERS = frozenset({"twilio"})


def provider_audio_format(provider: str) -> AudioFormat:
    """Return the raw wire audio format expected by a telephony provider."""

    normalized = provider.strip().lower()
    if normalized in L16_PROVIDERS:
        return LINEAR16_8K_MONO
    if normalized in MULAW_PROVIDERS:
        return MULAW_8K_MONO
    raise ValueError(f"unsupported telephony provider for audio format: {provider}")


def bytes_per_sample(audio_format: AudioFormat) -> int:
    if audio_format.codec == "linear16":
        return 2
    if audio_format.codec == "mulaw":
        return 1
    raise ValueError(f"unsupported audio codec: {audio_format.codec}")


def bytes_per_second(audio_format: AudioFormat) -> int:
    return (
        audio_format.sample_rate_hz
        * audio_format.channels
        * bytes_per_sample(audio_format)
    )


def frame_size_bytes(audio_format: AudioFormat, frame_duration_ms: int = 20) -> int:
    if frame_duration_ms <= 0:
        raise ValueError("frame duration must be positive")
    size = bytes_per_second(audio_format) * frame_duration_ms // 1000
    sample_size = bytes_per_sample(audio_format) * audio_format.channels
    return (size // sample_size) * sample_size


def validate_audio_payload(payload: bytes, audio_format: AudioFormat) -> None:
    sample_size = bytes_per_sample(audio_format) * audio_format.channels
    if len(payload) % sample_size:
        raise ValueError(
            f"{audio_format.codec} payload length must align to {sample_size}-byte samples"
        )
