"""Codec conversion helpers for call v2 audio boundaries."""

from __future__ import annotations

try:
    import audioop
except ImportError:  # pragma: no cover - Python 3.13+ fallback in requirements
    import audioop_lts as audioop  # type: ignore

from app.call_v2.events import AudioFormat


def mulaw_to_linear16(payload: bytes, *, sample_width: int = 2) -> bytes:
    """Convert 8-bit mu-law bytes to signed 16-bit linear PCM."""

    return audioop.ulaw2lin(payload, sample_width)


def linear16_to_mulaw(payload: bytes, *, sample_width: int = 2) -> bytes:
    """Convert signed 16-bit linear PCM bytes to 8-bit mu-law."""

    if len(payload) % sample_width:
        raise ValueError("linear16 payload length must align to 16-bit samples")
    return audioop.lin2ulaw(payload, sample_width)


def convert_audio(
    payload: bytes,
    *,
    source_format: AudioFormat,
    target_format: AudioFormat,
) -> bytes:
    """Convert audio between supported raw telephony formats."""

    if source_format.is_compatible_with(target_format):
        return payload
    if source_format.sample_rate_hz != target_format.sample_rate_hz:
        raise ValueError("sample-rate conversion is not supported")
    if source_format.channels != target_format.channels:
        raise ValueError("channel conversion is not supported")
    if source_format.container != target_format.container:
        raise ValueError("container conversion is not supported")

    if source_format.codec == "mulaw" and target_format.codec == "linear16":
        return mulaw_to_linear16(payload)
    if source_format.codec == "linear16" and target_format.codec == "mulaw":
        return linear16_to_mulaw(payload)

    raise ValueError(
        f"unsupported codec conversion: {source_format.codec} -> {target_format.codec}"
    )

