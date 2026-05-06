"""
Job Pydantic schemas — request/response models for Job endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobBase(BaseModel):
    """Base fields shared across Job schemas."""
    title: str = Field(..., max_length=255, description="The job title")
    description: str = Field(..., description="Full job description")
    requirements: str | None = Field(None, description="Job requirements / qualifications")
    status: str = Field("active", description="Status: active, paused, closed")


class JobCreate(JobBase):
    """Schema for creating a new job."""
    pass


class JobUpdate(BaseModel):
    """Schema for updating an existing job. All fields are optional."""
    title: str | None = Field(None, max_length=255)
    description: str | None = None
    requirements: str | None = None
    status: str | None = None


class JobResponse(JobBase):
    """Schema for returning job data."""
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
