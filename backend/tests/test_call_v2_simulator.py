"""Phase 8.5 tests for the call v2 websocket simulator harness."""

import base64
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.config import get_settings
from app.call_v2.simulator import CallV2SimulatorHarness
from app.main import app


def _start_message(stream_sid: str = "stream-v2"):
    return {
        "event": "start",
        "now_ms": 0,
        "stream_sid": stream_sid,
        "start": {
            "stream_sid": stream_sid,
            "call_id": "manual-call",
            "media_format": {
                "encoding": "audio/l16",
                "sample_rate": 8000,
                "channels": 1,
            },
        },
    }


def _media_message(*, now_ms: int = 700, timestamp: int = 1600):
    return {
        "event": "media",
        "now_ms": now_ms,
        "stream_sid": "stream-v2",
        "media": {
            "payload": base64.b64encode(b"\xff\x7f" * 160).decode("ascii"),
            "timestamp": timestamp,
            "chunk": 1,
        },
    }


def _stt_final(text: str, *, now_ms: int, audio_offset_ms: int, duration_ms: int):
    return {
        "event": "stt.final",
        "now_ms": now_ms,
        "text": text,
        "segment_id": f"seg-{now_ms}",
        "audio_offset_ms": audio_offset_ms,
        "duration_ms": duration_ms,
    }


def _stt_endpoint(text: str, *, now_ms: int, audio_offset_ms: int, duration_ms: int):
    return {
        "event": "stt.endpoint",
        "now_ms": now_ms,
        "text": text,
        "audio_offset_ms": audio_offset_ms,
        "duration_ms": duration_ms,
        "silence_ms": 500,
    }


@pytest.mark.asyncio
async def test_harness_normal_flow_returns_audio_and_trace():
    harness = CallV2SimulatorHarness.create(call_id="manual-v2")

    assert await harness.handle_message(_start_message()) == []
    assert await harness.handle_message(
        _stt_final("I built APIs", now_ms=100, audio_offset_ms=1000, duration_ms=500)
    ) == []
    assert await harness.handle_message(
        _stt_endpoint("I built APIs", now_ms=600, audio_offset_ms=1000, duration_ms=500)
    ) == []

    outbound = await harness.handle_message({"event": "time.advance", "now_ms": 700})

    assert outbound[0]["event"] == "media"
    assert outbound[0]["stream_sid"] == "stream-v2"
    assert outbound[-1]["event"] == "v2.trace"
    event_types = [item["event_type"] for item in outbound[-1]["trace"]]
    assert "turn.confirmed" in event_types
    assert "audio.source_selected" in event_types


@pytest.mark.asyncio
async def test_harness_pause_continue_cancels_without_audio():
    harness = CallV2SimulatorHarness.create(call_id="manual-v2")

    await harness.handle_message(_start_message())
    await harness.handle_message(
        _stt_final("I built APIs", now_ms=100, audio_offset_ms=1000, duration_ms=500)
    )
    await harness.handle_message(
        _stt_endpoint("I built APIs", now_ms=600, audio_offset_ms=1000, duration_ms=500)
    )
    outbound = await harness.handle_message(_media_message())
    trace = await harness.handle_message({"event": "trace.get", "now_ms": 800})
    persisted = await harness.handle_message({"event": "persisted.get", "now_ms": 800})

    assert outbound == []
    assert persisted[0]["turns"] == []
    event_types = [item["event_type"] for item in trace[0]["trace"]]
    assert "turn.tentative_cancelled" in event_types
    assert trace[0]["state"] == "listening"


def test_call_v2_simulator_websocket_normal_flow():
    client = TestClient(app)

    with client.websocket_connect(f"/ws/call-v2-sim/{uuid4()}") as websocket:
        ready = websocket.receive_json()
        assert ready["event"] == "v2.ready"

        websocket.send_json(_start_message())
        websocket.send_json(
            _stt_final(
                "I built APIs",
                now_ms=100,
                audio_offset_ms=1000,
                duration_ms=500,
            )
        )
        websocket.send_json(
            _stt_endpoint(
                "I built APIs",
                now_ms=600,
                audio_offset_ms=1000,
                duration_ms=500,
            )
        )
        websocket.send_json({"event": "time.advance", "now_ms": 700})

        media = websocket.receive_json()
        trace = websocket.receive_json()

        assert media["event"] == "media"
        assert trace["event"] == "v2.trace"
        assert trace["state"] == "speaking"


def test_call_v2_simulator_websocket_stop_sends_end_call():
    client = TestClient(app)

    with client.websocket_connect(f"/ws/call-v2-sim/{uuid4()}") as websocket:
        assert websocket.receive_json()["event"] == "v2.ready"
        websocket.send_json(_start_message())
        websocket.send_json(
            {
                "event": "stop",
                "now_ms": 50,
                "stream_sid": "stream-v2",
                "stop": {"reason": "manual_stop"},
            }
        )
        assert websocket.receive_json()["event"] == "v2.end_call"
        assert websocket.receive_json()["event"] == "v2.trace"
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()


def test_call_v2_simulator_websocket_reports_bad_control_event():
    client = TestClient(app)

    with client.websocket_connect(f"/ws/call-v2-sim/{uuid4()}") as websocket:
        assert websocket.receive_json()["event"] == "v2.ready"
        websocket.send_json({"event": "stt.unsupported", "now_ms": 10})

        error = websocket.receive_json()

        assert error["event"] == "v2.error"
        assert "unsupported v2 simulator STT event" in error["message"]

        websocket.send_json({"event": "trace.get", "now_ms": 20})
        assert websocket.receive_json()["event"] == "v2.trace"


def test_call_v2_simulator_websocket_can_require_token():
    settings = get_settings()
    original = settings.CALL_V2_SIMULATOR_TOKEN
    settings.CALL_V2_SIMULATOR_TOKEN = "dev-secret"
    client = TestClient(app)
    try:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/call-v2-sim/{uuid4()}"):
                pass

        with client.websocket_connect(
            f"/ws/call-v2-sim/{uuid4()}?token=dev-secret"
        ) as websocket:
            assert websocket.receive_json()["event"] == "v2.ready"
    finally:
        settings.CALL_V2_SIMULATOR_TOKEN = original
