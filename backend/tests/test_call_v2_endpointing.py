"""Phase 5 tests for call v2 endpointing and speculation."""

from app.call_v2.audio.formats import LINEAR16_8K_MONO
from app.call_v2.events import (
    CallIdentity,
    SttFinalSegment,
    SttInterimTranscript,
    SttTentativeEndpoint,
    TelephonyAudioFrame,
    TentativeTurnCancelled,
    TentativeTurnStarted,
    TimestampMetadata,
    TurnConfirmed,
)
from app.call_v2.ids import GenerationIdManager
from app.call_v2.turns.endpointing import EndpointingController, EndpointingSettings
from app.call_v2.turns.speculation import SpeculationHarness, input_fingerprint


def _final_segment(
    text: str,
    *,
    start_ms: int = 0,
    duration_ms: int = 500,
    segment_id: str = "s1",
    received_at_ms: int = 100,
) -> SttFinalSegment:
    return SttFinalSegment(
        type="stt.final_segment",
        text=text,
        confidence=0.9,
        segment_id=segment_id,
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=start_ms,
        ),
        duration_ms=duration_ms,
    )


def _tentative_endpoint(
    text: str,
    *,
    start_ms: int = 0,
    duration_ms: int = 500,
    received_at_ms: int = 600,
) -> SttTentativeEndpoint:
    return SttTentativeEndpoint(
        type="stt.tentative_endpoint",
        text=text,
        confidence=0.9,
        silence_ms=500,
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=start_ms,
        ),
        duration_ms=duration_ms,
    )


def _audio_frame(
    *,
    received_at_ms: int,
    audio_offset_ms: int,
    sequence_number: int = 1,
) -> TelephonyAudioFrame:
    return TelephonyAudioFrame(
        type="telephony.audio_frame",
        identity=CallIdentity(provider="browser", stream_id="stream-1"),
        payload=b"\x00\x01",
        format=LINEAR16_8K_MONO,
        sequence_number=sequence_number,
        timestamps=TimestampMetadata(
            backend_received_at_ms=received_at_ms,
            audio_offset_ms=audio_offset_ms,
        ),
    )


def test_endpointing_starts_tentative_turn_after_stt_endpoint():
    controller = EndpointingController(
        settings=EndpointingSettings(confirmation_window_ms=800)
    )
    controller.on_final_segment(
        _final_segment("I built APIs", start_ms=1000, duration_ms=700)
    )

    events = controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", start_ms=1000, duration_ms=700)
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, TentativeTurnStarted)
    assert event.generation_id == 1
    assert event.text == "I built APIs"
    assert event.evidence["endpoint_audio_end_ms"] == 1700
    assert event.evidence["confirmation_deadline_ms"] == 1400


def test_pause_then_candidate_continues_cancels_tentative_generation():
    controller = EndpointingController()
    controller.on_final_segment(
        _final_segment("I built APIs", start_ms=1000, duration_ms=700)
    )
    controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", start_ms=1000, duration_ms=700)
    )

    events = controller.on_audio_frame(
        _audio_frame(received_at_ms=700, audio_offset_ms=1750)
    )

    assert len(events) == 1
    cancelled = events[0]
    assert isinstance(cancelled, TentativeTurnCancelled)
    assert cancelled.generation_id == 1
    assert cancelled.reason == "audio_after_tentative"
    assert controller.generation_ids.is_stale(1) is True


def test_non_candidate_audio_frame_does_not_cancel_tentative_turn():
    controller = EndpointingController()
    controller.on_final_segment(
        _final_segment("I built APIs", start_ms=1000, duration_ms=700)
    )
    controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", start_ms=1000, duration_ms=700)
    )

    events = controller.on_audio_frame(
        _audio_frame(received_at_ms=700, audio_offset_ms=1750),
        candidate_activity=False,
    )

    assert events == []
    assert controller.pending_turn is not None


def test_silence_confirmation_confirms_turn_after_window():
    controller = EndpointingController(
        settings=EndpointingSettings(confirmation_window_ms=800)
    )
    controller.on_final_segment(
        _final_segment("yes", start_ms=1000, duration_ms=200, received_at_ms=100)
    )
    controller.on_tentative_endpoint(
        _tentative_endpoint("yes", start_ms=1000, duration_ms=200, received_at_ms=600)
    )

    assert controller.advance_time(1399) == []
    events = controller.advance_time(1400)

    assert len(events) == 1
    confirmed = events[0]
    assert isinstance(confirmed, TurnConfirmed)
    assert confirmed.generation_id == 1
    assert confirmed.text == "yes"
    assert confirmed.duration_ms == 200
    assert controller.generation_ids.can_speak(1) is True


