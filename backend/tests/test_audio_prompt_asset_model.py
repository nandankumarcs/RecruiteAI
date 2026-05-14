"""
Unit tests for AudioPromptAsset model.

Tests model creation, field validation, and constraint enforcement.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.audio_prompt_asset import AudioPromptAsset


class TestAudioPromptAssetModel:
    """Test suite for AudioPromptAsset model."""

    @pytest.mark.asyncio
    async def test_create_audio_prompt_asset(self, db_session):
        """Test creating a basic audio prompt asset."""
        asset = AudioPromptAsset(
            template_key="opener_consent",
            category="opener",
            text="Hello! I'm calling from the recruitment team.",
            file_path="prompt-audio/opener/1/abc123.pcm",
            file_hash="abc123def456",
            duration_ms=3000,
            provider="sarvam",
            speaker="priya",
            language_code="en-IN",
            sample_rate=8000,
            codec="linear16",
            pace=1.2,
            version=1,
            status="ready",
            last_generated_at=datetime.now(timezone.utc),
        )

        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(asset)

        assert asset.id is not None
        assert asset.template_key == "opener_consent"
        assert asset.category == "opener"
        assert asset.status == "ready"
        assert asset.version == 1

    @pytest.mark.asyncio
    async def test_default_values(self, db_session):
        """Test that default values are applied correctly."""
        asset = AudioPromptAsset(
            template_key="test_template",
            category="filler",
            text="Understood",
            file_path="prompt-audio/filler/1/xyz789.pcm",
            file_hash="xyz789",
            duration_ms=500,
        )

        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(asset)

        # Check defaults
        assert asset.provider == "sarvam"
        assert asset.speaker == "priya"
        assert asset.language_code == "en-IN"
        assert asset.sample_rate == 8000
        assert asset.codec == "linear16"
        assert asset.pace == 1.2
        assert asset.version == 1
        assert asset.status == "pending"
        assert asset.created_at is not None
        assert asset.updated_at is not None

    @pytest.mark.asyncio
    async def test_unique_constraint_template_key_version(self, db_session):
        """Test that composite unique constraint on (template_key, version) is enforced."""
        # Create first asset
        asset1 = AudioPromptAsset(
            template_key="reprompt_clarify",
            category="reprompt",
            text="Can you clarify that?",
            file_path="prompt-audio/reprompt/1/hash1.pcm",
            file_hash="hash1",
            duration_ms=2000,
            version=1,
        )
        db_session.add(asset1)
        await db_session.commit()

        # Try to create duplicate with same template_key and version
        asset2 = AudioPromptAsset(
            template_key="reprompt_clarify",
            category="reprompt",
            text="Can you clarify that please?",  # Different text
            file_path="prompt-audio/reprompt/1/hash2.pcm",
            file_hash="hash2",
            duration_ms=2100,
            version=1,  # Same version
        )
        db_session.add(asset2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_multiple_versions_allowed(self, db_session):
        """Test that multiple versions of the same template are allowed."""
        # Create version 1
        asset1 = AudioPromptAsset(
            template_key="closing_thank_you",
            category="closing",
            text="Thank you for your time.",
            file_path="prompt-audio/closing/1/hash1.pcm",
            file_hash="hash1",
            duration_ms=2000,
            version=1,
        )
        db_session.add(asset1)
        await db_session.commit()

        # Create version 2 (should succeed)
        asset2 = AudioPromptAsset(
            template_key="closing_thank_you",
            category="closing",
            text="Thank you very much for your time.",
            file_path="prompt-audio/closing/2/hash2.pcm",
            file_hash="hash2",
            duration_ms=2500,
            version=2,
        )
        db_session.add(asset2)
        await db_session.commit()
        await db_session.refresh(asset2)

        # Verify both exist
        result = await db_session.execute(
            select(AudioPromptAsset).where(
                AudioPromptAsset.template_key == "closing_thank_you"
            )
        )
        assets = result.scalars().all()
        assert len(assets) == 2
        assert {a.version for a in assets} == {1, 2}

    @pytest.mark.asyncio
    async def test_nullable_job_and_question_ids(self, db_session):
        """Test that job_id and question_id can be null for global templates."""
        asset = AudioPromptAsset(
            template_key="filler_okay",
            category="filler",
            text="Okay",
            file_path="prompt-audio/filler/1/okay.pcm",
            file_hash="okay123",
            duration_ms=400,
            job_id=None,
            question_id=None,
        )

        db_session.add(asset)
        await db_session.commit()
        await db_session.refresh(asset)

        assert asset.job_id is None
        assert asset.question_id is None

    @pytest.mark.asyncio
    async def test_status_values(self, db_session):
        """Test different status values."""
        statuses = ["pending", "ready", "failed"]

        for status in statuses:
            asset = AudioPromptAsset(
                template_key=f"test_{status}",
                category="filler",
                text=f"Test {status}",
                file_path=f"prompt-audio/filler/1/{status}.pcm",
                file_hash=f"{status}_hash",
                duration_ms=500,
                status=status,
            )
            db_session.add(asset)

        await db_session.commit()

        # Verify all were created
        result = await db_session.execute(
            select(AudioPromptAsset).where(
                AudioPromptAsset.template_key.in_(
                    [f"test_{s}" for s in statuses]
                )
            )
        )
        assets = result.scalars().all()
        assert len(assets) == 3
        assert {a.status for a in assets} == set(statuses)

    @pytest.mark.asyncio
    async def test_indexes_exist(self, db_session):
        """Test that required indexes are defined."""
        # Verify indexes directly from the model's table metadata
        indexes = AudioPromptAsset.__table__.indexes
        index_names = {idx.name for idx in indexes}

        # Check required indexes
        assert "ix_audio_prompt_assets_template_key" in index_names
        assert "ix_audio_prompt_assets_file_hash" in index_names
        assert "ix_audio_prompt_assets_status" in index_names
        assert "ix_audio_prompt_assets_category" in index_names
        assert "idx_job_question" in index_names
