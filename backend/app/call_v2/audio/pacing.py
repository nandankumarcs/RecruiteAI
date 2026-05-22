"""Audio chunking and pacing helpers for call v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from app.call_v2.audio.formats import frame_size_bytes
from app.call_v2.events import AudioFormat


@dataclass(frozen=True, slots=True)
class AudioFramePlan:
    audio_format: AudioFormat
    frame_duration_ms: int = 20

    @property
    def chunk_size_bytes(self) -> int:
        return frame_size_bytes(self.audio_format, self.frame_duration_ms)

    @property
    def sleep_seconds(self) -> float:
        return self.frame_duration_ms / 1000.0


def iter_audio_frames(
    payload: bytes,
    *,
    audio_format: AudioFormat,
    frame_duration_ms: int = 20,
    pad_final_frame: bool = False,
) -> Iterator[bytes]:
    """Yield fixed-duration audio frames for paced telephony playback."""

    chunk_size = frame_size_bytes(audio_format, frame_duration_ms)
    if chunk_size <= 0:
        raise ValueError("audio frame size must be positive")

    for offset in range(0, len(payload), chunk_size):
        chunk = payload[offset : offset + chunk_size]
        if not chunk:
            continue
        if pad_final_frame and len(chunk) < chunk_size:
            chunk = chunk + (b"\x00" * (chunk_size - len(chunk)))
        yield chunk
