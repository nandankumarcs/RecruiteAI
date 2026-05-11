"""
Resume Router — handles resume upload, listing, detail, and deletion.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_parser_agent import ResumeParserAgent, get_resume_parser_agent
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import ResumeDetailResponse, ResumeResponse
from app.services.storage import StorageProvider, get_storage_provider

router = APIRouter(tags=["resumes"])

ALLOWED_RESUME_TYPES = {"pdf", "docx"}


def _validate_resume_file(file: UploadFile) -> str:
    if not file.filename:
        raise ValidationError("Uploaded file must have a filename")

    extension = Path(file.filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_RESUME_TYPES:
        raise ValidationError("Unsupported file type. Only PDF and DOCX are allowed.")
    return extension


async def _get_owned_job(
    job_id: uuid.UUID, db: AsyncSession, current_user: User
) -> Job:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundError(resource="Job")
    return job


@router.post(
    "/api/jobs/{job_id}/resumes",
    response_model=list[ResumeResponse],
    status_code=201,
)
async def upload_resumes(
    job_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProvider = Depends(get_storage_provider),
    parser: ResumeParserAgent = Depends(get_resume_parser_agent),
):
    """Upload one or more resumes for a job and parse them immediately."""
    job = await _get_owned_job(job_id, db, current_user)

    if not files:
        raise ValidationError("At least one resume file is required")

    resumes: list[Resume] = []

    for file in files:
        file_type = _validate_resume_file(file)
        safe_name = os.path.basename(file.filename)
        destination = f"resumes/{job_id}/{uuid.uuid4()}-{safe_name}"
        saved_path = await storage.save_file(file, destination)

        try:
            parsed = await parser.parse_resume(saved_path, file_type)
            status = "parsed"
        except Exception:
            parsed = {
                "candidate_name": None,
                "phone_number": None,
                "email": None,
                "raw_text": None,
                "parsed_data": None,
            }
            status = "error"

        # Evaluate candidate against JD if parsing was successful
        matching_score = None
        match_explanation = None
        if status == "parsed" and parsed.get("raw_text") and job.description:
            try:
                evaluation = await parser.evaluate_candidate_against_jd(
                    parsed["raw_text"], job.description
                )
                matching_score = evaluation.matching_score
                match_explanation = evaluation.explanation
            except Exception:
                pass

        resume = Resume(
            job_id=job_id,
            candidate_name=parsed["candidate_name"],
            phone_number=parsed["phone_number"],
            email=parsed["email"],
            file_path=saved_path,
            file_type=file_type,
            raw_text=parsed["raw_text"],
            parsed_data=parsed["parsed_data"],
            matching_score=matching_score,
            match_explanation=match_explanation,
            status=status,
        )
        db.add(resume)
        resumes.append(resume)

    await db.flush()
    for resume in resumes:
        await db.refresh(resume)

    return resumes


@router.get("/api/jobs/{job_id}/resumes", response_model=list[ResumeResponse])
async def list_resumes(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List parsed/uploaded resumes for a job owned by the current user."""
    await _get_owned_job(job_id, db, current_user)

    result = await db.execute(
        select(Resume)
        .where(Resume.job_id == job_id)
        .order_by(Resume.matching_score.desc().nullslast(), Resume.created_at.desc())
    )
    return result.scalars().all()


@router.get("/api/resumes/{resume_id}", response_model=ResumeDetailResponse)
async def get_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full detail for a specific resume owned by the current user."""
    result = await db.execute(
        select(Resume)
        .join(Job, Resume.job_id == Job.id)
        .where(Resume.id == resume_id, Job.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundError(resource="Resume")
    return resume


@router.delete("/api/resumes/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProvider = Depends(get_storage_provider),
):
    """Delete a stored resume and its database record."""
    result = await db.execute(
        select(Resume)
        .join(Job, Resume.job_id == Job.id)
        .where(Resume.id == resume_id, Job.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundError(resource="Resume")

    await storage.delete_file(resume.file_path)
    await db.delete(resume)
    await db.flush()
