"""
Tests for the Jobs router CRUD endpoints.
"""

import pytest
from httpx import AsyncClient

from app.models.job import Job


@pytest.fixture
def mock_job_data():
    return {
        "title": "Senior Software Engineer",
        "description": "We are looking for a Python expert.",
        "requirements": "FastAPI, PostgreSQL, React",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_create_job(authenticated_client: AsyncClient, mock_job_data):
    """Test creating a new job."""
    response = await authenticated_client.post("/api/jobs", json=mock_job_data)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == mock_job_data["title"]
    assert "id" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_list_jobs(authenticated_client: AsyncClient, mock_job_data):
    """Test listing jobs for the current user."""
    # Create two jobs
    await authenticated_client.post("/api/jobs", json=mock_job_data)
    
    mock_job_data["title"] = "Frontend Developer"
    await authenticated_client.post("/api/jobs", json=mock_job_data)
    
    response = await authenticated_client.get("/api/jobs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    
    titles = [job["title"] for job in data]
    assert "Senior Software Engineer" in titles
    assert "Frontend Developer" in titles


@pytest.mark.asyncio
async def test_get_job(authenticated_client: AsyncClient, mock_job_data):
    """Test getting a specific job by ID."""
    create_resp = await authenticated_client.post("/api/jobs", json=mock_job_data)
    job_id = create_resp.json()["id"]
    
    response = await authenticated_client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["title"] == mock_job_data["title"]


@pytest.mark.asyncio
async def test_update_job(authenticated_client: AsyncClient, mock_job_data):
    """Test updating an existing job."""
    create_resp = await authenticated_client.post("/api/jobs", json=mock_job_data)
    job_id = create_resp.json()["id"]
    
    update_data = {"title": "Lead Software Engineer", "status": "paused"}
    response = await authenticated_client.put(f"/api/jobs/{job_id}", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Lead Software Engineer"
    assert data["status"] == "paused"
    assert data["description"] == mock_job_data["description"]  # Unchanged


@pytest.mark.asyncio
async def test_update_job_invalid_status(authenticated_client: AsyncClient, mock_job_data):
    """Test updating a job with invalid status fails validation."""
    create_resp = await authenticated_client.post("/api/jobs", json=mock_job_data)
    job_id = create_resp.json()["id"]
    
    update_data = {"status": "invalid_status"}
    response = await authenticated_client.put(f"/api/jobs/{job_id}", json=update_data)
    
    assert response.status_code == 422
    assert "Invalid status" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_job(authenticated_client: AsyncClient, mock_job_data):
    """Test deleting a job."""
    create_resp = await authenticated_client.post("/api/jobs", json=mock_job_data)
    job_id = create_resp.json()["id"]
    
    # Delete it
    del_resp = await authenticated_client.delete(f"/api/jobs/{job_id}")
    assert del_resp.status_code == 204
    
    # Try getting it again
    get_resp = await authenticated_client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_access_other_users_job(
    client: AsyncClient, authenticated_client: AsyncClient, db_session, test_user
):
    """Test that a user cannot access another user's job."""
    import uuid
    from app.core.security import hash_password
    from app.core.security import create_access_token
    from app.models.user import User
    
    # Create Job for user 1
    create_resp = await authenticated_client.post(
        "/api/jobs", 
        json={"title": "Secret Job", "description": "...", "status": "active"}
    )
    job_id = create_resp.json()["id"]
    
    # Create User 2
    user2 = User(
        email="otheruser@example.com",
        hashed_password=hash_password("Password123"),
        full_name="Other User",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(user2)
    
    # Login as User 2
    token2 = create_access_token({"sub": str(user2.id)})
    client.headers.update({"Authorization": f"Bearer {token2}"})
    
    # User 2 tries to GET User 1's job
    response = await client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 404  # Returns 404 instead of 403 to hide existence
