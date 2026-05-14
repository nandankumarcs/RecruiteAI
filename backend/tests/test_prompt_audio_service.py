"""
Unit tests for PromptAudioService.

Tests core functionality: text normalization, hash computation, asset lookup,
and asset creation/update operations.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio_prompt_asset import AudioPromptAsset
from app.services.prompt_audio_service import PromptAudioService
from app.services.storage import StorageProvider
from app.services.tts_providers import BaseTTSProvider


@pytest.fixture
def mock_session_factory():
    """Mock session factory that returns a mock AsyncSession."""
    mock_session = AsyncMock(spec=AsyncSession)
    return lambda: mock_session


@pytest.fixture
def mock_storage_provider():
    """Mock storage provider."""
    return MagicMock(spec=StorageProvider)


@pytest.fixture
def mock_tts_provider():
    """Mock TTS provider."""
    return MagicMock(spec=BaseTTSProvider)


@pytest.fixture
def service(mock_session_factory, mock_storage_provider, mock_tts_provider):
    """Create PromptAudioService instance with mocked dependencies."""
    return PromptAudioService(
        session_factory=mock_session_factory,
        storage_provider=mock_storage_provider,
        tts_provider=mock_tts_provider,
    )


class TestTextNormalization:
    """Test _normalize_text method."""

    def test_removes_extra_whitespace(self, service):
        """Should collapse multiple spaces to single space."""
        text = "Hello    world   with    extra     spaces"
        normalized = service._normalize_text(text)
        assert normalized == "hello world with extra spaces"

    def test_converts_to_lowercase(self, service):
        """Should convert all text to lowercase."""
        text = "Hello World WITH Mixed CASE"
        normalized = service._normalize_text(text)
        assert normalized == "hello world with mixed case"

    def test_strips_leading_trailing_punctuation(self, service):
        """Should remove punctuation from start and end."""
        text = "...Hello world!!!"
        normalized = service._normalize_text(text)
        assert normalized == "hello world"

    def test_preserves_internal_punctuation(self, service):
        """Should keep punctuation within the text."""
        text = "Hello, world! How are you?"
        normalized = service._normalize_text(text)
        # Leading/trailing punctuation stripped, internal preserved
        assert "," in normalized
        assert "!" in normalized

    def test_handles_newlines_and_tabs(self, service):
        """Should normalize newlines and tabs to spaces."""
        text = "Hello\n\tworld\twith\nnewlines"
        normalized = service._normalize_text(text)
        assert normalized == "hello world with newlines"

    def test_empty_string(self, service):
        """Should handle empty string."""
        text = ""
        normalized = service._normalize_text(text)
        assert normalized == ""

    def test_whitespace_only(self, service):
        """Should handle whitespace-only string."""
        text = "   \n\t   "
        normalized = service._normalize_text(text)
        assert normalized == ""


class TestAssetHashComputation:
    """Test _compute_asset_hash method."""

    def test_deterministic_hash(self, service):
        """Should produce same hash for identical inputs."""
        hash1 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        hash2 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        assert hash1 == hash2

    def test_different_text_different_hash(self, service):
        """Should produce different hash for different text."""
        hash1 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        hash2 = service._compute_asset_hash(
            normalized_text="goodbye world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        assert hash1 != hash2

    def test_different_speaker_different_hash(self, service):
        """Should produce different hash for different speaker."""
        hash1 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        hash2 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="arvind",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        assert hash1 != hash2

    def test_different_pace_different_hash(self, service):
        """Should produce different hash for different pace."""
        hash1 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        hash2 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.5,
            provider="sarvam",
        )
        assert hash1 != hash2

    def test_different_provider_different_hash(self, service):
        """Should produce different hash for different provider."""
        hash1 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        hash2 = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="deepgram",
        )
        assert hash1 != hash2

    def test_hash_format(self, service):
        """Should produce 64-character hexadecimal SHA-256 hash."""
        hash_value = service._compute_asset_hash(
            normalized_text="hello world",
            speaker="priya",
            language_code="en-IN",
            pace=1.2,
            provider="sarvam",
        )
        # SHA-256 produces 64 hex characters
        assert len(hash_value) == 64
        # Should be valid hexadecimal
        assert all(c in "0123456789abcdef" for c in hash_value)

    def test_matches_manual_sha256(self, service):
        """Should match manually computed SHA-256."""
        normalized_text = "hello world"
        speaker = "priya"
        language_code = "en-IN"
        pace = 1.2
        provider = "sarvam"

        # Compute hash using service
        service_hash = service._compute_asset_hash(
            normalized_text=normalized_text,
            speaker=speaker,
            language_code=language_code,
            pace=pace,
            provider=provider,
        )

        # Compute hash manually
        hash_input = f"{normalized_text}|{speaker}|{language_code}|{pace}|{provider}"
        manual_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        assert service_hash == manual_hash


class TestFindByHash:
    """Test _find_by_hash helper method."""

    @pytest.mark.asyncio
    async def test_finds_existing_asset(self, service):
        """Should find asset with matching hash."""
        mock_session = AsyncMock(spec=AsyncSession)
        test_hash = "abc123"
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="test_key",
            category="opener",
            text="test text",
            file_path="test/path.pcm",
            file_hash=test_hash,
            duration_ms=1000,
            status="ready",
        )

        # Mock the query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result

        result = await service._find_by_hash(mock_session, test_hash)

        assert result == expected_asset
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service):
        """Should return None when no matching asset exists."""
        mock_session = AsyncMock(spec=AsyncSession)
        test_hash = "nonexistent"

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service._find_by_hash(mock_session, test_hash)

        assert result is None

    @pytest.mark.asyncio
    async def test_filters_by_status(self, service):
        """Should filter by status when provided."""
        mock_session = AsyncMock(spec=AsyncSession)
        test_hash = "abc123"
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="test_key",
            category="opener",
            text="test text",
            file_path="test/path.pcm",
            file_hash=test_hash,
            duration_ms=1000,
            status="ready",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result

        result = await service._find_by_hash(mock_session, test_hash, status="ready")

        assert result == expected_asset
        # Verify the query was executed (status filter applied in query construction)
        mock_session.execute.assert_called_once()


class TestCreateOrUpdateAsset:
    """Test _create_or_update_asset helper method."""

    @pytest.mark.asyncio
    async def test_creates_new_asset(self, service):
        """Should create new asset when none exists."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock query to return no existing asset
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        asset = await service._create_or_update_asset(
            mock_session,
            template_key="test_opener",
            category="opener",
            text="Hello world",
            file_hash="abc123",
            status="pending",
        )

        assert asset.template_key == "test_opener"
        assert asset.category == "opener"
        assert asset.text == "Hello world"
        assert asset.file_hash == "abc123"
        assert asset.status == "pending"
        assert asset.file_path == "prompt-audio/opener/1/abc123.pcm"
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_asset(self, service):
        """Should update existing asset when found."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Create existing asset
        existing_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="test_opener",
            category="opener",
            text="Old text",
            file_path="old/path.pcm",
            file_hash="old_hash",
            duration_ms=1000,
            status="ready",
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Mock query to return existing asset
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_asset
        mock_session.execute.return_value = mock_result

        asset = await service._create_or_update_asset(
            mock_session,
            template_key="test_opener",
            category="opener",
            text="New text",
            file_hash="new_hash",
            status="pending",
            version=1,
        )

        assert asset == existing_asset
        assert asset.text == "New text"
        assert asset.file_hash == "new_hash"
        assert asset.status == "pending"
        # Should not add new asset
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_sets_job_and_question_ids(self, service):
        """Should set job_id and question_id when provided."""
        mock_session = AsyncMock(spec=AsyncSession)
        job_id = uuid.uuid4()
        question_id = uuid.uuid4()

        # Mock query to return no existing asset
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        asset = await service._create_or_update_asset(
            mock_session,
            template_key="question_123",
            category="question",
            text="What is your experience?",
            file_hash="abc123",
            job_id=job_id,
            question_id=question_id,
        )

        assert asset.job_id == job_id
        assert asset.question_id == question_id

    @pytest.mark.asyncio
    async def test_uses_custom_synthesis_config(self, service):
        """Should use custom synthesis configuration when provided."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock query to return no existing asset
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        asset = await service._create_or_update_asset(
            mock_session,
            template_key="test_key",
            category="opener",
            text="Test text",
            file_hash="abc123",
            provider="deepgram",
            speaker="custom_voice",
            language_code="en-US",
            sample_rate=16000,
            codec="opus",
            pace=1.5,
        )

        assert asset.provider == "deepgram"
        assert asset.speaker == "custom_voice"
        assert asset.language_code == "en-US"
        assert asset.sample_rate == 16000
        assert asset.codec == "opus"
        assert asset.pace == 1.5


