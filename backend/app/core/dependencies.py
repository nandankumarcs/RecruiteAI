"""
FastAPI dependencies — reusable dependency injections.

Provides get_current_user for auth-protected routes and get_db for database sessions.
"""

from typing import Optional
from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

# OAuth2 scheme — expects "Authorization: Bearer <token>" header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that extracts and validates the current user from JWT token.

    Raises:
        AuthenticationError: If token is invalid, expired, or user not found.
    """
    payload = decode_token(token)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    # Ensure this is an access token, not a refresh token
    token_type = payload.get("type")
    if token_type != "access":
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token missing user identifier")

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    return user


async def get_current_user_from_query(
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency that extracts and validates the current user from JWT token in query parameter.
    Used for SSE endpoints where EventSource doesn't support custom headers.

    Raises:
        AuthenticationError: If token is invalid, expired, or user not found.
    """
    if not token:
        raise AuthenticationError("Token is required")
    
    payload = decode_token(token)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    # Ensure this is an access token, not a refresh token
    token_type = payload.get("type")
    if token_type != "access":
        raise AuthenticationError("Invalid token type")

    user_id = payload.get("sub")
    if user_id is None:
        raise AuthenticationError("Token missing user identifier")

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is inactive")

    return user
