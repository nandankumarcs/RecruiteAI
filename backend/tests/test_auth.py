"""
Auth endpoint tests — TDD tests for login, refresh, and me endpoints.

Tests cover:
- Successful login with valid credentials
- Failed login with wrong password
- Failed login with non-existent email
- Token refresh flow
- Get current user profile
- Protected route access without token
- Inactive user cannot login
"""

import pytest
from httpx import AsyncClient

from app.core.security import create_refresh_token, hash_password
from app.models.user import User


# ─── Login Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    """Should return access + refresh tokens for valid credentials."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "testuser@example.com", "password": "TestPassword@123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    """Should return 401 for incorrect password."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "testuser@example.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Should return 401 for email that doesn't exist."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db_session):
    """Should return 401 for an inactive user account."""
    # Create an inactive user
    user = User(
        email="inactive@example.com",
        hashed_password=hash_password("Password@123"),
        full_name="Inactive User",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/auth/login",
        json={"email": "inactive@example.com", "password": "Password@123"},
    )
    assert response.status_code == 401
    assert "inactive" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_login_invalid_email_format(client: AsyncClient):
    """Should return 422 for malformed email."""
    response = await client.post(
        "/api/auth/login",
        json={"email": "not-an-email", "password": "anything"},
    )
    assert response.status_code == 422


# ─── Token Refresh Tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, test_user: User):
    """Should return new token pair for a valid refresh token."""
    refresh_token = create_refresh_token({"sub": str(test_user.id)})

    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient):
    """Should return 401 for an invalid refresh token."""
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": "invalid-token-string"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_access_token_rejected(
    client: AsyncClient, test_user: User
):
    """Should reject an access token used as a refresh token."""
    # Login to get an access token
    login_resp = await client.post(
        "/api/auth/login",
        json={"email": "testuser@example.com", "password": "TestPassword@123"},
    )
    access_token = login_resp.json()["access_token"]

    # Try to use access token as refresh token — should fail
    response = await client.post(
        "/api/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert response.status_code == 401
    assert "refresh" in response.json()["detail"].lower()


# ─── Get Current User Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_me_success(client: AsyncClient, test_user: User, auth_headers: dict):
    """Should return the authenticated user's profile."""
    response = await client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "testuser@example.com"
    assert data["full_name"] == "Test User"
    assert "hashed_password" not in data  # Password should never be exposed


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient):
    """Should return 401 when no auth token is provided."""
    response = await client.get("/api/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient):
    """Should return 401 for an invalid/expired token."""
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


# ─── Health Check ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Health endpoint should return OK without auth."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