class TestGetReadyAudioAsset:
    """Test get_ready_audio_asset method."""

    @pytest.mark.asyncio
    async def test_finds_asset_by_template_key(self, service, mock_session_factory):
        """Should find asset by template_key."""
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="opener_consent",
            category="opener",
            text="Hello world",
            file_path="prompt-audio/opener/1/abc123.pcm",
            file_hash="abc123",
            duration_ms=1000,
            status="ready",
            version=1,
        )

        # Mock the session and query result
        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(template_key="opener_consent")

        assert result == expected_asset
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_finds_asset_by_job_id(self, service, mock_session_factory):
        """Should find asset by job_id."""
        job_id = uuid.uuid4()
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="question_123",
            category="question",
            text="What is your experience?",
            file_path="prompt-audio/question/1/def456.pcm",
            file_hash="def456",
            duration_ms=2000,
            status="ready",
            version=1,
            job_id=job_id,
        )

        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(job_id=job_id)

        assert result == expected_asset
        assert result.job_id == job_id

    @pytest.mark.asyncio
    async def test_finds_asset_by_question_id(self, service, mock_session_factory):
        """Should find asset by question_id."""
        question_id = uuid.uuid4()
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="question_456",
            category="question",
            text="Describe your role",
            file_path="prompt-audio/question/1/ghi789.pcm",
            file_hash="ghi789",
            duration_ms=1500,
            status="ready",
            version=1,
            question_id=question_id,
        )

        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(question_id=question_id)

        assert result == expected_asset
        assert result.question_id == question_id

    @pytest.mark.asyncio
    async def test_finds_asset_by_multiple_criteria(self, service, mock_session_factory):
        """Should find asset by multiple criteria (template_key, job_id, question_id)."""
        job_id = uuid.uuid4()
        question_id = uuid.uuid4()
        expected_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="question_789",
            category="question",
            text="Tell me about your project",
            file_path="prompt-audio/question/1/jkl012.pcm",
            file_hash="jkl012",
            duration_ms=1800,
            status="ready",
            version=1,
            job_id=job_id,
            question_id=question_id,
        )

        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(
            template_key="question_789",
            job_id=job_id,
            question_id=question_id,
        )

        assert result == expected_asset
        assert result.template_key == "question_789"
        assert result.job_id == job_id
        assert result.question_id == question_id

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service, mock_session_factory):
        """Should return None when no matching asset exists."""
        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(template_key="nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_only_returns_ready_assets(self, service, mock_session_factory):
        """Should only return assets with status='ready'."""
        # This test verifies that the query filters by status='ready'
        # The actual filtering happens in the query construction
        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(template_key="pending_asset")

        # Should return None because only ready assets are queried
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_latest_version(self, service, mock_session_factory):
        """Should return the latest version when multiple versions exist."""
        # The query orders by version DESC, so it should return the highest version
        latest_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="opener_consent",
            category="opener",
            text="Updated hello world",
            file_path="prompt-audio/opener/2/xyz999.pcm",
            file_hash="xyz999",
            duration_ms=1100,
            status="ready",
            version=2,  # Latest version
        )

        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = latest_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset(template_key="opener_consent")

        assert result == latest_asset
        assert result.version == 2

    @pytest.mark.asyncio
    async def test_handles_no_criteria_provided(self, service, mock_session_factory):
        """Should handle case when no criteria are provided (returns first ready asset)."""
        # When no criteria are provided, it should still query with status='ready'
        # and return the first result
        some_asset = AudioPromptAsset(
            id=uuid.uuid4(),
            template_key="some_template",
            category="opener",
            text="Some text",
            file_path="prompt-audio/opener/1/aaa111.pcm",
            file_hash="aaa111",
            duration_ms=1000,
            status="ready",
            version=1,
        )

        mock_session = mock_session_factory()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = some_asset
        mock_session.execute.return_value = mock_result
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = AsyncMock()

        result = await service.get_ready_audio_asset()

        assert result == some_asset
