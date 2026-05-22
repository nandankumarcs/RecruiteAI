"""Sarvam TTS engine adapter for call v2.

Wraps Sarvam's HTTP streaming API in the v2 TtsEngine protocol.
Audio is collected in full before returning — the v2 pipeline chunks it
into 20 ms frames and paces it internally, so there is no benefit in
yielding individual Sarvam HTTP chunks here.

Transport selection (HTTP vs WebSocket) follows SARVAM_TTS_TRANSPORT config.
The WebSocket path reuses a persistent connection across turns and has
lower first-byte latency on the second+ turn.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
import websockets

from app.call_v2.tts.base import TtsAudio, TtsRequest
from app.call_v2.tts.providers import TtsProviderError
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SarvamTtsEngine:
    """v2 TtsEngine backed by the Sarvam AI speech synthesis API."""

    api_key: str
    provider: str = "sarvam"
    model: str = "bulbul:v3"
    voice: str = "priya"
    language: str = "en-IN"
    speaking_style: str | None = None
    sample_rate: int = 8000
    codec: str = "linear16"
    pace: float = 1.2
    transport: str = "http"
    ws_url: str = "wss://api.sarvam.ai/text-to-speech/ws"
    first_byte_timeout: float = 2.0
    completion_timeout: float = 15.0
    cancelled_generation_ids: set[int] = field(default_factory=set)

    # WebSocket state — shared across turns on the same engine instance.
    _ws: object = field(default=None, init=False, repr=False)
    _ws_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock, init=False, repr=False
    )

    async def synthesize(self, request: TtsRequest) -> TtsAudio:
        if request.generation_id in self.cancelled_generation_ids:
            raise TtsProviderError(
                f"Sarvam TTS generation {request.generation_id} was cancelled"
            )
        if not self.api_key:
            raise TtsProviderError("SARVAM_API_KEY is not configured")

        run_id = str(uuid.uuid4())[:8]
        logger.debug(
            "sarvam.tts.start gen=%d run=%s text_len=%d transport=%s",
            request.generation_id,
            run_id,
            len(request.text),
            self.transport,
        )

        try:
            if self.transport == "websocket":
                payload = await self._synthesize_ws(request.text, run_id)
            else:
                payload = await self._synthesize_http(request.text, run_id)
        except TtsProviderError:
            raise
        except Exception as exc:
            raise TtsProviderError(f"Sarvam TTS failed: {exc}") from exc

        if not payload:
            raise TtsProviderError("Sarvam TTS returned empty audio")

        logger.debug(
            "sarvam.tts.complete gen=%d run=%s bytes=%d",
            request.generation_id,
            run_id,
            len(payload),
        )
        return TtsAudio(
            payload=payload,
            audio_format=request.output_format,
            provider=self.provider,
            model=self.model,
            voice=self.voice,
            language=self.language,
            speaking_style=self.speaking_style,
        )

    def cancel(self, generation_id: int) -> None:
        self.cancelled_generation_ids.add(generation_id)

    # ------------------------------------------------------------------
    # HTTP streaming
    # ------------------------------------------------------------------

    async def synthesize_chunked(
        self, request: TtsRequest
    ):
        """Yield raw L16 PCM bytes as they arrive from Sarvam's HTTP stream.

        Callers should assemble these into fixed-duration frames themselves.
        This allows audio playback to start with the very first chunk rather
        than waiting for the full sentence to be synthesised.
        """
        if request.generation_id in self.cancelled_generation_ids:
            raise TtsProviderError(
                f"Sarvam TTS generation {request.generation_id} was cancelled"
            )
        if not self.api_key:
            raise TtsProviderError("SARVAM_API_KEY is not configured")
        run_id = str(uuid.uuid4())[:8]
        logger.debug(
            "sarvam.tts.chunked_start gen=%d run=%s text_len=%d",
            request.generation_id, run_id, len(request.text),
        )
        async for chunk in self._http_chunks(request.text, run_id):
            if request.generation_id in self.cancelled_generation_ids:
                return
            yield chunk

    async def _synthesize_http(self, text: str, run_id: str) -> bytes:
        chunks: list[bytes] = []
        async for chunk in self._http_chunks(text, run_id):
            chunks.append(chunk)
        return b"".join(chunks)

    async def _http_chunks(self, text: str, run_id: str):
        """Async generator: yield raw PCM bytes as the Sarvam HTTP stream delivers them."""
        url = "https://api.sarvam.ai/text-to-speech/stream"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        body = {
            "text": text,
            "target_language_code": self.language,
            "speaker": self.voice,
            "model": self.model,
            "speech_sample_rate": self.sample_rate,
            "output_audio_codec": self.codec,
            "pace": self.pace,
        }

        chunk_count = 0
        try:
            async with httpx.AsyncClient(timeout=self.completion_timeout) as client:
                async with client.stream("POST", url, headers=headers, json=body) as resp:
                    if resp.status_code != 200:
                        err = await resp.aread()
                        raise TtsProviderError(
                            f"Sarvam HTTP {resp.status_code}: {err[:200]}"
                        )
                    async for chunk in resp.aiter_bytes():
                        if not chunk:
                            continue
                        if chunk_count == 0:
                            logger.debug(
                                "sarvam.tts.first_chunk run=%s bytes=%d",
                                run_id, len(chunk),
                            )
                        chunk_count += 1
                        yield chunk
        except httpx.TimeoutException as exc:
            raise TtsProviderError(f"Sarvam HTTP timeout: {exc}") from exc

    # ------------------------------------------------------------------
    # WebSocket streaming (persistent connection, lower first-byte latency)
    # ------------------------------------------------------------------

    async def _synthesize_ws(self, text: str, run_id: str) -> bytes:
        async with self._ws_lock:
            ws = await self._ensure_ws(run_id)
            try:
                await ws.send(json.dumps({"type": "text", "data": {"text": text}}))
                await ws.send(json.dumps({"type": "flush"}))
                return await self._collect_ws_audio(ws, run_id)
            except (asyncio.CancelledError, GeneratorExit):
                await self._close_ws()
                raise
            except Exception:
                await self._close_ws()
                raise

    async def _collect_ws_audio(self, ws, run_id: str) -> bytes:
        chunks: list[bytes] = []
        first_seen = False

        while True:
            timeout = self.first_byte_timeout if not first_seen else self.completion_timeout
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                label = "first byte" if not first_seen else "completion"
                raise TtsProviderError(
                    f"Sarvam WS {label} timeout after {timeout:.1f}s"
                ) from exc

            if isinstance(raw, bytes):
                if not first_seen:
                    logger.debug("sarvam.tts.first_chunk run=%s bytes=%d", run_id, len(raw))
                    first_seen = True
                chunks.append(raw)
                continue

            msg = json.loads(raw)
            msg_type = msg.get("type", "")
            data = msg.get("data") or {}

            if msg_type == "audio":
                audio_b64 = data.get("audio") or data.get("content")
                if audio_b64:
                    audio = base64.b64decode(audio_b64)
                    if not first_seen:
                        logger.debug("sarvam.tts.first_chunk run=%s bytes=%d", run_id, len(audio))
                        first_seen = True
                    chunks.append(audio)

            elif msg_type in {"event"} and data.get("event_type") in {"final", "completion"}:
                break
            elif msg_type in {"final", "completion"}:
                break
            elif msg_type == "error":
                raise TtsProviderError(f"Sarvam WS error: {raw}")
            elif msg_type == "ping":
                with suppress(Exception):
                    await ws.send(json.dumps({"type": "pong"}))

        return b"".join(chunks)

    async def _ensure_ws(self, run_id: str):
        if self._ws is None or getattr(self._ws, "closed", False):
            self._ws = await self._connect_ws(run_id)
        return self._ws

    async def _connect_ws(self, run_id: str):
        params = urlencode({"model": self.model, "send_completion_event": "true"})
        url = f"{self.ws_url}?{params}"
        logger.debug("sarvam.tts.ws_connect run=%s url=%s", run_id, url)
        ws = await websockets.connect(
            url,
            additional_headers={"Api-Subscription-Key": self.api_key},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=2,
        )
        await ws.send(json.dumps({
            "type": "config",
            "data": {
                "target_language_code": self.language,
                "speaker": self.voice,
                "model": self.model,
                "pace": self.pace,
                "speech_sample_rate": self.sample_rate,
                "output_audio_codec": self.codec,
                "enable_preprocessing": True,
            },
        }))
        logger.debug("sarvam.tts.ws_ready run=%s", run_id)
        return ws

    async def _close_ws(self) -> None:
        ws, self._ws = self._ws, None
        if ws is not None:
            with suppress(Exception):
                await ws.close()


def sarvam_tts_engine_from_settings() -> SarvamTtsEngine:
    """Build a SarvamTtsEngine from the current app settings."""
    s = get_settings()
    return SarvamTtsEngine(
        api_key=s.SARVAM_API_KEY,
        model=s.SARVAM_TTS_MODEL,
        voice=s.SARVAM_TTS_SPEAKER,
        language=s.SARVAM_TTS_LANGUAGE,
        sample_rate=s.SARVAM_TTS_SAMPLE_RATE,
        codec=s.SARVAM_TTS_CODEC,
        pace=s.SARVAM_TTS_PACE,
        transport=s.SARVAM_TTS_TRANSPORT.lower(),
        ws_url=s.SARVAM_TTS_WEBSOCKET_URL,
        first_byte_timeout=s.SARVAM_TTS_FIRST_BYTE_TIMEOUT_SECONDS,
        completion_timeout=s.SARVAM_TTS_COMPLETION_TIMEOUT_SECONDS,
    )
