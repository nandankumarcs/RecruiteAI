"""API tests for call initiation and retrieval."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select

import app.routers.calls as calls_router_module
from app.agents.question_generator_agent import (
    GeneratedQuestion,
    QuestionGenerationResult,
    get_question_generator_agent,
)
from app.agents.evaluation_agent import get_evaluation_agent
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
    def __init__(self):
        self.ended_call_sids: list[str] = []
        self.redirected_calls: list[tuple[str, str]] = []

    def start_outbound_call(
        self,
        *,
        to_number: str,
        twiml_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ):
        assert to_number
        assert "/webhooks/twilio/voice?call_resume_id=" in twiml_url
        assert status_callback_url.endswith("/webhooks/twilio/status")
        assert recording_callback_url is not None
        assert recording_callback_url.endswith("/webhooks/twilio/recording")
        return OutboundCallResult(
            call_sid="CA_TEST_CALL_SID",
            status="queued",
            provider="mock",
        )

    def end_call(self, call_sid: str):
        self.ended_call_sids.append(call_sid)

    def say_and_hangup(self, call_sid: str, message: str):
        self.redirected_calls.append((call_sid, message))


class FakeEvaluationAgent:
    async def evaluate_call(self, *, call: Call, job: Job, resume: Resume):
        from app.agents.evaluation_agent import EvaluationResult

        return EvaluationResult(
            overall_score=8,
            technical_score=8,
            communication_score=7,
            experience_score=8,
            remarks="Strong match for the role based on the transcript.",
            strengths=["Clear technical examples", "Good role alignment"],
            weaknesses=["Could provide more depth on trade-offs"],
            recommendation="advance",
        )


@pytest_asyncio.fixture(autouse=True)
async def override_phase5_deps():
    app.dependency_overrides[get_question_generator_agent] = lambda: FakeQuestionGeneratorAgent()
    fake_telephony = FakeTelephonyService()
    app.dependency_overrides[get_telephony_service] = lambda: fake_telephony
    app.dependency_overrides[get_evaluation_agent] = lambda: FakeEvaluationAgent()
    yield
    app.dependency_overrides.pop(get_question_generator_agent, None)
    app.dependency_overrides.pop(get_telephony_service, None)
    app.dependency_overrides.pop(get_evaluation_agent, None)


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


@pytest.mark.asyncio
async def test_evaluate_call(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
    db_session,
):
    job, resume = parsed_resume_for_calls
    create_response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")
    call_id = create_response.json()["call"]["id"]

    call = await db_session.get(Call, call_id)
    call.transcript = (
        "AI: Tell me about your experience.\n"
        "Candidate: I built Python and FastAPI systems for AI workflows."
    )
    call.status = "completed"
    await db_session.commit()

    response = await authenticated_client.post(f"/api/calls/{call_id}/evaluate")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "evaluation.v1"
    assert data["overall_score"] == 8


@pytest.mark.asyncio
async def test_completed_status_callback_auto_evaluates_when_transcript_exists(
    client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_AUTO_EVAL_STATUS",
        status="in_progress",
        phone_number=resume.phone_number,
        transcript=(
            "Assistant: Tell me about your experience.\n"
            "User: I have built AI systems with Python and FastAPI."
        ),
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/twilio/status",
        data={
            "CallSid": "CA_AUTO_EVAL_STATUS",
            "CallStatus": "completed",
            "CallDuration": "55",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.ai_evaluation is not None
    assert call.ai_evaluation["schema_version"] == "evaluation.v1"
    assert isinstance(call.ai_evaluation["overall_score"], int)


@pytest.mark.asyncio
async def test_evaluate_call_requires_transcript(
    authenticated_client: AsyncClient,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    _job, resume = parsed_resume_for_calls
    create_response = await authenticated_client.post(f"/api/resumes/{resume.id}/calls/start")
    call_id = create_response.json()["call"]["id"]

    response = await authenticated_client.post(f"/api/calls/{call_id}/evaluate")

    assert response.status_code == 422
    assert "transcript" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_twilio_status_callback_persists_duration_and_recording(
    client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_STATUS_TEST",
        status="queued",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/twilio/status",
        data={
            "CallSid": "CA_STATUS_TEST",
            "CallStatus": "completed",
            "CallDuration": "42",
            "RecordingUrl": "https://api.twilio.test/recordings/abc",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.duration_seconds == 42
    assert call.recording_url == "https://api.twilio.test/recordings/abc"


@pytest.mark.asyncio
async def test_twilio_answered_status_maps_to_in_progress(
    client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_ANSWERED_TEST",
        status="queued",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/twilio/status",
        data={
            "CallSid": "CA_ANSWERED_TEST",
            "CallStatus": "answered",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "in_progress"


@pytest.mark.asyncio
async def test_twilio_recording_callback_persists_recording_metadata(
    client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_RECORDING_TEST",
        status="in_progress",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/twilio/recording",
        data={
            "CallSid": "CA_RECORDING_TEST",
            "RecordingStatus": "completed",
            "RecordingUrl": "https://api.twilio.test/recordings/final",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.recording_url == "https://api.twilio.test/recordings/final"
    assert call.recording_path == "https://api.twilio.test/recordings/final"
    assert call.status == "completed"


@pytest.mark.asyncio
async def test_recording_callback_auto_evaluates_completed_call(
    client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_AUTO_EVAL_RECORDING",
        status="in_progress",
        phone_number=resume.phone_number,
        transcript=(
            "Assistant: Walk me through a project.\n"
            "User: I built a retrieval system with LangChain and FAISS."
        ),
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/twilio/recording",
        data={
            "CallSid": "CA_AUTO_EVAL_RECORDING",
            "RecordingStatus": "completed",
            "RecordingUrl": "https://api.twilio.test/recordings/final",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.ai_evaluation is not None
    assert call.ai_evaluation["schema_version"] == "evaluation.v1"
    assert isinstance(call.ai_evaluation["overall_score"], int)


@pytest.mark.asyncio
async def test_get_call_recording_proxies_audio(
    authenticated_client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
    monkeypatch,
):
    job, resume = parsed_resume_for_calls
    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_RECORDING_PROXY",
        status="completed",
        phone_number=resume.phone_number,
        recording_url="https://api.twilio.test/recordings/final",
    )
    db_session.add(call)
    await db_session.commit()

    monkeypatch.setattr(calls_router_module.settings, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(calls_router_module.settings, "TWILIO_AUTH_TOKEN", "token123")

    class FakeRecordingResponse:
        content = b"fake-audio"
        headers = {"content-type": "audio/mpeg"}

        def raise_for_status(self):
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            assert url == "https://api.twilio.test/recordings/final.mp3"
            return FakeRecordingResponse()

    monkeypatch.setattr(calls_router_module.httpx, "AsyncClient", FakeAsyncClient)

    response = await authenticated_client.get(f"/api/calls/{call.id}/recording")

    assert response.status_code == 200
    assert response.content == b"fake-audio"
    assert response.headers["content-type"].startswith("audio/mpeg")


@pytest.mark.asyncio
async def test_dashboard_metrics_include_call_stats(
    authenticated_client: AsyncClient,
    db_session,
    parsed_resume_for_calls: tuple[Job, Resume],
):
    job, resume = parsed_resume_for_calls
    db_session.add_all(
        [
            Call(
                resume_id=resume.id,
                job_id=job.id,
                twilio_call_sid="CA_DASH_1",
                status="completed",
                phone_number=resume.phone_number,
                ai_evaluation={"overall_score": 8},
            ),
            Call(
                resume_id=resume.id,
                job_id=job.id,
                twilio_call_sid="CA_DASH_2",
                status="in_progress",
                phone_number=resume.phone_number,
            ),
        ]
    )
    await db_session.commit()

    response = await authenticated_client.get("/api/dashboard/metrics")

    assert response.status_code == 200
    data = response.json()
    assert data["total_jobs"] == 1
    assert data["active_jobs"] == 1
    assert data["total_calls"] == 2
    assert data["active_calls"] == 1
    assert data["completed_calls"] == 1
    assert data["average_score"] == 8.0


@pytest.mark.asyncio
async def test_voice_webhook_includes_stream_status_callback(client: AsyncClient):
    response = await client.post(
        "/webhooks/twilio/voice",
        params={"call_resume_id": str(uuid.uuid4())},
    )

    assert response.status_code == 200
    body = response.text
    assert "/webhooks/twilio/stream-status" in body
    assert "/ws/twilio-media/" in body
