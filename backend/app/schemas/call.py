"""Pydantic schemas for call initiation and retrieval."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CallMessageResponse(BaseModel):
    """API response schema for a single message in a call."""

    id: uuid.UUID
    role: str
    content: str
    sequence_number: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    messages: list[CallMessageResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginatedCallsResponse(BaseModel):
    """Paginated response for call list with summary stats."""

    items: list[CallResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    completed_count: int
    active_calls: list[CallResponse]


class CallStartResponse(BaseModel):
    """Response for call initiation."""

    provider: str
    call: CallResponse
    # Populated when the configured telephony provider is the browser simulator —
    # the URL the dashboard should open so the candidate can "take the call".
    join_url: str | None = None


class CallEvaluationResponse(BaseModel):
    """Response for a stored call evaluation."""

    schema_version: str
    status: str
    confidence: str
    overall_score: int | None
    technical_score: int | None
    communication_score: int | None
    experience_score: int | None
    behavioral_score: int | None = None
    behavioral_summary: str | None = None
    remarks: str
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str


class CallStartRequest(BaseModel):
    """Request body for starting a call."""

    phone_number: str | None = None
