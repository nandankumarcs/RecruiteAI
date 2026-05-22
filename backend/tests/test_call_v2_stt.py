"""Phase 4 tests for call v2 STT boundaries."""

import json

import pytest

from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import (
    CallIdentity,
    SttError,
    SttFinalSegment,
    SttInterimTranscript,
    SttSpeechStarted,
    SttTentativeEndpoint,
    SttUtteranceEnded,
    TelephonyAudioFrame,
    TimestampMetadata,
)
from app.call_v2.stt.deepgram import DeepgramEventNormalizer
from app.call_v2.stt.fake import FakeSttEngine
from app.call_v2.stt.transcript_assembler import TranscriptAssembler


def _results_payload(
    *,
    transcript: str,
    is_final: bool,
    speech_final: bool = False,
    confidence: float = 0.91,
    start: float = 1.25,
    duration: float = 0.5,
):
    return {
        "type": "Results",
        "is_final": is_final,
        "speech_final": speech_final,
        "start": start,
        "duration": duration,
        "channel": {
            "alternatives": [
                {
                    "transcript": transcript,
                    "confidence": confidence,
                }
            ]
        },
    }


def test_deepgram_normalizer_maps_speech_started():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    events = normalizer.normalize(
        {"type": "SpeechStarted"},
        backend_received_at_ms=100,
    )

    assert len(events) == 1
    assert isinstance(events[0], SttSpeechStarted)
    assert events[0].timestamps.backend_received_at_ms == 100


def test_deepgram_normalizer_maps_interim_results_from_json_string():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    events = normalizer.normalize(
        json.dumps(_results_payload(transcript="hello there", is_final=False)),
        backend_received_at_ms=200,
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, SttInterimTranscript)
    assert event.text == "hello there"
    assert event.confidence == 0.91
    assert event.duration_ms == 500
    assert event.timestamps.audio_offset_ms == 1250


def test_deepgram_normalizer_maps_final_speech_final_to_segment_and_tentative_endpoint():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    events = normalizer.normalize(
        _results_payload(
            transcript="I worked on FastAPI",
            is_final=True,
            speech_final=True,
            start=2.0,
            duration=1.2,
        ),
        backend_received_at_ms=300,
    )

    assert len(events) == 2
    final_segment, tentative_endpoint = events
    assert isinstance(final_segment, SttFinalSegment)
    assert isinstance(tentative_endpoint, SttTentativeEndpoint)
    assert final_segment.text == "I worked on FastAPI"
    assert final_segment.segment_id == "start=2.0;duration=1.2"
    assert final_segment.duration_ms == 1200
    assert tentative_endpoint.text == "I worked on FastAPI"
    assert tentative_endpoint.duration_ms == 1200


def test_deepgram_normalizer_accepts_final_result_speech_finalized_variant():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)
    payload = _results_payload(
        transcript="please explain the question",
        is_final=False,
        start=3.0,
        duration=0.75,
    )
    payload["type"] = "FinalResult"
    payload["speech_finalized"] = True
    payload.pop("is_final")

    events = normalizer.normalize(payload, backend_received_at_ms=350)

    assert len(events) == 2
    final_segment, tentative_endpoint = events
    assert isinstance(final_segment, SttFinalSegment)
    assert isinstance(tentative_endpoint, SttTentativeEndpoint)
    assert final_segment.text == "please explain the question"
    assert final_segment.segment_id == "start=3.0;duration=0.75"
    assert tentative_endpoint.text == "please explain the question"


def test_deepgram_normalizer_accepts_channels_alternatives_variant():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)
    payload = _results_payload(transcript="yes that works", is_final=False)
    payload["channels"] = [payload.pop("channel")]

    events = normalizer.normalize(payload, backend_received_at_ms=250)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, SttInterimTranscript)
    assert event.text == "yes that works"
    assert event.confidence == 0.91


def test_deepgram_normalizer_does_not_use_request_id_as_segment_id():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    first = normalizer.normalize(
        {
            **_results_payload(
                transcript="first segment",
                is_final=True,
                start=1.0,
                duration=0.5,
            ),
            "request_id": "same-request",
        },
        backend_received_at_ms=300,
    )[0]
    second = normalizer.normalize(
        {
            **_results_payload(
                transcript="second segment",
                is_final=True,
                start=1.5,
                duration=0.5,
            ),
            "request_id": "same-request",
        },
        backend_received_at_ms=400,
    )[0]

    assert isinstance(first, SttFinalSegment)
    assert isinstance(second, SttFinalSegment)
    assert first.segment_id == "start=1.0;duration=0.5"
    assert second.segment_id == "start=1.5;duration=0.5"


def test_deepgram_normalizer_maps_utterance_end_and_error():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    utterance_events = normalizer.normalize(
        {"type": "UtteranceEnd", "last_word_end": 4.2},
        backend_received_at_ms=400,
    )
    error_events = normalizer.normalize(
        {"type": "Error", "error": {"code": "bad_request", "message": "Nope"}},
        backend_received_at_ms=500,
    )

    assert isinstance(utterance_events[0], SttUtteranceEnded)
    assert utterance_events[0].timestamps.audio_offset_ms == 4200
    assert isinstance(error_events[0], SttError)
    assert error_events[0].code == "bad_request"
    assert error_events[0].message == "Nope"


def test_deepgram_normalizer_ignores_empty_results_and_unknown_events():
    normalizer = DeepgramEventNormalizer(input_format=LINEAR16_8K_MONO)

    assert (
        normalizer.normalize(
            _results_payload(transcript="", is_final=True),
            backend_received_at_ms=10,
        )
        == []
    )
    assert normalizer.normalize({"type": "Metadata"}, backend_received_at_ms=10) == []


