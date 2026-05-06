"""
Calls Router — start and inspect interview calls.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_generator_agent import (
    QuestionGeneratorAgent,
    get_question_generator_agent,
)
from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.exceptions import CallInProgressError, NotFoundError, ValidationError
from app.database import get_db
from app.models.call import Call
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.models.user import User
from app.schemas.call import CallResponse, CallStartResponse
from app.services.telephony import TelephonyService, get_telephony_service

settings = get_settings()

router = APIRouter(tags=["calls"])


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
    outbound = telephony.start_outbound_call(
        to_number=resume.phone_number,
        twiml_url=twiml_url,
        status_callback_url=status_callback_url,
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
