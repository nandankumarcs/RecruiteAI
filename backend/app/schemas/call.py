"""Pydantic schemas for call initiation and retrieval."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallResponse(BaseModel):
    """API response schema for a call record."""

    id: uuid.UUID
    resume_id: uuid.UUID
    job_id: uuid.UUID
    provider: str
    voice_runtime: str
    provider_call_id: str | None
    twilio_call_sid: str | None
    status: str
    phone_number: str
    duration_seconds: int | None
    recording_url: str | None
    recording_path: str | None
    transcript: str | None
    ai_evaluation: dict | None
    cost_breakdown: dict | None
    latency_metrics: dict | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallStartResponse(BaseModel):
    """Response for call initiation."""

    provider: str
    call: CallResponse


class CallEvaluationResponse(BaseModel):
    """Response for a stored call evaluation."""

    schema_version: str
    overall_score: int
    technical_score: int
    communication_score: int
    experience_score: int
    remarks: str
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str