def test_late_stt_endpoint_cancels_when_newer_audio_already_arrived():
    controller = EndpointingController(
        settings=EndpointingSettings(confirmation_window_ms=800)
    )
    controller.on_audio_frame(
        _audio_frame(received_at_ms=1500, audio_offset_ms=2500)
    )
    controller.on_final_segment(
        _final_segment(
            "I started answering",
            start_ms=1000,
            duration_ms=700,
            received_at_ms=2000,
        )
    )
    controller.on_tentative_endpoint(
        _tentative_endpoint(
            "I started answering",
            start_ms=1000,
            duration_ms=700,
            received_at_ms=2000,
        )
    )

    events = controller.advance_time(2800)

    assert len(events) == 1
    cancelled = events[0]
    assert isinstance(cancelled, TentativeTurnCancelled)
    assert cancelled.generation_id == 1
    assert cancelled.reason == "audio_after_tentative"
    assert controller.pending_turn is None
    assert controller.generation_ids.is_stale(1) is True


def test_duplicate_final_after_tentative_does_not_cancel_pending_turn():
    controller = EndpointingController()
    segment = _final_segment("I built APIs", start_ms=1000, duration_ms=700)
    controller.on_final_segment(segment)
    controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", start_ms=1000, duration_ms=700)
    )

    events = controller.on_final_segment(segment)

    assert events == []
    assert controller.pending_turn is not None


def test_post_tts_guard_accepts_short_answer_without_speech_started():
    controller = EndpointingController(
        settings=EndpointingSettings(
            confirmation_window_ms=300,
            post_tts_guard_ms=1000,
        )
    )
    controller.mark_tts_completed(at_ms=1000)
    controller.on_final_segment(
        _final_segment("yes", start_ms=1100, duration_ms=150, received_at_ms=1200)
    )

    events = controller.on_tentative_endpoint(
        _tentative_endpoint("yes", start_ms=1100, duration_ms=150, received_at_ms=1250)
    )
    confirmed = controller.advance_time(1550)

    assert isinstance(events[0], TentativeTurnStarted)
    assert events[0].evidence["post_tts_guard"] is True
    assert len(confirmed) == 1
    assert confirmed[0].text == "yes"


def test_vad_only_audio_during_assistant_speaking_does_not_cancel_tentative_turn():
    controller = EndpointingController()
    controller.on_final_segment(
        _final_segment("I built APIs", start_ms=1000, duration_ms=700)
    )
    controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", start_ms=1000, duration_ms=700)
    )
    controller.mark_assistant_speaking(True)

    events = controller.on_audio_frame(
        _audio_frame(received_at_ms=900, audio_offset_ms=1900)
    )

    assert events == []
    assert controller.pending_turn is not None


def test_speculative_result_is_only_eligible_after_matching_confirmation():
    ids = GenerationIdManager()
    controller = EndpointingController(
        generation_ids=ids,
        settings=EndpointingSettings(confirmation_window_ms=100),
    )
    speculation = SpeculationHarness()
    controller.on_final_segment(_final_segment("I built APIs"))
    turn_event = controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs", received_at_ms=600)
    )[0]
    assert isinstance(turn_event, TentativeTurnStarted)

    started = speculation.start(turn_event)
    completed = speculation.complete(
        turn_event.generation_id,
        result={"spoken_text": "Great, tell me more."},
        completed_at_ms=650,
        latency_ms=50,
    )

    assert started.speculative is True
    assert completed.result["spoken_text"] == "Great, tell me more."
    assert (
        speculation.eligible_result(
            turn_event.generation_id,
            expected_fingerprint=input_fingerprint("I built APIs"),
            generation_ids=ids,
        )
        is None
    )

    controller.advance_time(700)

    assert speculation.eligible_result(
        turn_event.generation_id,
        expected_fingerprint=input_fingerprint("I built APIs"),
        generation_ids=ids,
    ) == {"spoken_text": "Great, tell me more."}


def test_stale_speculative_output_is_discarded_after_cancellation():
    ids = GenerationIdManager()
    controller = EndpointingController(generation_ids=ids)
    speculation = SpeculationHarness()
    controller.on_final_segment(_final_segment("I built APIs"))
    turn_event = controller.on_tentative_endpoint(
        _tentative_endpoint("I built APIs")
    )[0]
    assert isinstance(turn_event, TentativeTurnStarted)
    speculation.start(turn_event)

    cancelled = controller.on_interim_transcript(
        SttInterimTranscript(
            type="stt.interim_transcript",
            text="I built APIs and workers",
            confidence=0.8,
            timestamps=TimestampMetadata(backend_received_at_ms=700),
            duration_ms=900,
        )
    )[0]
    assert isinstance(cancelled, TentativeTurnCancelled)
    speculation.cancel(cancelled)
    completed = speculation.complete(
        turn_event.generation_id,
        result={"spoken_text": "Stale response"},
        completed_at_ms=900,
        latency_ms=300,
    )

    assert completed.result["discarded"] is True
    assert speculation.eligible_result(
        turn_event.generation_id,
        expected_fingerprint=input_fingerprint("I built APIs"),
        generation_ids=ids,
    ) is None
