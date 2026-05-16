"""Server-side recorder for browser-telephony simulator calls.

Captures both directions of a simulator call to a stereo WAV:
  - channel 0 (left)  = inbound, the candidate's microphone audio
  - channel 1 (right) = outbound, the AI's TTS audio

The recorder is fed via :class:`RecordingWebSocket`, a transparent proxy that
sits between FastAPI's ``WebSocket`` and the existing realtime bridge. The
bridge is untouched — it sees a normal WebSocket and only the methods that
carry audio (``receive_text`` for inbound and ``send_json`` for outbound) are
tapped for recording.

Time alignment uses wall-clock offsets from the first frame: when a frame
arrives at time ``t``, the corresponding channel buffer is padded with silence
up to ``t`` before the frame bytes are appended. This handles either side
being silent or both sides talking simultaneously without per-frame timestamps.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
import uuid
import wave

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# All wire audio on this provider is L16 8kHz mono — matches Exotel.
SAMPLE_RATE = 8000
SAMPLE_WIDTH = 2  # bytes per L16 sample
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH
# Safety cap so a runaway call can't exhaust disk. 30 min × 8 kHz × 2 B = ~28.8 MB per channel.
MAX_RECORDING_SECONDS = 60 * 30


class SimulatorCallRecorder:
    """Accumulates inbound + outbound L16 audio per call; emits a stereo WAV on demand."""

    def __init__(self, call_id: uuid.UUID):
        self.call_id = call_id
        self._start_ts: float | None = None
        self._inbound = bytearray()
        self._outbound = bytearray()
        self._overflow_logged = False

    def _now_offset_bytes(self) -> int:
        if self._start_ts is None:
            self._start_ts = time.monotonic()
            return 0
        elapsed = time.monotonic() - self._start_ts
        # Round down to an even byte (sample) boundary so we never split a sample.
        return (int(elapsed * BYTES_PER_SECOND) // 2) * 2

    def _append(self, buf: bytearray, l16: bytes) -> None:
        cap = MAX_RECORDING_SECONDS * BYTES_PER_SECOND
        if len(buf) >= cap:
            if not self._overflow_logged:
                logger.warning(
                    "Simulator recording exceeded %ds cap (call=%s); dropping further frames",
                    MAX_RECORDING_SECONDS,
                    self.call_id,
                )
                self._overflow_logged = True
            return
        target = self._now_offset_bytes()
        if len(buf) < target:
            buf.extend(b"\x00" * (target - len(buf)))
        buf.extend(l16)

    def add_inbound(self, l16: bytes) -> None:
        self._append(self._inbound, l16)

    def add_outbound(self, l16: bytes) -> None:
        self._append(self._outbound, l16)

    def is_empty(self) -> bool:
        return len(self._inbound) == 0 and len(self._outbound) == 0

    def to_wav_bytes(self) -> bytes:
        """Materialize the accumulated buffers as a stereo 8 kHz PCM16 WAV."""
        # Align both channels to the same length so interleaving works cleanly.
        max_len = max(len(self._inbound), len(self._outbound), 2)
        if max_len % 2:
            max_len += 1  # keep even-byte alignment
        if len(self._inbound) < max_len:
            self._inbound.extend(b"\x00" * (max_len - len(self._inbound)))
        if len(self._outbound) < max_len:
            self._outbound.extend(b"\x00" * (max_len - len(self._outbound)))

        sample_count = max_len // 2
        interleaved = bytearray(max_len * 2)
        for i in range(sample_count):
            src = i * 2
            dst = i * 4
            interleaved[dst:dst + 2] = self._inbound[src:src + 2]
            interleaved[dst + 2:dst + 4] = self._outbound[src:src + 2]

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(bytes(interleaved))
        return buf.getvalue()


class RecordingWebSocket:
    """Transparent proxy over a FastAPI ``WebSocket`` that records media frames.

    Delegates everything via ``__getattr__`` except the methods that carry audio:
    ``receive_text`` / ``receive_json`` (client → server media, inbound) and
    ``send_json`` (server → client media, outbound). Any exception inside the
    recording tap is swallowed so the call path is never broken by recording.
    """

    def __init__(self, ws: WebSocket, recorder: SimulatorCallRecorder):
        self._ws = ws
        self._recorder = recorder

    def __getattr__(self, name: str):
        return getattr(self._ws, name)

    async def receive_text(self) -> str:
        text = await self._ws.receive_text()
        try:
            data = json.loads(text)
            if isinstance(data, dict) and data.get("event") == "media":
                payload = (data.get("media") or {}).get("payload")
                if payload:
                    self._recorder.add_inbound(base64.b64decode(payload))
        except Exception:
            pass
        return text

    async def receive_json(self) -> dict:
        data = await self._ws.receive_json()
        try:
            if isinstance(data, dict) and data.get("event") == "media":
                payload = (data.get("media") or {}).get("payload")
                if payload:
                    self._recorder.add_inbound(base64.b64decode(payload))
        except Exception:
            pass
        return data

    async def send_json(self, data, *args, **kwargs) -> None:
        try:
            if isinstance(data, dict) and data.get("event") == "media":
                payload = (data.get("media") or {}).get("payload")
                if payload:
                    self._recorder.add_outbound(base64.b64decode(payload))
        except Exception:
            pass
        await self._ws.send_json(data, *args, **kwargs)
