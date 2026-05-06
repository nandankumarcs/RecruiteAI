"""
Auth Router — handles login, token refresh, and current user profile.

Endpoints:
  POST /api/auth/login   — Authenticate with email/password, returns JWT pair
  POST /api/auth/refresh — Exchange a refresh token for a new access token
  GET  /api/auth/me      — Get the current authenticated user's profile
"""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a user with email and password.
    Returns access + refresh JWT token pair on success.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is inactive")

    # Generate token pair
    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    The old refresh token is implicitly invalidated (stateless rotation).
    """
    payload = decode_token(request.refresh_token)
    if payload is None:
        raise AuthenticationError("Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type — expected refresh token")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token missing user identifier")

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    # Issue new token pair
    token_data = {"sub": str(user.id)}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user
