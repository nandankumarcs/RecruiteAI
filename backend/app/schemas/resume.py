"""Pydantic schemas for resume API responses."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ResumeBaseResponse(BaseModel):
    """Common resume fields returned by the API."""

    id: uuid.UUID
    job_id: uuid.UUID
    candidate_name: str | None
    phone_number: str | None
    email: str | None
    file_path: str
    file_type: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResumeResponse(ResumeBaseResponse):
    """List/upload response for resumes."""

    parsed_data: dict | None


class ResumeDetailResponse(ResumeResponse):
    """Detailed resume response including extracted text."""

    raw_text: str | None
