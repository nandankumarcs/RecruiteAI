"""API tests for interview question generation and listing."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.agents.question_generator_agent import (
    GeneratedQuestion,
    QuestionGenerationResult,
    get_question_generator_agent,
)
from app.main import app
from app.models.job import Job
from app.models.resume import Resume


class FakeQuestionGeneratorAgent:
    """Deterministic question generator for endpoint tests."""

    async def generate_questions(self, job: Job, resume: Resume) -> QuestionGenerationResult:
        return QuestionGenerationResult(
            schema_version="questions.v1",
            questions=[
                GeneratedQuestion(
                    question_text=f"Why are you a fit for {job.title}?",
                    category="introduction",
                    difficulty=1,
                    order_index=1,
                ),
                GeneratedQuestion(
                    question_text=f"Walk me through your strongest project relevant to {job.title}.",
                    category="project",
                    difficulty=3,
                    order_index=2,
                ),
            ],
        )


@pytest_asyncio.fixture(autouse=True)
async def override_question_generator():
    """Use a local fake generator for question endpoint tests."""
    app.dependency_overrides[get_question_generator_agent] = lambda: FakeQuestionGeneratorAgent()
    yield
    app.dependency_overrides.pop(get_question_generator_agent, None)


@pytest_asyncio.fixture
async def job_with_parsed_resume(db_session, test_user) -> tuple[Job, Resume]:
    """Create a parsed resume that can generate interview questions."""
    job = Job(
        user_id=test_user.id,
        title="AI Engineer",
        description="Build AI interview tooling.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Jane Candidate",
        phone_number="+1 222 333 4444",
        email="jane@example.com",
        file_path="/tmp/jane.pdf",
        file_type="pdf",
        raw_text="Jane Candidate",
        status="parsed",
        parsed_data={"summary": "AI engineer", "skills": ["Python", "FastAPI"]},
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(job)
    await db_session.refresh(resume)
    return job, resume


@pytest.mark.asyncio
async def test_generate_questions(
    authenticated_client: AsyncClient,
    job_with_parsed_resume: tuple[Job, Resume],
):
    """Generating questions should persist and return a question set."""
    _job, resume = job_with_parsed_resume

    response = await authenticated_client.post(
        f"/api/resumes/{resume.id}/questions/generate"
    )

    assert response.status_code == 201
    data = response.json()
    assert data["schema_version"] == "questions.v1"
    assert len(data["questions"]) == 2
    assert data["questions"][0]["order_index"] == 1
    assert data["questions"][1]["category"] == "project"


@pytest.mark.asyncio
async def test_list_questions(
    authenticated_client: AsyncClient,
    job_with_parsed_resume: tuple[Job, Resume],
):
    """Listing should return previously generated questions in order."""
    _job, resume = job_with_parsed_resume
    await authenticated_client.post(f"/api/resumes/{resume.id}/questions/generate")

    response = await authenticated_client.get(f"/api/resumes/{resume.id}/questions")

    assert response.status_code == 200
    data = response.json()
    assert [question["order_index"] for question in data["questions"]] == [1, 2]


@pytest.mark.asyncio
async def test_generate_questions_replaces_existing_set(
    authenticated_client: AsyncClient,
    job_with_parsed_resume: tuple[Job, Resume],
):
    """Regeneration should replace the old set instead of duplicating questions."""
    _job, resume = job_with_parsed_resume

    await authenticated_client.post(f"/api/resumes/{resume.id}/questions/generate")
    await authenticated_client.post(f"/api/resumes/{resume.id}/questions/generate")

    response = await authenticated_client.get(f"/api/resumes/{resume.id}/questions")
    assert response.status_code == 200
    assert len(response.json()["questions"]) == 2


@pytest.mark.asyncio
async def test_generate_questions_requires_parsed_resume(
    authenticated_client: AsyncClient,
    db_session,
    test_user,
):
    """Question generation should reject resumes that are not parsed yet."""
    job = Job(
        user_id=test_user.id,
        title="Backend Engineer",
        description="Build APIs.",
        requirements="FastAPI",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Not Parsed Yet",
        phone_number="+1 222 333 4444",
        email="pending@example.com",
        file_path="/tmp/pending.pdf",
        file_type="pdf",
        raw_text=None,
        status="uploaded",
        parsed_data=None,
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)

    response = await authenticated_client.post(
        f"/api/resumes/{resume.id}/questions/generate"
    )

    assert response.status_code == 422
    assert "parsed resumes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_access_other_users_questions(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    db_session,
    test_user,
):
    """Question endpoints should remain scoped to the job owner."""
    from app.core.security import create_access_token, hash_password
    from app.models.user import User

    job = Job(
        user_id=test_user.id,
        title="Private AI Role",
        description="Hidden",
        requirements="Python",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Private Candidate",
        phone_number="+1 222 333 4444",
        email="private@example.com",
        file_path="/tmp/private.pdf",
        file_type="pdf",
        raw_text="Private Candidate",
        status="parsed",
        parsed_data={"summary": "private"},
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(resume)

    user2 = User(
        id=uuid.uuid4(),
        email="question-other@example.com",
        hashed_password=hash_password("Password123"),
        full_name="Other Question User",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()

    token2 = create_access_token({"sub": str(user2.id)})
    client.headers.update({"Authorization": f"Bearer {token2}"})

    response = await client.get(f"/api/resumes/{resume.id}/questions")
    assert response.status_code == 404
