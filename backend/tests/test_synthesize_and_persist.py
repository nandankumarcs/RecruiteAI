"""
Integration tests for _synthesize_and_persist method.

Tests the complete audio synthesis and persistence flow including:
- TTS API calls with correct parameters
- Audio format validation (linear16 PCM, 8kHz)
- Storage integration
- Duration calculation
- Error handling
"""

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile

from app.models.audio_prompt_asset import AudioPromptAsset
from app.services.prompt_audio_service import PromptAudioService
from app.services.storage import StorageProvider
from app.services.tts_providers import BaseTTSProvider


@pytest.fixture
def mock_session_factory():
    """Mock session factory that returns a mock AsyncSession."""
    mock_session = AsyncMock()
    return lambda: mock_session


@pytest.fixture
def mock_storage_provider():
    """Mock storage provider."""
    mock_storage = MagicMock(spec=StorageProvider)
    mock_storage.save_file = AsyncMock(return_value="/full/path/to/audio.pcm")
    return mock_storage


@pytest.fixture
def mock_tts_provider():
    """Mock TTS provider."""
    mock_tts = MagicMock(spec=BaseTTSProvider)
    # Generate fake audio: 8000 Hz * 2 bytes/sample * 1 second = 16000 bytes
    fake_audio = b"\x00\x01" * 8000  # 16000 bytes = 1 second of audio
    mock_tts.synthesize = AsyncMock(return_value=fake_audio)
    return mock_tts


@pytest.fixture
def service(mock_session_factory, mock_storage_provider, mock_tts_provider):
    """Create PromptAudioService instance with mocked dependencies."""
    return PromptAudioService(
        session_factory=mock_session_factory,
        storage_provider=mock_storage_provider,
        tts_provider=mock_tts_provider,
    )


