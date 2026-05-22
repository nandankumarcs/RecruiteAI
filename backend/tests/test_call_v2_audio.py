"""Phase 3 tests for call v2 audio boundary helpers."""

import pytest

from app.call_v2.audio.codecs import convert_audio, linear16_to_mulaw, mulaw_to_linear16
from app.call_v2.audio.formats import (
    LINEAR16_8K_MONO,
    MULAW_8K_MONO,
    bytes_per_second,
    frame_size_bytes,
    provider_audio_format,
    validate_audio_payload,
)
from app.call_v2.audio.pacing import AudioFramePlan, iter_audio_frames
from app.call_v2.events import AudioFormat


def test_provider_audio_format_matches_v2_provider_boundaries():
    assert provider_audio_format("browser") == LINEAR16_8K_MONO
    assert provider_audio_format("exotel") == LINEAR16_8K_MONO
    assert provider_audio_format("twilio") == MULAW_8K_MONO
    with pytest.raises(ValueError, match="unsupported telephony provider"):
        provider_audio_format("unknown")


def test_audio_byte_rates_and_20ms_frame_sizes_match_legacy_runtime_values():
    assert bytes_per_second(LINEAR16_8K_MONO) == 16000
    assert bytes_per_second(MULAW_8K_MONO) == 8000

    assert frame_size_bytes(LINEAR16_8K_MONO, frame_duration_ms=20) == 320
    assert frame_size_bytes(MULAW_8K_MONO, frame_duration_ms=20) == 160


def test_audio_frame_plan_exposes_chunk_size_and_sleep_time():
    plan = AudioFramePlan(audio_format=LINEAR16_8K_MONO, frame_duration_ms=20)

    assert plan.chunk_size_bytes == 320
    assert plan.sleep_seconds == 0.020


def test_iter_audio_frames_chunks_and_optionally_pads_final_frame():
    payload = b"a" * 700

    frames = list(
        iter_audio_frames(
            payload,
            audio_format=LINEAR16_8K_MONO,
            frame_duration_ms=20,
        )
    )
    padded_frames = list(
        iter_audio_frames(
            payload,
            audio_format=LINEAR16_8K_MONO,
            frame_duration_ms=20,
            pad_final_frame=True,
        )
    )

    assert [len(frame) for frame in frames] == [320, 320, 60]
    assert [len(frame) for frame in padded_frames] == [320, 320, 320]
    assert padded_frames[-1].startswith(b"a" * 60)
    assert padded_frames[-1][60:] == b"\x00" * 260


def test_validate_audio_payload_rejects_misaligned_linear16_payload():
    validate_audio_payload(b"\x00\x01", LINEAR16_8K_MONO)

    with pytest.raises(ValueError, match="align"):
        validate_audio_payload(b"\x00", LINEAR16_8K_MONO)


def test_mulaw_linear16_conversion_changes_width_and_preserves_duration():
    linear16 = b"\x00\x00\xff\x7f\x00\x80\x34\x12"

    mulaw = linear16_to_mulaw(linear16)
    restored_linear16 = mulaw_to_linear16(mulaw)

    assert len(mulaw) == len(linear16) // 2
    assert len(restored_linear16) == len(linear16)


def test_convert_audio_returns_same_payload_for_compatible_formats():
    payload = b"\x00\x01"

    assert (
        convert_audio(
            payload,
            source_format=LINEAR16_8K_MONO,
            target_format=AudioFormat(codec="linear16"),
        )
        == payload
    )


def test_convert_audio_converts_between_supported_telephony_codecs():
    linear16 = b"\x00\x00\xff\x7f"

    mulaw = convert_audio(
        linear16,
        source_format=LINEAR16_8K_MONO,
        target_format=MULAW_8K_MONO,
    )
    restored = convert_audio(
        mulaw,
        source_format=MULAW_8K_MONO,
        target_format=LINEAR16_8K_MONO,
    )

    assert len(mulaw) == 2
    assert len(restored) == len(linear16)


def test_convert_audio_rejects_sample_rate_or_channel_conversion():
    with pytest.raises(ValueError, match="sample-rate conversion"):
        convert_audio(
            b"\x00\x01",
            source_format=LINEAR16_8K_MONO,
            target_format=AudioFormat(codec="mulaw", sample_rate_hz=16000),
        )

    with pytest.raises(ValueError, match="channel conversion"):
        convert_audio(
            b"\x00\x01",
            source_format=LINEAR16_8K_MONO,
            target_format=AudioFormat(codec="mulaw", channels=2),
        )


def test_linear16_to_mulaw_rejects_misaligned_input():
    with pytest.raises(ValueError, match="align"):
        linear16_to_mulaw(b"\x00")
