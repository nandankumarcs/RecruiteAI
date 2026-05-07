"""Call model for phone interview calls, runtime metrics, and cost observability."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    resume_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resumes.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), default="twilio")
    voice_runtime: Mapped[str] = mapped_column(String(100), default="openai_realtime")
    provider_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    twilio_call_sid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
        # pending, ringing, in_progress, completed, failed, no_answer
    )
    phone_number: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recording_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cost_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ai_evaluation schema:
    # {
    #   overall_score: int (1-10),
    #   categories: {technical: int, communication: int, experience: int},
    #   remarks: str,
    #   strengths: [str],
    #   weaknesses: [str]
    # }
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    resume = relationship("Resume", back_populates="calls")
    job = relationship("Job", back_populates="calls")
    messages = relationship(
        "CallMessage", back_populates="call", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Call {self.phone_number} ({self.status})>"