def test_transcript_assembler_deduplicates_provider_replays_without_hiding_repeated_speech():
    assembler = TranscriptAssembler()

    first = SttFinalSegment(
        type="stt.final_segment",
        text="I worked on FastAPI",
        confidence=0.9,
        segment_id="s1",
        timestamps=TimestampMetadata(backend_received_at_ms=10, audio_offset_ms=1000),
        duration_ms=1000,
    )
    duplicate_id = SttFinalSegment(
        type="stt.final_segment",
        text="I worked on FastAPI again",
        confidence=0.9,
        segment_id="s1",
        timestamps=TimestampMetadata(backend_received_at_ms=11, audio_offset_ms=2000),
        duration_ms=1000,
    )
    overlapping_duplicate_text = SttFinalSegment(
        type="stt.final_segment",
        text="  I worked on FastAPI  ",
        confidence=0.8,
        segment_id="s2",
        timestamps=TimestampMetadata(backend_received_at_ms=12, audio_offset_ms=1000),
        duration_ms=1000,
    )
    overlapping_suffix_duplicate = SttFinalSegment(
        type="stt.final_segment",
        text="FastAPI",
        confidence=0.8,
        segment_id="s3",
        timestamps=TimestampMetadata(backend_received_at_ms=13, audio_offset_ms=1600),
        duration_ms=500,
    )
    repeated_later = SttFinalSegment(
        type="stt.final_segment",
        text="I worked on FastAPI",
        confidence=0.8,
        segment_id="s4",
        timestamps=TimestampMetadata(backend_received_at_ms=14, audio_offset_ms=3000),
        duration_ms=1000,
    )
    second = SttFinalSegment(
        type="stt.final_segment",
        text="and PostgreSQL",
        confidence=0.8,
        segment_id="s5",
        timestamps=TimestampMetadata(backend_received_at_ms=15, audio_offset_ms=4200),
        duration_ms=600,
    )

    assert assembler.add_final_segment(first) is True
    assert assembler.add_final_segment(duplicate_id) is False
    assert assembler.add_final_segment(overlapping_duplicate_text) is False
    assert assembler.add_final_segment(overlapping_suffix_duplicate) is False
    assert assembler.add_final_segment(repeated_later) is True
    assert assembler.add_final_segment(second) is True
    assert (
        assembler.current_text()
        == "I worked on FastAPI I worked on FastAPI and PostgreSQL"
    )


def test_transcript_assembler_replaces_overlapping_extended_final_segment():
    assembler = TranscriptAssembler()

    assert assembler.add_final_segment(
        SttFinalSegment(
            type="stt.final_segment",
            text="I built APIs",
            confidence=0.9,
            segment_id="s1",
            timestamps=TimestampMetadata(
                backend_received_at_ms=10,
                audio_offset_ms=1000,
            ),
            duration_ms=500,
        )
    )
    assert assembler.add_final_segment(
        SttFinalSegment(
            type="stt.final_segment",
            text="I built APIs and workers",
            confidence=0.9,
            segment_id="s2",
            timestamps=TimestampMetadata(
                backend_received_at_ms=20,
                audio_offset_ms=1000,
            ),
            duration_ms=900,
        )
    )

    assert assembler.current_text() == "I built APIs and workers"


def test_transcript_assembler_flushes_transcript_with_confidence_and_duration_then_resets():
    assembler = TranscriptAssembler()
    timestamps = TimestampMetadata(backend_received_at_ms=10)

    assembler.add_final_segment(
        SttFinalSegment(
            type="stt.final_segment",
            text="I built APIs",
            confidence=0.8,
            segment_id="s1",
            timestamps=timestamps,
            duration_ms=700,
        )
    )
    assembler.add_final_segment(
        SttFinalSegment(
            type="stt.final_segment",
            text="with FastAPI",
            confidence=1.0,
            segment_id="s2",
            timestamps=timestamps,
            duration_ms=300,
        )
    )

    transcript = assembler.flush()

    assert transcript is not None
    assert transcript.text == "I built APIs with FastAPI"
    assert transcript.segment_count == 2
    assert transcript.confidence == pytest.approx(0.9)
    assert transcript.duration_ms == 1000
    assert assembler.current_text() == ""


def test_transcript_assembler_uses_tentative_endpoint_text_when_no_final_segments():
    assembler = TranscriptAssembler()
    endpoint = SttTentativeEndpoint(
        type="stt.tentative_endpoint",
        text="yes sure",
        confidence=0.7,
        silence_ms=None,
        timestamps=TimestampMetadata(backend_received_at_ms=20),
        duration_ms=200,
    )

    transcript = assembler.flush(endpoint)

    assert transcript is not None
    assert transcript.text == "yes sure"
    assert transcript.segment_count == 0


@pytest.mark.asyncio
async def test_fake_stt_engine_collects_audio_and_replays_events():
    event = SttSpeechStarted(
        type="stt.speech_started",
        timestamps=TimestampMetadata(backend_received_at_ms=10),
    )
    engine = FakeSttEngine(
        provider="fake",
        input_format=LINEAR16_8K_MONO,
        events=[event],
    )
    frame = TelephonyAudioFrame(
        type="telephony.audio_frame",
        identity=CallIdentity(provider="browser", stream_id="stream-1"),
        payload=b"\x00\x01",
        format=LINEAR16_8K_MONO,
        sequence_number=1,
        timestamps=TimestampMetadata(backend_received_at_ms=1),
    )

    await engine.send_audio(frame)
    replayed = [item async for item in engine.receive_events()]
    await engine.close()

    assert engine.received_audio == [frame]
    assert replayed == [event]
    with pytest.raises(RuntimeError, match="closed"):
        await engine.send_audio(frame)
