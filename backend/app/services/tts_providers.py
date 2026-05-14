"""TTS provider abstraction layer for pluggable text-to-speech services."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
import uuid
from contextlib import suppress
from typing import Protocol
from urllib.parse import urlencode

import httpx
import websockets

from app.config import get_settings
from app.debug_log import log_debug

settings = get_settings()
logger = logging.getLogger(__name__)


class BaseTTSProvider(Protocol):
    """Protocol for TTS providers."""

    provider_name: str
    supports_streaming: bool

    async def synthesize(
        self,
        *,
        text: str,
        telephony_provider: str,
    ) -> bytes:
        """
        Synthesize text to audio bytes (non-streaming).
        
        Args:
            text: Text to synthesize
            telephony_provider: "exotel" or "twilio" - determines audio format
            
        Returns:
            Raw audio bytes in the format expected by the telephony provider
        """
        ...

    async def synthesize_stream(
        self,
        *,
        text: str,
        telephony_provider: str,
    ):
        """
        Synthesize text to audio bytes with streaming (async generator).
        
        Args:
            text: Text to synthesize
            telephony_provider: "exotel" or "twilio" - determines audio format
            
        Yields:
            Audio byte chunks as they become available
        """
        ...


class DeepgramTTSProvider:
    """Deepgram TTS provider - original implementation."""

    provider_name = "deepgram"
    supports_streaming = False  # Deepgram REST API doesn't support true streaming

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.model = settings.DEEPGRAM_TTS_MODEL

    async def synthesize(
        self,
        *,
        text: str,
        telephony_provider: str,
    ) -> bytes:
        """Synthesize using Deepgram TTS."""
        tts_run_id = str(uuid.uuid4())[:8]
        log_debug(f"[{tts_run_id}] Deepgram TTS: {text[:50]}...")

        if not self.api_key:
            log_debug(f"[{tts_run_id}] ERROR: Missing Deepgram API key")
            raise ValueError("Missing Deepgram API key")

        encoding = "linear16" if telephony_provider == "exotel" else "mulaw"
        tts_url = (
            f"https://api.deepgram.com/v1/speak?model={self.model}"
            f"&encoding={encoding}&sample_rate=8000"
        )

        # Normalize smart quotes
        text_to_speak = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')

        # NOTE: We use a subprocess for TTS to avoid hanging issues
        # Multiple attempts showed that in-process HTTP calls to Deepgram's
        # REST TTS can hang indefinitely when invoked from the Twilio media
        # WebSocket handler. A subprocess isolates the network call.
        import os

        env = os.environ.copy()
        env["RECRUITEAI_TTS_URL"] = tts_url
        env["RECRUITEAI_TTS_TOKEN"] = self.api_key
        env["RECRUITEAI_TTS_TEXT"] = text_to_speak

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            (
                "import base64, json, os, requests\n"
                "url=os.environ['RECRUITEAI_TTS_URL']\n"
                "token=os.environ['RECRUITEAI_TTS_TOKEN']\n"
                "text=os.environ['RECRUITEAI_TTS_TEXT']\n"
                "r=requests.post(url, headers={'Authorization': f'Token {token}', 'Content-Type':'application/json'}, json={'text': text}, timeout=15)\n"
                "out={'status': r.status_code, 'audio_b64': base64.b64encode(r.content).decode('ascii')}\n"
                "print(json.dumps(out))\n"
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)

        if proc.returncode != 0:
            raise RuntimeError(
                f"TTS subprocess failed rc={proc.returncode}: {stderr.decode('utf-8', 'ignore')[:300]}"
            )

        result = json.loads(stdout.decode("utf-8").strip() or "{}")
        status_code = int(result.get("status", 0))
        audio_bytes = base64.b64decode(result.get("audio_b64", "") or "")

        log_debug(f"[{tts_run_id}] Response status: {status_code}, bytes: {len(audio_bytes)}")

        if status_code != 200:
            log_debug(f"[{tts_run_id}] Deepgram TTS Error: {status_code}")
            raise RuntimeError(f"Deepgram TTS failed with status {status_code}")

        return audio_bytes

    async def synthesize_stream(
        self,
        *,
        text: str,
        telephony_provider: str,
    ):
        """Deepgram doesn't support streaming, so we yield the complete audio as one chunk."""
        audio_bytes = await self.synthesize(text=text, telephony_provider=telephony_provider)
        yield audio_bytes


