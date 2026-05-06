"""API tests for call initiation and retrieval."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

from app.agents.question_generator_agent import (
    GeneratedQuestion,
    QuestionGenerationResult,
    get_question_generator_agent,
)
from app.main import app
from app.models.call import Call
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.services.telephony import OutboundCallResult, get_telephony_service


class FakeQuestionGeneratorAgent:
    async def generate_questions(self, job: Job, resume: Resume) -> QuestionGenerationResult:
        return QuestionGenerationResult(
            schema_version="questions.v1",
            questions=[
                GeneratedQuestion(
                    question_text="Tell me about your background.",
                    category="introduction",
                    difficulty=1,
                    order_index=1,
                ),
                GeneratedQuestion(
                    question_text="Walk me through a relevant project.",
                    category="project",
                    difficulty=3,
                    order_index=2,
                ),
            ],
        )


class FakeTelephonyService:
    def start_outbound_call(self, *, to_number: str, twiml_url: str, status_callback_url: str):
        assert to_number
        assert "/webhooks/twilio/voice?call_resume_id=" in twiml_url
        assert status_callback_url.endswith("/webhooks/twilio/status")
        return OutboundCallResult(
            call_sid="CA_TEST_CALL_SID",
            status="queued",
            provider="mock",
        )


@pytest_asyncio.fixture(autouse=True)
async def override_phase5_deps():
    app.dependency_overrides[get_question_generator_agent] = lambda: FakeQuestionGeneratorAgent()
    app.dependency_overrides[get_telephony_service] = lambda: FakeTelephonyService()
    yield
    app.dependency_overrides.pop(get_question_generator_agent, None)
    app.dependency_overrides.pop(get_telephony_service, None)


@pytest_asyncio.fixture
async def parsed_resume_for_calls(db_session, test_user) -> tuple[Job, Resume]:
    job = Job(
        user_id=test_user.id,
        title="AI Engineer",
        description="Build interview tooling.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Call Candidate",
        phone_number="+1 333 444 5555",
        email="call@example.com",
        file_path="/tmp/call.pdf",
        file_type="pdf",
        raw_text="Call Candidate",
        status="parsed",
        parsed_data={"summary": "AI engineer", "skills": ["Python", "FastAPI"]},
    )
    db_session.add(resume)
    await db_session.commit()
    await db_session.refresh(job)
    await db_session.refresh(resume)
    return job, resume


@pytest.mark.asyncio
async def test_start_call_generates_questions_and_creates_call(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    _job, resume = parsed_resume_for_calls

    response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    assert response.status_code == 201
    data = response.json()
    assert data["provider"] == "mock"
    assert data["call"]["status"] == "queued"
    assert data["call"]["twilio_call_sid"] == "CA_TEST_CALL_SID"


@pytest.mark.asyncio
async def test_start_call_reuses_existing_questions(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
    db_session,
):
    job, resume = parsed_resume_for_calls
    db_session.add(
        InterviewQuestion(
            job_id=job.id,
            resume_id=resume.id,
            question_text="Existing question",
            category="technical",
            difficulty=2,
            order_index=1,
        )
    )
    await db_session.commit()

    response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    assert response.status_code == 201
    question_count = await db_session.scalar(
        select(func.count(InterviewQuestion.id)).where(InterviewQuestion.resume_id == resume.id)
    )
    assert question_count == 1


@pytest.mark.asyncio
async def test_start_call_rejects_unparsed_resume(
    authenticated_client: AsyncClient,
    db_session,
    test_user,
):
    job = Job(
        user_id=test_user.id,
        title="Backend Engineer",
        description="Build APIs",
        requirements="FastAPI",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Pending Candidate",
        phone_number="+1 333 444 5555",
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

    response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    assert response.status_code == 422
    assert "parsed resumes" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_calls_for_job(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    response = await authenticated_client.get(f"/api/jobs/{job.id}/calls")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["phone_number"] == "+1 333 444 5555"


@pytest.mark.asyncio
async def test_get_call_detail(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    _job, resume = parsed_resume_for_calls
    create_response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")
    call_id = create_response.json()["call"]["id"]

    response = await authenticated_client.get(f"/api/calls/{call_id}")

    assert response.status_code == 200
    assert response.json()["id"] == call_id


@pytest.mark.asyncio
async def test_cannot_start_second_active_call(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    _job, resume = parsed_resume_for_calls
    await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cannot_access_other_users_call(
    client: AsyncClient,
    authenticated_client: AsyncClient,
    db_session,
    test_user,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    from app.core.security import create_access_token, hash_password
    from app.models.user import User

    _job, resume = parsed_resume_for_calls
    create_response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")
    call_id = create_response.json()["call"]["id"]

    user2 = User(
        id=uuid.uuid4(),
        email="call-other@example.com",
        hashed_password=hash_password("Password123"),
        full_name="Other Call User",
        is_active=True,
    )
    db_session.add(user2)
    await db_session.commit()

    token2 = create_access_token({"sub": str(user2.id)})
    client.headers.update({"Authorization": f"Bearer {token2}"})

    response = await client.get(f"/api/calls/{call_id}")
    assert response.status_code == 404
