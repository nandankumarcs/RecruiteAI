"""
PromptAudioService - Service for managing pre-generated audio assets.

This service handles the generation, persistence, and retrieval of pre-generated
TTS audio for stable recruiter prompts (opener, questions, reprompts, closers, fillers).

Requirements: 2.1, 2.2, 17.1, 17.2, 17.3, 17.4
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.audio_prompt_asset import AudioPromptAsset
from app.models.question import InterviewQuestion
from app.services.prompt_templates import (
    DEFAULT_CLARIFICATION_TEXTS,
    DEFAULT_CLOSING_TEXTS,
    DEFAULT_FILLER_TEXTS,
    DEFAULT_OPENER_TEXT,
    DEFAULT_REPROMPT_TEXTS,
)
from app.services.storage import StorageProvider
from app.services.tts_providers import BaseTTSProvider, get_tts_provider

logger = logging.getLogger(__name__)
settings = get_settings()


class PromptAudioService:
    """
    Service for managing pre-generated audio assets.
    
    Handles audio generation, persistence, and retrieval with deterministic
    hashing for deduplication and efficient caching.
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        storage_provider: StorageProvider,
        tts_provider: BaseTTSProvider,
    ):
        """
        Initialize PromptAudioService.
        
        Args:
            session_factory: Callable that returns an async database session
            storage_provider: Storage abstraction for file operations
            tts_provider: TTS provider for audio synthesis
        """
        self.session_factory = session_factory
        self.storage = storage_provider
        self.tts = tts_provider

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _current_synthesis_config(self) -> dict[str, object]:
        return {
            "provider": self.tts.provider_name,
            "speaker": settings.SARVAM_TTS_SPEAKER,
            "language_code": settings.SARVAM_TTS_LANGUAGE,
            "pace": settings.SARVAM_TTS_PACE,
            "sample_rate": settings.SARVAM_TTS_SAMPLE_RATE,
            "codec": settings.SARVAM_TTS_CODEC,
        }

    def _normalize_text(self, text: str) -> str:
        """
        Normalize prompt text for consistent hashing.
        
        Removes extra whitespace, converts to lowercase, and strips punctuation
        to ensure identical prompts generate the same hash regardless of minor
        formatting differences.
        
        Args:
            text: Raw prompt text
            
        Returns:
            Normalized text string
            
        Requirements: 17.1
        """
        # Remove extra whitespace (collapse multiple spaces to single space)
        text = " ".join(text.split())
        
        # Convert to lowercase for case-insensitive matching
        text = text.lower()
        
        # Strip leading/trailing punctuation
        text = text.strip(".,!?;:\"'")
        
        return text

    def _compute_asset_hash(
        self,
        normalized_text: str,
        speaker: str,
        language_code: str,
        pace: float,
        provider: str,
    ) -> str:
        """
        Compute deterministic hash for asset deduplication.
        
        Uses SHA-256 to create a unique identifier based on normalized text
        and all synthesis configuration parameters. Identical prompts with
        identical configuration will always produce the same hash.
        
        Args:
            normalized_text: Normalized prompt text
            speaker: TTS speaker/voice identifier
            language_code: Language code (e.g., "en-IN")
            pace: Speech pace multiplier
            provider: TTS provider name
            
        Returns:
            64-character hexadecimal SHA-256 hash
            
        Requirements: 17.2, 17.3, 17.4
        """
        # Combine all synthesis parameters into a single string
        # Use pipe separator to avoid ambiguity
        hash_input = f"{normalized_text}|{speaker}|{language_code}|{pace}|{provider}"
        
        # Use SHA-256 for cryptographic-quality deterministic hashing
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    async def _find_by_hash(
        self,
        session: AsyncSession,
        file_hash: str,
        status: str | None = None,
    ) -> AudioPromptAsset | None:
        """
        Find an existing audio asset by file hash.
        
        Helper method for checking if an asset with identical content
        already exists before generating new audio.
        
        Args:
            session: Database session
            file_hash: SHA-256 hash of normalized text + config
            status: Optional status filter (e.g., "ready")
            
        Returns:
            Matching AudioPromptAsset or None if not found
            
        Requirements: 2.2
        """
        query = select(AudioPromptAsset).where(AudioPromptAsset.file_hash == file_hash)
        
        if status:
            query = query.where(AudioPromptAsset.status == status)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def _create_or_update_asset(
        self,
        session: AsyncSession,
        *,
        template_key: str,
        category: str,
        text: str,
        file_hash: str,
        job_id: uuid.UUID | None = None,
        question_id: uuid.UUID | None = None,
        provider: str = "sarvam",
        speaker: str = "priya",
        language_code: str = "en-IN",
        sample_rate: int = 8000,
        codec: str = "linear16",
        pace: float = 1.2,
        status: str = "pending",
        version: int = 1,
    ) -> AudioPromptAsset:
        """
        Create or update an audio prompt asset record.
        
        Helper method for persisting asset metadata to the database.
        Checks for existing asset with same template_key and version,
        updating if found or creating new if not.
        
        Args:
            session: Database session
            template_key: Unique identifier for the template
            category: Asset category (opener, question, reprompt, etc.)
            text: Original prompt text
            file_hash: SHA-256 hash for deduplication
            job_id: Optional job association
            question_id: Optional question association
            provider: TTS provider name
            speaker: TTS speaker/voice
            language_code: Language code
            sample_rate: Audio sample rate in Hz
            codec: Audio codec
            pace: Speech pace multiplier
            status: Asset status (pending, ready, failed)
            version: Asset version number
            
        Returns:
            Created or updated AudioPromptAsset instance
            
        Requirements: 2.1, 2.2
        """
        # Check if asset with this template_key and version already exists
        query = select(AudioPromptAsset).where(
            AudioPromptAsset.template_key == template_key,
            AudioPromptAsset.version == version,
        )
        result = await session.execute(query)
        existing_asset = result.scalar_one_or_none()

        if existing_asset:
            # Update existing asset
            existing_asset.text = text
            existing_asset.file_hash = file_hash
            existing_asset.status = status
            existing_asset.category = category
            existing_asset.job_id = job_id
            existing_asset.question_id = question_id
            existing_asset.provider = provider
            existing_asset.speaker = speaker
            existing_asset.language_code = language_code
            existing_asset.sample_rate = sample_rate
            existing_asset.codec = codec
            existing_asset.pace = pace
            existing_asset.updated_at = self._utcnow()
            
            logger.info(
                f"Updated existing asset: {template_key} v{version} [{status}]"
            )
            return existing_asset
        else:
            # Create new asset
            # Generate file path: prompt-audio/{category}/{version}/{hash}.pcm
            file_path = f"prompt-audio/{category}/{version}/{file_hash}.pcm"
            
            new_asset = AudioPromptAsset(
                id=uuid.uuid4(),
                template_key=template_key,
                category=category,
                text=text,
                file_path=file_path,
                file_hash=file_hash,
                duration_ms=0,  # Will be updated after synthesis
                provider=provider,
                speaker=speaker,
                language_code=language_code,
                sample_rate=sample_rate,
                codec=codec,
                pace=pace,
                job_id=job_id,
                question_id=question_id,
                version=version,
                status=status,
                created_at=self._utcnow(),
                updated_at=self._utcnow(),
            )
            
            session.add(new_asset)
            
            logger.info(
                f"Created new asset: {template_key} v{version} [{status}]"
            )
            return new_asset

    async def ensure_prompt_audio(
        self,
        *,
        template_key: str,
        category: str,
        text: str,
        job_id: uuid.UUID | None = None,
        question_id: uuid.UUID | None = None,
        force_regenerate: bool = False,
    ) -> AudioPromptAsset:
        """
        Ensure audio asset exists for the given prompt.
        
        Returns existing ready asset or generates new one. This is the main
        entry point for obtaining audio assets - it handles deduplication,
        caching, and generation orchestration.
        
        Args:
            template_key: Unique identifier for the template (e.g., "opener_consent", "question_12345")
            category: Asset category (opener, question, reprompt, clarification, closing, filler)
            text: Original prompt text to synthesize
            job_id: Optional job association for job-specific assets
            question_id: Optional question association for question assets
            force_regenerate: If True, bypass cache and regenerate audio
            
        Returns:
            AudioPromptAsset instance (status may be pending, ready, or failed)
            
        Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
        """
        synthesis = self._current_synthesis_config()
        provider = str(synthesis["provider"])
        speaker = str(synthesis["speaker"])
        language_code = str(synthesis["language_code"])
        pace = float(synthesis["pace"])
        sample_rate = int(synthesis["sample_rate"])
        codec = str(synthesis["codec"])
        
        # Normalize text and compute hash for deduplication
        normalized_text = self._normalize_text(text)
        asset_hash = self._compute_asset_hash(
            normalized_text=normalized_text,
            speaker=speaker,
            language_code=language_code,
            pace=pace,
            provider=provider,
        )
        
        async with self.session_factory() as session:
            # Check for existing ready asset (unless force_regenerate=True)
            existing_template_result = await session.execute(
                select(AudioPromptAsset)
                .where(AudioPromptAsset.template_key == template_key)
                .order_by(AudioPromptAsset.version.desc())
                .limit(1)
            )
            latest_template_asset = existing_template_result.scalar_one_or_none()

            if (
                not force_regenerate
                and latest_template_asset
                and latest_template_asset.file_hash == asset_hash
                and latest_template_asset.status == "ready"
            ):
                logger.info(
                    "Found existing ready asset for %s: %s",
                    template_key,
                    latest_template_asset.id,
                )
                return latest_template_asset

            next_version = (
                (latest_template_asset.version + 1)
                if latest_template_asset is not None
                else 1
            )

            if not force_regenerate:
                existing_by_hash = await self._find_by_hash(
                    session=session,
                    file_hash=asset_hash,
                    status="ready",
                )
                if existing_by_hash:
                    asset = await self._create_or_update_asset(
                        session=session,
                        template_key=template_key,
                        category=category,
                        text=text,
                        file_hash=asset_hash,
                        job_id=job_id,
                        question_id=question_id,
                        provider=provider,
                        speaker=speaker,
                        language_code=language_code,
                        sample_rate=sample_rate,
                        codec=codec,
                        pace=pace,
                        status="ready",
                        version=next_version,
                    )
                    asset.file_path = existing_by_hash.file_path
                    asset.duration_ms = existing_by_hash.duration_ms
                    asset.last_generated_at = existing_by_hash.last_generated_at or self._utcnow()
                    session.add(asset)
                    await session.commit()
                    await session.refresh(asset)
                    logger.info(
                        "Reused existing ready audio by hash for %s as version %s",
                        template_key,
                        asset.version,
                    )
                    return asset

            # Create or update asset record with status=pending
            asset = await self._create_or_update_asset(
                session=session,
                template_key=template_key,
                category=category,
                text=text,
                file_hash=asset_hash,
                job_id=job_id,
                question_id=question_id,
                provider=provider,
                speaker=speaker,
                language_code=language_code,
                sample_rate=sample_rate,
                codec=codec,
                pace=pace,
                status="pending",
                version=next_version,
            )
            
            # Commit the pending asset to database
            await session.commit()
            await session.refresh(asset)
            
            # Synthesize and persist audio
            try:
                await self._synthesize_and_persist(asset)
                
                # Update status to ready
                asset.status = "ready"
                asset.last_generated_at = self._utcnow()
                
                logger.info(
                    f"Successfully generated audio for {template_key}: "
                    f"{asset.duration_ms}ms, {asset.file_path}"
                )
            except Exception as e:
                # Update status to failed
                asset.status = "failed"
                logger.error(
                    f"Audio generation failed for {template_key}: {e}",
                    exc_info=True,
                )
            
            # Save final status
            session.add(asset)
            await session.commit()
            await session.refresh(asset)
            
            return asset

    async def get_ready_audio_asset(
        self,
        *,
        template_key: str | None = None,
        job_id: uuid.UUID | None = None,
        question_id: uuid.UUID | None = None,
    ) -> AudioPromptAsset | None:
        """
        Retrieve a ready audio asset by lookup criteria.
        
        Queries the database for an audio asset matching the provided criteria.
        Only returns assets with status='ready'. Supports lookup by template_key,
        job_id, and/or question_id.
        
        Args:
            template_key: Optional template key to match (e.g., "opener_consent", "question_12345")
            job_id: Optional job ID to match (for job-specific assets)
            question_id: Optional question ID to match (for question assets)
            
        Returns:
            AudioPromptAsset instance if found and ready, None otherwise
            
        Requirements: 1.6, 2.7
        """
        async with self.session_factory() as session:
            # Build query with status=ready filter
            query = select(AudioPromptAsset).where(
                AudioPromptAsset.status == "ready"
            )
            
            # Add optional filters based on provided criteria
            if template_key is not None:
                query = query.where(AudioPromptAsset.template_key == template_key)
            
            if job_id is not None:
                query = query.where(AudioPromptAsset.job_id == job_id)
            
            if question_id is not None:
                query = query.where(AudioPromptAsset.question_id == question_id)
            
            # Order by version descending to get the latest version, limit to 1
            query = query.order_by(AudioPromptAsset.version.desc()).limit(1)

            # Execute query
            result = await session.execute(query)
            asset = result.scalar_one_or_none()
            
            if asset:
                logger.debug(
                    f"Found ready asset: template_key={template_key}, "
                    f"job_id={job_id}, question_id={question_id}, "
                    f"asset_id={asset.id}, version={asset.version}"
                )
            else:
                logger.debug(
                    f"No ready asset found: template_key={template_key}, "
                    f"job_id={job_id}, question_id={question_id}"
                )
            
            return asset

    async def ensure_question_audio_for_job(
        self,
        job_id: uuid.UUID,
        *,
        force_regenerate: bool = False,
    ) -> list[AudioPromptAsset]:
        assets: list[AudioPromptAsset] = []
        async with self.session_factory() as session:
            result = await session.execute(
                select(InterviewQuestion)
                .where(InterviewQuestion.job_id == job_id)
                .order_by(InterviewQuestion.order_index.asc(), InterviewQuestion.created_at.asc())
            )
            questions = list(result.scalars().all())

        for question in questions:
            if not question.question_text.strip():
                continue
            assets.append(
                await self.ensure_prompt_audio(
                    template_key=f"question_{question.id}",
                    category="question",
                    text=question.question_text,
                    job_id=job_id,
                    question_id=question.id,
                    force_regenerate=force_regenerate,
                )
            )
        return assets

    async def ensure_default_fillers(self, *, force_regenerate: bool = False) -> list[AudioPromptAsset]:
        assets: list[AudioPromptAsset] = []
        for template_key, text in DEFAULT_FILLER_TEXTS.items():
            assets.append(
                await self.ensure_prompt_audio(
                    template_key=template_key,
                    category="filler",
                    text=text,
                    force_regenerate=force_regenerate,
                )
            )
        return assets

    async def ensure_default_templates(
        self,
        *,
        categories: set[str] | None = None,
        force_regenerate: bool = False,
    ) -> list[AudioPromptAsset]:
        selected = {category.lower() for category in (categories or set())}
        include_all = not selected
        templates: list[tuple[str, str, str]] = []

        if include_all or "opener" in selected:
            templates.append(("opener_consent", "opener", DEFAULT_OPENER_TEXT))
        if include_all or "reprompt" in selected:
            templates.extend(
                (template_key, "reprompt", text)
                for template_key, text in DEFAULT_REPROMPT_TEXTS.items()
            )
        if include_all or "clarification" in selected:
            templates.extend(
                (template_key, "clarification", text)
                for template_key, text in DEFAULT_CLARIFICATION_TEXTS.items()
            )
        if include_all or "closing" in selected:
            templates.extend(
                (template_key, "closing", text)
                for template_key, text in DEFAULT_CLOSING_TEXTS.items()
            )

        assets: list[AudioPromptAsset] = []
        for template_key, category, text in templates:
            assets.append(
                await self.ensure_prompt_audio(
                    template_key=template_key,
                    category=category,
                    text=text,
                    force_regenerate=force_regenerate,
                )
            )
        if include_all or "filler" in selected:
            assets.extend(await self.ensure_default_fillers(force_regenerate=force_regenerate))
        return assets

    async def _synthesize_and_persist(self, asset: AudioPromptAsset) -> None:
        """
        Synthesize audio via TTS and persist to storage.

        This method handles the actual TTS synthesis and file storage.
        It updates the asset's file_path and duration_ms fields but does
        not commit to the database - the caller is responsible for that.

        Args:
            asset: AudioPromptAsset instance with text and synthesis config

        Raises:
            Exception: If synthesis or storage fails

        Requirements: 2.5, 2.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 20.1
        """
        logger.info(
            f"Synthesizing audio for {asset.template_key}: "
            f"speaker={asset.speaker}, pace={asset.pace}, language={asset.language_code}"
        )

        # Call Sarvam TTS API to synthesize audio
        # Note: We use "exotel" as telephony_provider to get linear16 PCM format
        try:
            audio_bytes = await self.tts.synthesize(
                text=asset.text,
                telephony_provider="exotel",  # Gets us linear16 PCM at 8kHz
            )
        except Exception as e:
            logger.error(f"TTS synthesis failed for {asset.template_key}: {e}")
            raise RuntimeError(f"TTS synthesis failed: {e}") from e

        if not audio_bytes:
            raise RuntimeError("TTS synthesis returned empty audio")

        logger.info(
            f"TTS synthesis complete for {asset.template_key}: {len(audio_bytes)} bytes"
        )

        # Calculate duration from audio length
        # For linear16 PCM: bytes = sample_rate * channels * bytes_per_sample * duration_seconds
        # We have: 8000 Hz, mono (1 channel), 16-bit (2 bytes per sample)
        # So: bytes = 8000 * 1 * 2 * duration_seconds = 16000 * duration_seconds
        bytes_per_second = asset.sample_rate * 2  # 2 bytes per sample for 16-bit
        duration_seconds = len(audio_bytes) / bytes_per_second
        duration_ms = int(duration_seconds * 1000)

        # Save audio bytes to storage
        # The file_path was already set in _create_or_update_asset
        # Format: prompt-audio/{category}/{version}/{hash}.pcm
        try:
            import io

            from fastapi import UploadFile

            audio_file = io.BytesIO(audio_bytes)
            upload_file = UploadFile(
                file=audio_file,
                filename=f"{asset.file_hash}.pcm",
            )

            full_path = await self.storage.save_file(
                file=upload_file,
                destination_path=asset.file_path,
            )

            logger.info(
                f"Audio file saved for {asset.template_key}: {full_path}"
            )
        except Exception as e:
            logger.error(f"Failed to save audio file for {asset.template_key}: {e}")
            raise RuntimeError(f"Failed to save audio file: {e}") from e

        asset.duration_ms = duration_ms

        logger.info(
            f"Audio persisted for {asset.template_key}: "
            f"duration={duration_ms}ms, path={asset.file_path}"
        )


def get_prompt_audio_service() -> PromptAudioService:
    from app.database import async_session_factory
    from app.services.storage import get_storage_provider

    return PromptAudioService(
        session_factory=async_session_factory,
        storage_provider=get_storage_provider(),
        tts_provider=get_tts_provider(),
    )