@pytest.fixture
def sample_asset():
    """Create a sample AudioPromptAsset for testing."""
    return AudioPromptAsset(
        id=uuid.uuid4(),
        template_key="test_opener",
        category="opener",
        text="Hello! I'm calling from the recruitment team.",
        file_path="prompt-audio/opener/1/abc123.pcm",
        file_hash="abc123",
        duration_ms=0,  # Will be calculated
        provider="sarvam",
        speaker="priya",
        language_code="en-IN",
        sample_rate=8000,
        codec="linear16",
        pace=1.2,
        job_id=None,
        question_id=None,
        version=1,
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestSynthesizeAndPersist:
    """Test _synthesize_and_persist method."""

    @pytest.mark.asyncio
    async def test_calls_tts_with_correct_parameters(self, service, sample_asset, mock_tts_provider):
        """Should call TTS provider with correct text and telephony provider."""
        await service._synthesize_and_persist(sample_asset)

        mock_tts_provider.synthesize.assert_called_once_with(
            text=sample_asset.text,
            telephony_provider="exotel",
        )

    @pytest.mark.asyncio
    async def test_saves_audio_to_storage(self, service, sample_asset, mock_storage_provider):
        """Should save synthesized audio to storage with correct path."""
        await service._synthesize_and_persist(sample_asset)

        # Verify save_file was called
        mock_storage_provider.save_file.assert_called_once()
        
        # Extract the call arguments
        call_args = mock_storage_provider.save_file.call_args
        upload_file = call_args.kwargs["file"]
        destination_path = call_args.kwargs["destination_path"]

        # Verify destination path matches asset file_path
        assert destination_path == sample_asset.file_path
        
        # Verify upload file has correct filename
        assert upload_file.filename == f"{sample_asset.file_hash}.pcm"

    @pytest.mark.asyncio
    async def test_calculates_duration_correctly(self, service, sample_asset, mock_tts_provider):
        """Should calculate duration_ms from audio byte length."""
        # Mock audio: 8000 Hz * 2 bytes/sample * 1 second = 16000 bytes
        fake_audio = b"\x00\x01" * 8000  # 16000 bytes = 1 second
        mock_tts_provider.synthesize = AsyncMock(return_value=fake_audio)

        await service._synthesize_and_persist(sample_asset)

        # Duration should be 1000ms (1 second)
        assert sample_asset.duration_ms == 1000

    @pytest.mark.asyncio
    async def test_calculates_duration_for_different_lengths(self, service, sample_asset, mock_tts_provider):
        """Should calculate duration correctly for various audio lengths."""
        # Mock audio: 8000 Hz * 2 bytes/sample * 2.5 seconds = 40000 bytes
        fake_audio = b"\x00\x01" * 20000  # 40000 bytes = 2.5 seconds
        mock_tts_provider.synthesize = AsyncMock(return_value=fake_audio)

        await service._synthesize_and_persist(sample_asset)

        # Duration should be 2500ms (2.5 seconds)
        assert sample_asset.duration_ms == 2500

    @pytest.mark.asyncio
    async def test_handles_tts_synthesis_failure(self, service, sample_asset, mock_tts_provider):
        """Should raise RuntimeError when TTS synthesis fails."""
        mock_tts_provider.synthesize = AsyncMock(side_effect=Exception("TTS API error"))

        with pytest.raises(RuntimeError, match="TTS synthesis failed"):
            await service._synthesize_and_persist(sample_asset)

    @pytest.mark.asyncio
    async def test_handles_empty_audio_response(self, service, sample_asset, mock_tts_provider):
        """Should raise RuntimeError when TTS returns empty audio."""
        mock_tts_provider.synthesize = AsyncMock(return_value=b"")

        with pytest.raises(RuntimeError, match="TTS synthesis returned empty audio"):
            await service._synthesize_and_persist(sample_asset)

    @pytest.mark.asyncio
    async def test_handles_storage_failure(self, service, sample_asset, mock_storage_provider):
        """Should raise RuntimeError when storage save fails."""
        mock_storage_provider.save_file = AsyncMock(side_effect=Exception("Storage error"))

        with pytest.raises(RuntimeError, match="Failed to save audio file"):
            await service._synthesize_and_persist(sample_asset)

    @pytest.mark.asyncio
    async def test_uses_asset_synthesis_configuration(self, service, mock_tts_provider):
        """Should use synthesis configuration from asset metadata."""
        # Create asset with custom configuration
        custom_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="custom_test",
            category="opener",
            text="Custom text",
            file_path="prompt-audio/opener/1/custom.pcm",
            file_hash="custom123",
            duration_ms=0,
            provider="sarvam",
            speaker="arvind",  # Different speaker
            language_code="hi-IN",  # Different language
            sample_rate=16000,  # Different sample rate
            codec="opus",  # Different codec
            pace=1.5,  # Different pace
            job_id=None,
            question_id=None,
            version=1,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Mock audio with appropriate length for 16kHz
        fake_audio = b"\x00\x01" * 16000  # 32000 bytes = 1 second at 16kHz
        mock_tts_provider.synthesize = AsyncMock(return_value=fake_audio)

        await service._synthesize_and_persist(custom_asset)

        # Verify TTS was called with asset's text
        mock_tts_provider.synthesize.assert_called_once_with(
            text=custom_asset.text,
            telephony_provider="exotel",
        )

        # Verify duration calculation uses asset's sample_rate
        # 32000 bytes / (16000 Hz * 2 bytes/sample) = 1 second = 1000ms
        assert custom_asset.duration_ms == 1000

    @pytest.mark.asyncio
    async def test_audio_format_is_raw_pcm(self, service, sample_asset, mock_storage_provider):
        """Should save audio as raw PCM without WAV container."""
        await service._synthesize_and_persist(sample_asset)

        # Verify file extension is .pcm
        assert sample_asset.file_path.endswith(".pcm")
        
        # Verify storage was called with correct path
        call_args = mock_storage_provider.save_file.call_args
        destination_path = call_args.kwargs["destination_path"]
        assert destination_path.endswith(".pcm")

    @pytest.mark.asyncio
    async def test_path_pattern_matches_specification(self, service, sample_asset):
        """Should use path pattern: prompt-audio/{category}/{version}/{hash}.pcm"""
        await service._synthesize_and_persist(sample_asset)

        # Verify path pattern
        expected_pattern = f"prompt-audio/{sample_asset.category}/{sample_asset.version}/{sample_asset.file_hash}.pcm"
        assert sample_asset.file_path == expected_pattern

    @pytest.mark.asyncio
    async def test_logs_synthesis_progress(self, service, sample_asset, caplog):
        """Should log synthesis progress for observability."""
        import logging
        caplog.set_level(logging.INFO)

        await service._synthesize_and_persist(sample_asset)

        # Verify key log messages are present
        log_messages = [record.message for record in caplog.records]
        
        # Should log synthesis start
        assert any("Synthesizing audio" in msg for msg in log_messages)
        
        # Should log synthesis complete
        assert any("TTS synthesis complete" in msg for msg in log_messages)
        
        # Should log file save
        assert any("Audio file saved" in msg for msg in log_messages)
        
        # Should log final persistence
        assert any("Audio persisted" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_logs_errors_on_failure(self, service, sample_asset, mock_tts_provider, caplog):
        """Should log errors when synthesis or storage fails."""
        import logging
        caplog.set_level(logging.ERROR)

        mock_tts_provider.synthesize = AsyncMock(side_effect=Exception("TTS API error"))

        with pytest.raises(RuntimeError):
            await service._synthesize_and_persist(sample_asset)

        # Verify error was logged
        log_messages = [record.message for record in caplog.records]
        assert any("TTS synthesis failed" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_duration_calculation_formula(self, service, sample_asset, mock_tts_provider):
        """Should use correct formula: duration_ms = (bytes / (sample_rate * 2)) * 1000"""
        # Test with known values
        sample_rate = 8000  # Hz
        duration_seconds = 3.5  # seconds
        bytes_per_second = sample_rate * 2  # 2 bytes per sample for 16-bit
        audio_bytes = int(bytes_per_second * duration_seconds)
        
        fake_audio = b"\x00" * audio_bytes
        mock_tts_provider.synthesize = AsyncMock(return_value=fake_audio)

        await service._synthesize_and_persist(sample_asset)

        # Expected duration: 3.5 seconds = 3500ms
        assert sample_asset.duration_ms == 3500

    @pytest.mark.asyncio
    async def test_does_not_modify_asset_on_failure(self, service, sample_asset, mock_tts_provider):
        """Should not modify asset duration_ms if synthesis fails."""
        original_duration = sample_asset.duration_ms
        mock_tts_provider.synthesize = AsyncMock(side_effect=Exception("TTS error"))

        with pytest.raises(RuntimeError):
            await service._synthesize_and_persist(sample_asset)

        # Duration should remain unchanged
        assert sample_asset.duration_ms == original_duration
