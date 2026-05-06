"""
Auth Pydantic schemas — request/response models for authentication endpoints.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Login request body."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token pair returned on successful login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request body."""
    refresh_token: str


class UserResponse(BaseModel):
    """User profile response — excludes password hash."""
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
