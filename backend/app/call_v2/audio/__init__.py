"""Audio boundary helpers for call v2."""

from app.call_v2.audio.codecs import convert_audio, linear16_to_mulaw, mulaw_to_linear16
from app.call_v2.audio.formats import (
    LINEAR16_8K_MONO,
    MULAW_8K_MONO,
    bytes_per_sample,
    bytes_per_second,
    frame_size_bytes,
    provider_audio_format,
    validate_audio_payload,
)
from app.call_v2.audio.pacing import AudioFramePlan, iter_audio_frames
from app.call_v2.audio.wav import linear16_to_wav_bytes, wav_bytes_to_linear16

__all__ = [
    "AudioFramePlan",
    "LINEAR16_8K_MONO",
    "MULAW_8K_MONO",
    "bytes_per_sample",
    "bytes_per_second",
    "convert_audio",
    "frame_size_bytes",
    "iter_audio_frames",
    "linear16_to_mulaw",
    "linear16_to_wav_bytes",
    "mulaw_to_linear16",
    "provider_audio_format",
    "validate_audio_payload",
    "wav_bytes_to_linear16",
]
