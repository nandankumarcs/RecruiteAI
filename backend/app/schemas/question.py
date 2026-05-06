"""Pydantic schemas for generated interview questions."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InterviewQuestionResponse(BaseModel):
    """API response schema for a stored interview question."""

    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID
    question_text: str
    category: str | None
    difficulty: int
    order_index: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedQuestionSetResponse(BaseModel):
    """Response for question generation/listing endpoints."""

    schema_version: str = "questions.v1"
    questions: list[InterviewQuestionResponse]
