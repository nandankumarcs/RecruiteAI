"""
Resume Router — handles resume upload, listing, detail, and deletion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_parser_agent import ResumeParserAgent, get_resume_parser_agent
from app.core.dependencies import get_current_user, get_current_user_from_query
from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.models.job import Job
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resume import (
    PaginatedResumesResponse,
    ResumeDetailResponse,
    ResumeResponse,
    ResumeUpdateRequest,
)
from app.services.storage import StorageProvider, get_storage_provider
from app.services.resume_session_manager import get_session_manager, ResumeSessionManager
from app.services.resume_progress_emitter import ResumeProgressEmitter

router = APIRouter(tags=["resumes"])
logger = logging.getLogger(__name__)

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


async def _process_resumes_background(
    session_id: str,
    job_id: uuid.UUID,
    file_paths: list[tuple[str, str, str]],  # (saved_path, filename, file_type)
    job_description: str | None,
    session_manager: ResumeSessionManager,
    storage: StorageProvider,
    parser: ResumeParserAgent,
) -> None:
    """
    Background task to process resumes sequentially with progress streaming.
    
    Args:
        session_id: Session identifier for progress tracking
        job_id: Job UUID
        file_paths: List of tuples (saved_path, filename, file_type)
        job_description: Job description for evaluation (optional)
        session_manager: Session manager instance
        storage: Storage provider instance
        parser: Resume parser agent instance
    """
    from app.database import async_session_factory
    
    emitter = ResumeProgressEmitter(session_manager)
    total_resumes = len(file_paths)
    
    # Create a new database session for background processing
    async with async_session_factory() as db:
        try:
            for index, (saved_path, filename, file_type) in enumerate(file_paths):
                try:
                    # Starting
                    await emitter.emit_starting(
                        session_id, index, total_resumes, filename
                    )
                    
                    # Uploading (file already saved, just emit event)
                    await emitter.emit_uploading(
                        session_id, index, total_resumes, filename
                    )
                    
                    # Parsing
                    await emitter.emit_parsing(
                        session_id, index, total_resumes, filename
                    )
                    
                    try:
                        parsed = await parser.parse_resume(saved_path, file_type)
                        status = "parsed"
                    except Exception as parse_error:
                        logger.error(f"Failed to parse {filename}: {parse_error}")
                        parsed = {
                            "candidate_name": None,
                            "phone_number": None,
                            "email": None,
                            "raw_text": None,
                            "parsed_data": None,
                        }
                        status = "error"
                        await emitter.emit_error(
                            session_id, index, total_resumes, filename,
                            error_message=str(parse_error),
                            failed_stage="parsing"
                        )
                        continue
                    
                    # Evaluating
                    matching_score = None
                    match_explanation = None
                    if status == "parsed" and parsed.get("raw_text") and job_description:
                        await emitter.emit_evaluating(
                            session_id, index, total_resumes, filename
                        )
                        
                        try:
                            evaluation = await parser.evaluate_candidate_against_jd(
                                parsed["raw_text"], job_description
                            )
                            matching_score = evaluation.matching_score
                            match_explanation = evaluation.explanation
                        except Exception as eval_error:
                            logger.error(f"Failed to evaluate {filename}: {eval_error}")
                            # Continue without evaluation
                    
                    # Save to database
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
                    await db.flush()
                    await db.refresh(resume)
                    
                    # Completed
                    await emitter.emit_completed(
                        session_id, index, total_resumes, filename,
                        candidate_name=resume.candidate_name,
                        email=resume.email,
                        phone_number=resume.phone_number,
                        matching_score=resume.matching_score
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing resume {filename}: {e}")
                    await emitter.emit_error(
                        session_id, index, total_resumes, filename,
                        error_message=str(e),
                        failed_stage="unknown"
                    )
            
            # Commit all changes
            await db.commit()
            
            # All completed
            await emitter.emit_all_completed(session_id, total_resumes)
            session_manager.mark_completed(session_id)
            
        except Exception as e:
            logger.error(f"Fatal error in background processing for session {session_id}: {e}")
            await db.rollback()


@router.post(
    "/api/jobs/{job_id}/resumes",
    response_model=dict,
    status_code=202,
)
async def upload_resumes(
    job_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProvider = Depends(get_storage_provider),
    parser: ResumeParserAgent = Depends(get_resume_parser_agent),
    session_manager: ResumeSessionManager = Depends(get_session_manager),
):
    """
    Upload resumes and return session_id immediately.
    Processing happens in background with progress streaming via SSE.
    
    Returns:
        dict: {
            "session_id": str,
            "total_resumes": int
        }
    """
    job = await _get_owned_job(job_id, db, current_user)

    if not files:
        raise ValidationError("At least one resume file is required")

    # Validate all files first
    validated_files = []
    for file in files:
        file_type = _validate_resume_file(file)
        validated_files.append((file, file_type))
    
    # Create session
    session_id = session_manager.create_session(
        job_id=str(job_id),
        user_id=str(current_user.id),
        total_resumes=len(validated_files)
    )
    
    # Save files to storage
    file_paths = []
    for file, file_type in validated_files:
        safe_name = os.path.basename(file.filename)
        destination = f"resumes/{job_id}/{uuid.uuid4()}-{safe_name}"
        saved_path = await storage.save_file(file, destination)
        file_paths.append((saved_path, file.filename, file_type))
    
    # Start background processing
    asyncio.create_task(
        _process_resumes_background(
            session_id=session_id,
            job_id=job_id,
            file_paths=file_paths,
            job_description=job.description,
            session_manager=session_manager,
            storage=storage,
            parser=parser,
        )
    )
    
    return {
        "session_id": session_id,
        "total_resumes": len(validated_files)
    }


@router.get("/api/jobs/{job_id}/resumes/stream")
async def stream_resume_progress(
    job_id: uuid.UUID,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query),
    session_manager: ResumeSessionManager = Depends(get_session_manager),
):
    """
    SSE endpoint for streaming resume processing progress.
    
    Streams real-time progress events for resume processing including:
    - starting: Resume processing begins
    - uploading: File upload stage
    - parsing: Resume parsing stage
    - evaluating: Evaluation against job description
    - completed: Resume successfully processed
    - error: Processing error occurred
    - all_completed: All resumes in session processed
    - keepalive: Periodic keepalive to prevent timeout
    
    Args:
        job_id: Job UUID
        session_id: Processing session identifier
        db: Database session
        current_user: Authenticated user
        session_manager: Session manager instance
        
    Returns:
        StreamingResponse with SSE events
    """
    # Validate job ownership
    await _get_owned_job(job_id, db, current_user)
    
    # Validate session exists
    session = session_manager.get_session(session_id)
    if not session:
        raise NotFoundError(resource="Processing session")
    
    # Verify session belongs to this job
    if session.job_id != str(job_id):
        raise NotFoundError(resource="Processing session")
    
    # Verify session belongs to current user
    if session.user_id != str(current_user.id):
        raise ValidationError("Session does not belong to current user")
    
    async def event_generator():
        """Generate SSE events from session event queue."""
        try:
            async for event in session_manager.subscribe(session_id):
                # Format event data
                event_data = event.to_dict()
                
                # SSE format: "event: <type>\ndata: <json>\n\n"
                if event.event_type == "keepalive":
                    # Send keepalive as comment to keep connection alive
                    yield ": keepalive\n\n"
                else:
                    # Send actual event with type and data
                    yield f"event: {event.event_type}\n"
                    yield f"data: {json.dumps(event_data)}\n\n"
                
                # Close stream after all_completed event
                if event.event_type == "all_completed":
                    break
                    
        except asyncio.CancelledError:
            # Client disconnected, cleanup handled by subscribe()
            logger.info(f"SSE connection cancelled for session {session_id}")
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Error in SSE stream for session {session_id}: {e}")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.get("/api/jobs/{job_id}/resumes", response_model=PaginatedResumesResponse)
async def list_resumes(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Literal["matching_score", "candidate_name", "status", "created_at"] = Query("matching_score"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List resumes for a job with server-side pagination and sorting."""
    await _get_owned_job(job_id, db, current_user)

    sort_col = getattr(Resume, sort_by)
    if sort_order == "desc":
        primary_order = desc(sort_col).nullslast()
    else:
        primary_order = asc(sort_col).nullsfirst()

    secondary_order = desc(Resume.created_at) if sort_by != "created_at" else None

    base_query = select(Resume).where(Resume.job_id == job_id)

    count_result = await db.execute(
        select(func.count()).select_from(Resume).where(Resume.job_id == job_id)
    )
    total = count_result.scalar_one()

    order_clauses = [primary_order, secondary_order] if secondary_order is not None else [primary_order]
    items_result = await db.execute(
        base_query
        .order_by(*order_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = items_result.scalars().all()

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


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


@router.patch("/api/resumes/{resume_id}", response_model=ResumeDetailResponse)
async def update_resume(
    resume_id: uuid.UUID,
    payload: ResumeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    parser: ResumeParserAgent = Depends(get_resume_parser_agent),
):
    """Update editable resume fields (parsed_data, contact info).

    Optionally re-runs the candidate-vs-JD matcher after save so the
    matching_score reflects any changes the user made to the content.
    """
    from app.agents.resume_parser_agent import serialize_structured_resume

    result = await db.execute(
        select(Resume)
        .join(Job, Resume.job_id == Job.id)
        .where(Resume.id == resume_id, Job.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundError(resource="Resume")

    # Apply top-level field updates (only when explicitly provided)
    if payload.candidate_name is not None:
        resume.candidate_name = payload.candidate_name.strip() or None
    if payload.phone_number is not None:
        resume.phone_number = payload.phone_number.strip() or None
    if payload.email is not None:
        resume.email = payload.email.strip() or None

    # Replace parsed_data with the v3 payload; preserve schema_version
    if payload.parsed_data is not None:
        new_data = payload.parsed_data.model_dump(mode="json")
        new_data["schema_version"] = "resume.v3"
        resume.parsed_data = new_data

    # Recalculate match score using serialized structured text so edits are reflected
    if payload.recalculate_match and resume.parsed_data:
        job_result = await db.execute(select(Job).where(Job.id == resume.job_id))
        job = job_result.scalar_one_or_none()
        if job and getattr(job, "description", None):
            resume_text = serialize_structured_resume(resume.parsed_data, resume)
            try:
                evaluation = await parser.evaluate_candidate_against_jd(
                    resume_text, job.description
                )
                resume.matching_score = evaluation.matching_score
                resume.match_explanation = evaluation.explanation
            except Exception as exc:
                logger.warning(
                    "Match recalculation failed for resume=%s: %s", resume_id, exc
                )
                # Don't fail the save — matching score is best-effort

    await db.commit()
    await db.refresh(resume)
    return resume


@router.get("/api/resumes/{resume_id}/file")
async def download_resume_file(
    resume_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve the original uploaded resume file (PDF or DOCX) for authenticated preview."""
    from pathlib import Path
    from fastapi.responses import Response as FileResponse

    result = await db.execute(
        select(Resume)
        .join(Job, Resume.job_id == Job.id)
        .where(Resume.id == resume_id, Job.user_id == current_user.id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise NotFoundError(resource="Resume")

    # file_path in DB may be stored as a relative path like "./uploads/resumes/..."
    # Resolve it: try as-is first, then relative to STORAGE_LOCAL_PATH base.
    from app.config import get_settings as _get_settings
    _settings = _get_settings()
    raw = resume.file_path
    # Strip leading "./" or "uploads/" prefix so we can re-anchor to the configured base
    clean = raw.lstrip("./")           # e.g. "uploads/resumes/job/file.pdf"
    if clean.startswith("uploads/"):
        clean = clean[len("uploads/"):]  # e.g. "resumes/job/file.pdf"

    candidates = [
        Path(raw),                                              # as stored (may be absolute)
        Path(_settings.STORAGE_LOCAL_PATH) / clean,            # base + stripped
        Path(_settings.STORAGE_LOCAL_PATH) / Path(raw).name,   # base + filename only
    ]
    file_path = next((p for p in candidates if p.exists()), None)
    if file_path is None:
        raise NotFoundError(resource="Resume file")

    content_type_map = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc":  "application/msword",
    }
    ext = (resume.file_type or file_path.suffix.lstrip(".")).lower()
    content_type = content_type_map.get(ext, "application/octet-stream")

    with open(file_path, "rb") as f:
        content = f.read()

    filename = file_path.name
    return FileResponse(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
