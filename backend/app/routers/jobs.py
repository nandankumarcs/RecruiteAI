"""
Jobs Router — handles CRUD operations for jobs.

Endpoints:
  GET    /api/jobs       — List all jobs for the authenticated user
  POST   /api/jobs       — Create a new job
  GET    /api/jobs/{id}  — Get a specific job by ID
  PUT    /api/jobs/{id}  — Update a specific job
  DELETE /api/jobs/{id}  — Delete a specific job
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.user import User
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.schemas.question import InterviewQuestionCreate, InterviewQuestionResponse, InterviewQuestionUpdate


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve all jobs owned by the current user."""
    result = await db.execute(
        select(Job)
        .where(Job.user_id == current_user.id)
        .order_by(Job.created_at.desc())
    )
    jobs = result.scalars().all()
    return jobs


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    job_in: JobCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new job for the current user."""
    job = Job(
        user_id=current_user.id,
        title=job_in.title,
        description=job_in.description,
        requirements=job_in.requirements,
        status=job_in.status,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)
    return job


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific job by ID."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise NotFoundError(resource="Job")
        
    return job


@router.put("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    job_in: JobUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a specific job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise NotFoundError(resource="Job")
        
    # Update fields provided in the request
    update_data = job_in.model_dump(exclude_unset=True)
    
    # Validation: prevent setting invalid statuses
    if "status" in update_data and update_data["status"] not in ["active", "paused", "closed"]:
        raise ValidationError(detail="Invalid status. Must be active, paused, or closed.")

    for field, value in update_data.items():
        setattr(job, field, value)
        
    await db.flush()
    await db.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a specific job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    
    if not job:
        raise NotFoundError(resource="Job")
        
    await db.delete(job)
    await db.flush()


# --- Interview Question Management ---

@router.get("/{job_id}/questions", response_model=list[InterviewQuestionResponse])
async def list_job_questions(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all interview questions for a specific job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError(resource="Job")

    result = await db.execute(
        select(InterviewQuestion)
        .where(InterviewQuestion.job_id == job_id)
        .order_by(InterviewQuestion.order_index.asc())
    )
    return result.scalars().all()


@router.post("/{job_id}/questions", response_model=InterviewQuestionResponse, status_code=201)
async def add_job_question(
    job_id: uuid.UUID,
    question_in: InterviewQuestionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a new interview question to a job."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError(resource="Job")

    question = InterviewQuestion(
        job_id=job_id,
        question_text=question_in.question_text,
        category=question_in.category,
        difficulty=question_in.difficulty,
        order_index=question_in.order_index,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)
    return question


@router.put("/{job_id}/questions/{question_id}", response_model=InterviewQuestionResponse)
async def update_job_question(
    job_id: uuid.UUID,
    question_id: uuid.UUID,
    question_in: InterviewQuestionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a specific interview question."""
    result = await db.execute(
        select(InterviewQuestion)
        .join(Job, InterviewQuestion.job_id == Job.id)
        .where(
            InterviewQuestion.id == question_id,
            Job.id == job_id,
            Job.user_id == current_user.id
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundError(resource="InterviewQuestion")

    update_data = question_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(question, field, value)

    await db.flush()
    await db.refresh(question)
    return question


@router.delete("/{job_id}/questions/{question_id}", status_code=204)
async def delete_job_question(
    job_id: uuid.UUID,
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a specific interview question."""
    result = await db.execute(
        select(InterviewQuestion)
        .join(Job, InterviewQuestion.job_id == Job.id)
        .where(
            InterviewQuestion.id == question_id,
            Job.id == job_id,
            Job.user_id == current_user.id
        )
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundError(resource="InterviewQuestion")

    await db.delete(question)
    await db.flush()

