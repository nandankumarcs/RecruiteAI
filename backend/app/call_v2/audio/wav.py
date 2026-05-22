"""WAV container helpers for provider-backed simulator audio."""

from __future__ import annotations

import io
import wave

try:
    import audioop
except ImportError:  # pragma: no cover - Python 3.13+ fallback in requirements
    import audioop_lts as audioop  # type: ignore

from app.call_v2.audio.formats import validate_audio_payload
from app.call_v2.events import AudioFormat


def linear16_to_wav_bytes(payload: bytes, *, audio_format: AudioFormat) -> bytes:
    """Wrap raw linear16 PCM in a WAV container."""

    if audio_format.codec != "linear16":
        raise ValueError("only linear16 audio can be wrapped as WAV")
    validate_audio_payload(payload, audio_format)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(audio_format.channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(audio_format.sample_rate_hz)
        wav_file.writeframes(payload)
    return buffer.getvalue()


def wav_bytes_to_linear16(
    wav_payload: bytes,
    *,
    target_format: AudioFormat,
) -> bytes:
    """Decode WAV bytes to raw linear16 PCM in the target mono sample rate."""

    if target_format.codec != "linear16":
        raise ValueError("WAV decoding currently supports only linear16 output")

    with wave.open(io.BytesIO(wav_payload), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        source_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2

    if channels != target_format.channels:
        if channels == 2 and target_format.channels == 1:
            frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        else:
            raise ValueError(
                f"unsupported WAV channel conversion: {channels} -> "
                f"{target_format.channels}"
            )

    if source_rate != target_format.sample_rate_hz:
        frames, _state = audioop.ratecv(
            frames,
            sample_width,
            target_format.channels,
            source_rate,
            target_format.sample_rate_hz,
            None,
        )

    validate_audio_payload(frames, target_format)
    return frames
