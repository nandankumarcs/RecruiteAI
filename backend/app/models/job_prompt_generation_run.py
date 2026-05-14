"""
JobPromptGenerationRun model — tracks bulk audio generation progress for job questions.

This optional model provides observability for the asynchronous process of generating
pre-generated audio assets for all questions in a job. It records success/failure counts
and error summaries for monitoring and debugging.

Requirements: 3.5, 14.5
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class JobPromptGenerationRun(Base):
    """
    Tracks bulk audio generation runs for job questions.
    
    This model provides observability when generating audio assets for all questions
    in a job. It records the run status, timing, success/failure counts, and error
    details for monitoring and debugging purposes.
    """
    
    __tablename__ = "job_prompt_generation_runs"

    # Primary identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Run status and timing
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
        # pending, in_progress, completed, failed
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Progress tracking
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job = relationship("Job", backref="prompt_generation_runs")

    def __repr__(self) -> str:
        return (
            f"<JobPromptGenerationRun job_id={self.job_id} "
            f"status={self.status} success={self.success_count} "
            f"failure={self.failure_count}>"
        )
