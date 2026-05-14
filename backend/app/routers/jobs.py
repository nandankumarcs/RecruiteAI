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
from app.schemas.question import InterviewQuestionCreate, InterviewQuestionResponse, InterviewQuestionUpdate, GeneratedQuestionSetResponse, QuestionsReorderRequest
from app.tasks.audio_generation import schedule_generate_question_audio_for_job
from app.agents.question_generator_agent import QuestionGeneratorAgent, get_question_generator_agent


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
    await db.commit()
    schedule_generate_question_audio_for_job(job_id)
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
    await db.commit()
    schedule_generate_question_audio_for_job(job_id)
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


@router.post("/{job_id}/questions/generate", response_model=GeneratedQuestionSetResponse, status_code=201)
async def generate_job_questions(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    generator: QuestionGeneratorAgent = Depends(get_question_generator_agent),
):
    """AI-generate interview questions for a job based on its JD."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError(resource="Job")

    generated = await generator.generate_questions(job)
    if not generated.questions:
        raise ValidationError("No questions could be generated for this job description.")

    # Clear existing questions for a fresh start
    from sqlalchemy import delete
    await db.execute(delete(InterviewQuestion).where(InterviewQuestion.job_id == job.id))

    stored_questions: list[InterviewQuestion] = []
    for item in generated.questions:
        question = InterviewQuestion(
            job_id=job.id,
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
    await db.commit()
    schedule_generate_question_audio_for_job(job_id)

    return GeneratedQuestionSetResponse(
        schema_version=generated.schema_version,
        questions=stored_questions,
    )


@router.patch("/{job_id}/questions/reorder", status_code=204)
async def reorder_job_questions(
    job_id: uuid.UUID,
    reorder_request: QuestionsReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch update the order_index of multiple questions."""
    # Verify job ownership
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError(resource="Job")

    # Update each question's order_index
    for update in reorder_request.questions:
        result = await db.execute(
            select(InterviewQuestion).where(
                InterviewQuestion.id == update.id,
                InterviewQuestion.job_id == job_id,
            )
        )
        question = result.scalar_one_or_none()
        if question:
            question.order_index = update.order_index

    await db.commit()
