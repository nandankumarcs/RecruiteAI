"""Pydantic schemas for interview questions."""

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class InterviewQuestionBase(BaseModel):
    question_text: str
    category: str | None = "general"
    difficulty: int = 1
    order_index: int = 0

class InterviewQuestionCreate(InterviewQuestionBase):
    pass

class InterviewQuestionUpdate(BaseModel):
    question_text: str | None = None
    category: str | None = None
    difficulty: int | None = None
    order_index: int | None = None

class InterviewQuestionResponse(InterviewQuestionBase):
    """API response schema for a stored interview question."""

    id: uuid.UUID
    job_id: uuid.UUID
    resume_id: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedQuestionSetResponse(BaseModel):
    """Response for question generation/listing endpoints."""

    schema_version: str = "questions.v1"
    questions: list[InterviewQuestionResponse]