class SarvamTTSProvider:
    """Sarvam TTS provider - Indian accent English with streaming support."""

    provider_name = "sarvam"
    supports_streaming = True  # Sarvam HTTP streaming sends chunks progressively

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.model = settings.SARVAM_TTS_MODEL
        self.speaker = settings.SARVAM_TTS_SPEAKER
        self.language = settings.SARVAM_TTS_LANGUAGE
        self.sample_rate = settings.SARVAM_TTS_SAMPLE_RATE
        self.codec = settings.SARVAM_TTS_CODEC
        self.pace = settings.SARVAM_TTS_PACE
        self.transport = settings.SARVAM_TTS_TRANSPORT.lower()
        self.ws_url = settings.SARVAM_TTS_WEBSOCKET_URL
        self.use_http_stream = settings.SARVAM_TTS_USE_HTTP_STREAM
        self.first_byte_timeout = settings.SARVAM_TTS_FIRST_BYTE_TIMEOUT_SECONDS
        self.completion_timeout = settings.SARVAM_TTS_COMPLETION_TIMEOUT_SECONDS
        self._ws = None
        self._ws_lock = asyncio.Lock()

    async def synthesize(
        self,
        *,
        text: str,
        telephony_provider: str,
    ) -> bytes:
        """Synthesize using Sarvam TTS HTTP streaming endpoint (collects all chunks)."""
        audio_chunks = []
        async for chunk in self.synthesize_stream(text=text, telephony_provider=telephony_provider):
            audio_chunks.append(chunk)
        return b"".join(audio_chunks)

    async def synthesize_stream(
        self,
        *,
        text: str,
        telephony_provider: str,
    ):
        """
        Synthesize using Sarvam TTS HTTP streaming endpoint with progressive chunk delivery.
        
        This method yields audio chunks as they arrive from Sarvam's streaming API,
        allowing playback to start immediately without waiting for complete generation.
        """
        tts_run_id = str(uuid.uuid4())[:8]
        log_debug(f"[{tts_run_id}] Sarvam TTS (streaming): {text[:50]}...")

        if not self.api_key:
            log_debug(f"[{tts_run_id}] ERROR: Missing Sarvam API key")
            raise ValueError("Missing Sarvam API key")

        # For now, we only support Exotel with linear16
        # Twilio support can be added later with mulaw conversion
        if telephony_provider != "exotel":
            raise ValueError(f"Sarvam TTS currently only supports Exotel, got: {telephony_provider}")

        if self.transport == "websocket":
            async for chunk in self._synthesize_websocket_stream(
                text=text,
                telephony_provider=telephony_provider,
                tts_run_id=tts_run_id,
            ):
                yield chunk
            return

        async for chunk in self._synthesize_http_stream(
            text=text,
            telephony_provider=telephony_provider,
            tts_run_id=tts_run_id,
        ):
            yield chunk

    async def _close_websocket(self) -> None:
        ws = self._ws
        self._ws = None
        if ws is not None:
            with suppress(Exception):
                await ws.close()

    async def reset_stream(self) -> None:
        """Drop any in-flight websocket audio so the next turn starts cleanly."""
        await self._close_websocket()

    async def _connect_websocket(self, tts_run_id: str):
        params = urlencode({"model": self.model, "send_completion_event": "true"})
        url = f"{self.ws_url}?{params}"
        headers = {"Api-Subscription-Key": self.api_key}
        log_debug(f"[{tts_run_id}] Connecting Sarvam websocket...")
        ws = await websockets.connect(
            url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=2,
        )
        await ws.send(
            json.dumps(
                {
                    "type": "config",
                    "data": {
                        "target_language_code": self.language,
                        "speaker": self.speaker,
                        "model": self.model,
                        "pace": self.pace,
                        "speech_sample_rate": self.sample_rate,
                        "output_audio_codec": self.codec,
                        "enable_preprocessing": True,
                    },
                }
            )
        )
        log_debug(f"[{tts_run_id}] Sarvam websocket configured")
        return ws

    async def _ensure_websocket(self, tts_run_id: str):
        ws = self._ws
        if ws is None or getattr(ws, "closed", False):
            self._ws = await self._connect_websocket(tts_run_id)
        return self._ws

    async def _synthesize_websocket_stream(
        self,
        *,
        text: str,
        telephony_provider: str,
        tts_run_id: str,
    ):
        """Synthesize using Sarvam's websocket streaming API."""
        async with self._ws_lock:
            ws = await self._ensure_websocket(tts_run_id)
            try:
                await ws.send(json.dumps({"type": "text", "data": {"text": text}}))
                await ws.send(json.dumps({"type": "flush"}))

                total_bytes = 0
                chunk_count = 0
                first_audio_seen = False

                while True:
                    timeout = (
                        self.first_byte_timeout
                        if not first_audio_seen
                        else self.completion_timeout
                    )
                    try:
                        raw_message = await asyncio.wait_for(ws.recv(), timeout=timeout)
                    except asyncio.TimeoutError as e:
                        if not first_audio_seen:
                            raise RuntimeError(
                                f"Sarvam websocket first byte exceeded {self.first_byte_timeout:.2f}s"
                            ) from e
                        raise RuntimeError(
                            f"Sarvam websocket completion exceeded {self.completion_timeout:.2f}s"
                        ) from e

                    message = {}
                    audio_bytes = b""
                    if isinstance(raw_message, bytes):
                        message_type = "audio"
                        audio_bytes = raw_message
                    else:
                        message = json.loads(raw_message)
                        message_type = message.get("type")
                        audio_b64 = (
                            (message.get("data") or {}).get("audio")
                            or (message.get("data") or {}).get("content")
                        )
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)

                    if message_type == "audio" and audio_bytes:
                        first_audio_seen = True
                        chunk_count += 1
                        total_bytes += len(audio_bytes)
                        if chunk_count == 1:
                            log_debug(
                                f"[{tts_run_id}] First Sarvam websocket audio chunk received: {len(audio_bytes)} bytes"
                            )
                        yield audio_bytes
                        continue

                    if message_type == "event":
                        event_type = (message.get("data") or {}).get("event_type")
                        if event_type in {"final", "completion"}:
                            break
                    elif message_type in {"final", "completion"}:
                        break
                    elif message_type == "error":
                        raise RuntimeError(f"Sarvam websocket error: {raw_message}")
                    elif message_type == "ping":
                        with suppress(Exception):
                            await ws.send(json.dumps({"type": "pong"}))

                log_debug(
                    f"[{tts_run_id}] Sarvam websocket complete: {total_bytes} bytes in {chunk_count} chunks"
                )
            except (asyncio.CancelledError, GeneratorExit):
                await self._close_websocket()
                raise
            except Exception:
                await self._close_websocket()
                raise

    async def _synthesize_http_stream(
        self,
        *,
        text: str,
        telephony_provider: str,
        tts_run_id: str,
    ):
        """Synthesize using Sarvam's HTTP streaming endpoint."""
        url = "https://api.sarvam.ai/text-to-speech/stream"
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "target_language_code": self.language,
            "speaker": self.speaker,
            "model": self.model,
            "speech_sample_rate": self.sample_rate,
            "output_audio_codec": self.codec,
            "pace": self.pace,
        }

        log_debug(f"[{tts_run_id}] Requesting Sarvam HTTP stream (progressive delivery)...")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        log_debug(
                            f"[{tts_run_id}] Sarvam TTS Error: {response.status_code} - {error_text[:200]}"
                        )
                        raise RuntimeError(
                            f"Sarvam TTS failed with status {response.status_code}: {error_text[:200]}"
                        )

                    total_bytes = 0
                    chunk_count = 0
                    chunks = response.aiter_bytes()
                    while True:
                        try:
                            timeout = self.first_byte_timeout if chunk_count == 0 else None
                            chunk = await asyncio.wait_for(chunks.__anext__(), timeout=timeout)
                        except StopAsyncIteration:
                            break
                        except asyncio.TimeoutError as e:
                            raise RuntimeError(
                                f"Sarvam TTS first byte exceeded {self.first_byte_timeout:.2f}s"
                            ) from e

                        if chunk:
                            total_bytes += len(chunk)
                            chunk_count += 1
                            # Log first chunk to track time-to-first-byte
                            if chunk_count == 1:
                                log_debug(
                                    f"[{tts_run_id}] First audio chunk received: {len(chunk)} bytes"
                                )
                            yield chunk

                    log_debug(
                        f"[{tts_run_id}] Sarvam TTS streaming complete: {total_bytes} bytes in {chunk_count} chunks"
                    )

        except httpx.TimeoutException as e:
            log_debug(f"[{tts_run_id}] Sarvam TTS timeout: {e}")
            raise RuntimeError(f"Sarvam TTS request timed out: {e}")
        except Exception as e:
            log_debug(f"[{tts_run_id}] Sarvam TTS error: {e}")
            raise


def get_tts_provider() -> BaseTTSProvider:
    """Factory function to get the configured TTS provider."""
    provider_name = settings.TTS_PROVIDER.lower()

    if provider_name == "sarvam":
        return SarvamTTSProvider()
    elif provider_name == "deepgram":
        return DeepgramTTSProvider()
    else:
        logger.warning(f"Unknown TTS provider '{provider_name}', falling back to Deepgram")
        return DeepgramTTSProvider()
