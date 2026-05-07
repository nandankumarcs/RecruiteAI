"""
Calls Router — start and inspect interview calls.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_generator_agent import (
    QuestionGeneratorAgent,
    get_question_generator_agent,
)
from app.agents.evaluation_agent import EvaluationAgent, get_evaluation_agent
from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.exceptions import CallInProgressError, NotFoundError, ValidationError
from app.database import async_session_factory, get_db
from app.models.call import Call
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.models.user import User
from app.schemas.call import CallEvaluationResponse, CallResponse, CallStartResponse
from app.services.call_evaluation import auto_evaluate_call_if_ready
from app.services.telephony import TelephonyService, get_telephony_service

settings = get_settings()

router = APIRouter(tags=["calls"])


MOCK_CALL_STEPS = [
    ("ringing", 2),
    ("in_progress", 3),
    ("completed", 4),
]


def _call_snapshot(call: Call) -> dict:
    return {
        "id": str(call.id),
        "resume_id": str(call.resume_id),
        "job_id": str(call.job_id),
        "twilio_call_sid": call.twilio_call_sid,
        "status": call.status,
        "phone_number": call.phone_number,
        "duration_seconds": call.duration_seconds,
        "recording_url": call.recording_url,
        "recording_path": call.recording_path,
        "transcript": call.transcript,
        "ai_evaluation": call.ai_evaluation,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "created_at": call.created_at.isoformat() if call.created_at else None,
    }


async def _simulate_mock_call_progress(call_id: uuid.UUID) -> None:
    for status, delay_seconds in MOCK_CALL_STEPS:
        await asyncio.sleep(delay_seconds)
        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            if call.status not in {"queued", "ringing", "in_progress"}:
                return

            call.status = status
            if status == "in_progress" and call.started_at is None:
                from datetime import datetime, timezone

                call.started_at = datetime.now(timezone.utc)
            if status == "completed":
                from datetime import datetime, timezone

                call.ended_at = datetime.now(timezone.utc)
                call.duration_seconds = max(
                    1,
                    int((call.ended_at - (call.started_at or call.created_at)).total_seconds()),
                )
                if not call.transcript:
                    call.transcript = (
                        "AI: Thanks for taking the time to speak with us today.\n"
                        "Candidate: Happy to be here.\n"
                        "AI: Tell me about your recent experience building AI systems.\n"
                        "Candidate: I worked on production-style RAG workflows using Python, FastAPI, FAISS, and LangChain.\n"
                        "AI: What trade-offs did you have to manage?\n"
                        "Candidate: I balanced retrieval quality, chunk sizing, and response latency to keep the experience useful and fast."
                    )
            await session.commit()
        if status == "completed":
            await auto_evaluate_call_if_ready(call_id)


async def _get_owned_resume(
    resume_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> tuple[Resume, Job]:
    result = await db.execute(
        select(Resume, Job)
        .join(Job, Resume.job_id == Job.id)
        .where(Resume.id == resume_id, Job.user_id == current_user.id)
    )
    row = result.one_or_none()
    if not row:
        raise NotFoundError(resource="Resume")
    return row


async def _ensure_questions(
    *,
    db: AsyncSession,
    job: Job,
    resume: Resume,
    generator: QuestionGeneratorAgent,
) -> None:
    existing = await db.execute(
        select(InterviewQuestion.id).where(InterviewQuestion.resume_id == resume.id).limit(1)
    )
    if existing.first():
        return

    generated = await generator.generate_questions(job, resume)
    if not generated.questions:
        raise ValidationError("No interview questions could be generated for this resume.")

    for item in generated.questions:
        db.add(
            InterviewQuestion(
                job_id=job.id,
                resume_id=resume.id,
                question_text=item.question_text,
                category=item.category,
                difficulty=item.difficulty,
                order_index=item.order_index,
            )
        )
    await db.flush()


@router.post("/api/resumes/{resume_id}/calls/start", response_model=CallStartResponse, status_code=201)
async def start_call(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    generator: QuestionGeneratorAgent = Depends(get_question_generator_agent),
    telephony: TelephonyService = Depends(get_telephony_service),
):
    """Generate questions if needed, create a call record, and initiate outbound telephony."""
    resume, job = await _get_owned_resume(resume_id, db, current_user)

    if resume.status != "parsed":
        raise ValidationError("Calls can only be started for parsed resumes.")
    if not resume.phone_number:
        raise ValidationError("Resume is missing a candidate phone number.")

    active_call = await db.execute(
        select(Call.id).where(
            Call.resume_id == resume.id,
            Call.status.in_(["pending", "queued", "ringing", "in_progress"]),
        ).limit(1)
    )
    if active_call.first():
        raise CallInProgressError()

    await _ensure_questions(db=db, job=job, resume=resume, generator=generator)

    twiml_url = f"{settings.PUBLIC_URL}/webhooks/twilio/voice?call_resume_id={resume.id}"
    status_callback_url = f"{settings.PUBLIC_URL}/webhooks/twilio/status"
    recording_callback_url = f"{settings.PUBLIC_URL}/webhooks/twilio/recording"
    outbound = telephony.start_outbound_call(
        to_number=resume.phone_number,
        twiml_url=twiml_url,
        status_callback_url=status_callback_url,
        recording_callback_url=recording_callback_url,
    )

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid=outbound.call_sid,
        status=outbound.status,
        phone_number=resume.phone_number,
    )
    db.add(call)
    await db.flush()
    await db.refresh(call)

    if getattr(telephony, "enable_mock_progression", False) and outbound.provider == "mock":
        asyncio.create_task(_simulate_mock_call_progress(call.id))

    return CallStartResponse(provider=outbound.provider, call=call)


@router.get("/api/jobs/{job_id}/calls", response_model=list[CallResponse])
async def list_calls(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List call records for a job owned by the current user."""
    owned_job = await db.execute(
        select(Job.id).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not owned_job.scalar_one_or_none():
        raise NotFoundError(resource="Job")

    result = await db.execute(
        select(Call)
        .where(Call.job_id == job_id)
        .order_by(Call.created_at.desc())
    )
    return result.scalars().all()


@router.get("/api/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one call record scoped to the owning user."""
    result = await db.execute(
        select(Call)
        .join(Job, Call.job_id == Job.id)
        .where(Call.id == call_id, Job.user_id == current_user.id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(resource="Call")
    return call


@router.get("/api/calls/{call_id}/recording")
async def get_call_recording(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Proxy a Twilio recording for authenticated frontend playback."""
    result = await db.execute(
        select(Call)
        .join(Job, Call.job_id == Job.id)
        .where(Call.id == call_id, Job.user_id == current_user.id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(resource="Call")
    if not call.recording_url:
        raise NotFoundError(resource="Recording")

    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise ValidationError("Twilio credentials are not configured for recording playback.")

    recording_url = call.recording_url
    if not recording_url.endswith(".mp3") and not recording_url.endswith(".wav"):
        recording_url = f"{recording_url}.mp3"

    async with httpx.AsyncClient(
        auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
        follow_redirects=True,
        timeout=30,
    ) as client:
        recording_response = await client.get(recording_url)
        recording_response.raise_for_status()

    return Response(
        content=recording_response.content,
        media_type=recording_response.headers.get("content-type", "audio/mpeg"),
    )


@router.websocket("/ws/calls/{call_id}")
async def call_status_websocket(websocket: WebSocket, call_id: uuid.UUID):
    """Stream call status updates over WebSocket for live progress UI."""
    await websocket.accept()
    try:
        while True:
            async with async_session_factory() as session:
                call = await session.get(Call, call_id)
                if call is None:
                    await websocket.send_json({"type": "not_found", "call_id": str(call_id)})
                    await websocket.close(code=4404)
                    return

                await websocket.send_json({"type": "call_update", "call": _call_snapshot(call)})
                if call.status in {"completed", "failed", "no_answer"}:
                    await websocket.close()
                    return

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@router.post("/api/calls/{call_id}/evaluate", response_model=CallEvaluationResponse)
async def evaluate_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    evaluator: EvaluationAgent = Depends(get_evaluation_agent),
):
    """Evaluate a call transcript and persist the result onto the call record."""
    result = await db.execute(
        select(Call, Job, Resume)
        .join(Job, Call.job_id == Job.id)
        .join(Resume, Call.resume_id == Resume.id)
        .where(Call.id == call_id, Job.user_id == current_user.id)
    )
    row = result.one_or_none()
    if not row:
        raise NotFoundError(resource="Call")

    call, job, resume = row
    if not call.transcript or not call.transcript.strip():
        raise ValidationError("Call transcript is required before evaluation.")

    evaluation = await evaluator.evaluate_call(call=call, job=job, resume=resume)
    call.ai_evaluation = evaluation.model_dump()
    if call.status == "queued":
        call.status = "completed"
    await db.flush()

    return CallEvaluationResponse(**call.ai_evaluation)
