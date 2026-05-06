"""
Resume model — stores uploaded candidate resumes and parsed data.
Linked to a job; stores both the raw file reference and extracted structured data.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    candidate_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf, docx
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # parsed_data schema: {skills:[], experience:[], education:[], summary:str}
    status: Mapped[str] = mapped_column(
        String(50), default="uploaded"  # uploaded, parsing, parsed, error
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job = relationship("Job", back_populates="resumes")
    calls = relationship("Call", back_populates="resume", cascade="all, delete-orphan")
    questions = relationship(
        "InterviewQuestion", back_populates="resume", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Resume {self.candidate_name or 'Unknown'} ({self.file_type})>"
