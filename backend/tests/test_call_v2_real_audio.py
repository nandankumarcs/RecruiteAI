"""Phase 10 tests for provider-backed simulator audio boundaries."""

import pytest
from fastapi.testclient import TestClient

from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.audio.wav import linear16_to_wav_bytes, wav_bytes_to_linear16
from app.call_v2.events import (
    CallIdentity,
    TelephonyAudioFrame,
    TimestampMetadata,
)
from app.call_v2.stt.openai import OpenAIBufferedTranscriptionEngine
from app.call_v2.simulator import CallV2SimulatorHarness
from app.call_v2.tts.base import TtsRequest
from app.call_v2.tts.openai import OpenAITtsEngine
from app.config import get_settings
from app.main import app


class _FakeTranscriptions:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.text


class _FakeSpeech:
    def __init__(self, wav_payload: bytes):
        self.wav_payload = wav_payload
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Response", (), {"content": self.wav_payload})()


class _FakeAudio:
    def __init__(self, *, transcript: str = "I built APIs", wav_payload: bytes = b""):
        self.transcriptions = _FakeTranscriptions(transcript)
        self.speech = _FakeSpeech(wav_payload)


class _FakeOpenAIClient:
    def __init__(self, *, transcript: str = "I built APIs", wav_payload: bytes = b""):
        self.audio = _FakeAudio(transcript=transcript, wav_payload=wav_payload)


class _BufferedSttStub:
    async def transcribe_buffer(self, *, now_ms: int, silence_ms: int | None = None):
        self.now_ms = now_ms
        self.silence_ms = silence_ms
        return []


def test_wav_round_trip_and_resample_to_target_format():
    source_format = LINEAR16_8K_MONO
    payload = b"\x00\x00\x01\x00" * 160

    wav_payload = linear16_to_wav_bytes(payload, audio_format=source_format)
    decoded = wav_bytes_to_linear16(
        wav_payload,
        target_format=LINEAR16_8K_MONO,
    )

    assert decoded == payload


@pytest.mark.asyncio
async def test_openai_buffered_stt_transcribes_buffer_to_final_and_endpoint():
    client = _FakeOpenAIClient(transcript="  I built APIs  ")
    engine = OpenAIBufferedTranscriptionEngine(
        api_key="test-key",
        input_format=LINEAR16_8K_MONO,
        client=client,
    )

    await engine.send_audio(
        TelephonyAudioFrame(
            type="telephony.audio_frame",
            identity=CallIdentity(provider="browser", stream_id="stream-v2"),
            payload=b"\x00\x00\x01\x00" * 160,
            format=LINEAR16_8K_MONO,
            sequence_number=1,
            timestamps=TimestampMetadata(
                backend_received_at_ms=100,
                audio_offset_ms=1000,
            ),
        )
    )

    events = await engine.transcribe_buffer(now_ms=700, silence_ms=500)

    assert [event.type for event in events] == [
        "stt.final_segment",
        "stt.tentative_endpoint",
    ]
    assert events[0].text == "I built APIs"
    assert events[0].duration_ms == 40
    assert events[1].silence_ms == 500
    assert client.audio.transcriptions.calls[0]["response_format"] == "text"
    assert client.audio.transcriptions.calls[0]["file"].name == "call-v2-turn.wav"
    assert await engine.transcribe_buffer(now_ms=800) == []


@pytest.mark.asyncio
async def test_simulator_routes_transcribe_buffer_before_generic_stt_controls():
    harness = CallV2SimulatorHarness.create(call_id="manual-v2")
    stub = _BufferedSttStub()
    harness.session.stt_engine = stub

    outbound = await harness.handle_message(
        {"event": "stt.transcribe_buffer", "now_ms": 750, "silence_ms": 500}
    )

    assert outbound == []
    assert stub.now_ms == 750
    assert stub.silence_ms == 500


@pytest.mark.asyncio
async def test_openai_tts_converts_wav_response_to_output_format():
    wav_payload = linear16_to_wav_bytes(
        b"\x00\x00\x01\x00" * 320,
        audio_format=LINEAR16_8K_MONO,
    )
    client = _FakeOpenAIClient(wav_payload=wav_payload)
    engine = OpenAITtsEngine(api_key="test-key", client=client)

    audio = await engine.synthesize(
        TtsRequest(
            generation_id=1,
            text="Thanks. Please continue.",
            output_format=LINEAR16_8K_MONO,
            provider="openai",
            model="gpt-4o-mini-tts",
            voice="coral",
        )
    )

    assert audio.provider == "openai"
    assert audio.audio_format == LINEAR16_8K_MONO
    assert audio.payload == b"\x00\x00\x01\x00" * 320
    assert client.audio.speech.calls[0]["response_format"] == "wav"
    assert client.audio.speech.calls[0]["input"] == "Thanks. Please continue."


def test_call_v2_simulator_real_audio_mode_is_explicitly_requested():
    settings = get_settings()
    original_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"
    client = TestClient(app)
    try:
        with client.websocket_connect("/ws/call-v2-sim/manual?real_audio=1") as ws:
            ready = ws.receive_json()
            assert ready["event"] == "v2.ready"
            assert ready["mode"] == "real_audio"
            assert "stt.transcribe_buffer" in ready["controls"]
    finally:
        settings.OPENAI_API_KEY = original_key
