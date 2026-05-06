"""
Questions Router — generate and list interview questions for one resume.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.question_generator_agent import (
    QuestionGeneratorAgent,
    get_question_generator_agent,
)
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.models.user import User
from app.schemas.question import GeneratedQuestionSetResponse

router = APIRouter(tags=["questions"])


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
    resume, job = row
    return resume, job


@router.post(
    "/api/resumes/{resume_id}/questions/generate",
    response_model=GeneratedQuestionSetResponse,
    status_code=201,
)
async def generate_questions(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    generator: QuestionGeneratorAgent = Depends(get_question_generator_agent),
):
    """Generate and persist interview questions for a resume."""
    resume, job = await _get_owned_resume(resume_id, db, current_user)

    if resume.status != "parsed":
        raise ValidationError("Questions can only be generated for parsed resumes.")

    generated = await generator.generate_questions(job, resume)
    if not generated.questions:
        raise ValidationError("No questions could be generated for this resume.")

    await db.execute(delete(InterviewQuestion).where(InterviewQuestion.resume_id == resume.id))

    stored_questions: list[InterviewQuestion] = []
    for item in generated.questions:
        question = InterviewQuestion(
            job_id=job.id,
            resume_id=resume.id,
            question_text=item.question_text,
            category=item.category,
            difficulty=item.difficulty,
            order_index=item.order_index,
        )
        db.add(question)
        stored_questions.append(question)

    await db.flush()
    for question in stored_questions:
        await db.refresh(question)

    return GeneratedQuestionSetResponse(
        schema_version=generated.schema_version,
        questions=stored_questions,
    )


@router.get(
    "/api/resumes/{resume_id}/questions",
    response_model=GeneratedQuestionSetResponse,
)
async def list_questions(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List stored interview questions for a resume."""
    resume, _job = await _get_owned_resume(resume_id, db, current_user)
    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.resume_id == resume.id)
        .order_by(InterviewQuestion.order_index.asc(), InterviewQuestion.created_at.asc())
    )
    questions = result.scalars().all()
    return GeneratedQuestionSetResponse(
        schema_version="questions.v1",
        questions=questions,
    )
