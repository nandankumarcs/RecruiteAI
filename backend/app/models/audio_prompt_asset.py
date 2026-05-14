"""
AudioPromptAsset model — pre-generated TTS audio for stable recruiter prompts.

This model stores metadata for pre-generated audio files used to reduce live-call
latency. Audio assets can be global templates (opener, reprompts, closers) or
job-specific (interview questions).

Requirements: 1.1, 1.2, 1.3, 1.6, 12.1, 12.2, 16.7, 17.5
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AudioPromptAsset(Base):
    """
    Pre-generated audio asset for recruiter prompts.
    
    Supports both global templates (opener, reprompts, fillers, closers) and
    job-specific assets (interview questions). Uses versioning to allow prompt
    text updates without breaking existing calls.
    """
    
    __tablename__ = "audio_prompt_assets"

    # Primary identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_key: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
        # opener, question, reprompt, clarification, off_topic_redirect, closing, filler
    )

    # Content
    text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    # Synthesis configuration
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="sarvam")
    speaker: Mapped[str] = mapped_column(String(50), nullable=False, default="priya")
    language_code: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en-IN"
    )
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=8000)
    codec: Mapped[str] = mapped_column(String(20), nullable=False, default="linear16")
    pace: Mapped[float] = mapped_column(Float, nullable=False, default=1.2)

    # Job/question association (nullable for global templates)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_questions.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Lifecycle
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
        # pending, ready, failed
    )
    last_generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    job = relationship("Job", backref="audio_prompt_assets")
    question = relationship("InterviewQuestion", backref="audio_prompt_assets")

    # Table constraints and indexes
    __table_args__ = (
        # Composite unique constraint on (template_key, version)
        UniqueConstraint("template_key", "version", name="uq_template_key_version"),
        # Composite index for job/question lookups
        Index("idx_job_question", "job_id", "question_id"),
    )

    def __repr__(self) -> str:
        return f"<AudioPromptAsset {self.template_key} v{self.version} [{self.status}]>"
