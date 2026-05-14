"""
Calls Router — start and inspect interview calls.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from typing import Literal

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import selectinload
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
from app.schemas.call import CallEvaluationResponse, CallResponse, CallStartRequest, CallStartResponse, PaginatedCallsResponse
from app.services.analytics import analytics_service
from app.services.call_evaluation import auto_evaluate_call_if_ready

from app.services.observability import append_latency_marker
from app.services.pricing import hydrate_cost_breakdown, merge_cost_breakdown
from app.services.telephony import TelephonyService, get_telephony_service

settings = get_settings()

router = APIRouter(tags=["calls"])


MOCK_CALL_STEPS = [
    ("ringing", 2),
    ("in_progress", 3),
    ("completed", 4),
]


async def _verify_public_webhook_endpoint() -> None:
    """Ensure PUBLIC_URL points to this backend before placing live telephony calls."""
    health_url = f"{settings.PUBLIC_URL.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            response = await client.get(health_url)
    except Exception as exc:
        print(f"DEBUG: Exception in _verify_public_webhook_endpoint: {repr(exc)}")
        raise ValidationError(
            f"PUBLIC_URL is unreachable: {health_url}. Ensure ngrok is running and the URL is current."
        ) from exc

    if response.status_code != 200:
        raise ValidationError(
            f"PUBLIC_URL health check failed ({response.status_code}) at {health_url}. "
            "Ensure ngrok is running and PUBLIC_URL matches the active tunnel."
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise ValidationError(
            f"PUBLIC_URL returned a non-JSON response at {health_url}. "
            "This usually means the tunnel URL is stale or offline."
        ) from exc
    if payload.get("status") != "ok":
        raise ValidationError(
            f"PUBLIC_URL health payload is unexpected at {health_url}: {payload}"
        )


def _call_snapshot(call: Call) -> dict:
    cost_breakdown = hydrate_cost_breakdown(
        existing=call.cost_breakdown,
        provider=call.provider,
        duration_seconds=call.duration_seconds,
    )
    return {
        "id": str(call.id),
        "resume_id": str(call.resume_id),
        "job_id": str(call.job_id),
        "provider": call.provider,
        "voice_runtime": call.voice_runtime,
        "provider_call_id": call.provider_call_id,
        "twilio_call_sid": call.twilio_call_sid,
        "status": call.status,
        "phone_number": call.phone_number,
        "duration_seconds": call.duration_seconds,
        "recording_url": call.recording_url,
        "recording_path": call.recording_path,
        "transcript": call.transcript,
        "ai_evaluation": call.ai_evaluation,
        "cost_breakdown": cost_breakdown,
        "latency_metrics": call.latency_metrics,
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


async def _check_job_questions(
    db: AsyncSession,
    job_id: uuid.UUID,
) -> None:
    existing = await db.execute(
        select(InterviewQuestion.id).where(InterviewQuestion.job_id == job_id).limit(1)
    )
    if not existing.first():
        raise ValidationError("No interview questions found for this job. Please add questions before starting a call.")



@router.post("/api/resumes/{resume_id}/calls/start", response_model=CallStartResponse, status_code=201)
async def start_call(
    resume_id: uuid.UUID,
    request_data: CallStartRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    telephony: TelephonyService = Depends(get_telephony_service),

):
    """Generate questions if needed, create a call record, and initiate outbound telephony."""
    resume, job = await _get_owned_resume(resume_id, db, current_user)

    # Use custom phone number if provided, otherwise fallback to resume's number
    to_number = (request_data.phone_number if request_data else None) or resume.phone_number

    if resume.status != "parsed":
        raise ValidationError("Calls can only be started for parsed resumes.")
    if not to_number:
        raise ValidationError("Candidate phone number is required to start a call.")

    # Update resume phone number if a new one was provided
    if request_data and request_data.phone_number and request_data.phone_number != resume.phone_number:
        resume.phone_number = request_data.phone_number
        db.add(resume)

    active_call = await db.execute(
        select(Call.id).where(
            Call.resume_id == resume.id,
            Call.status.in_(["pending", "queued", "ringing", "in_progress"]),
        ).limit(1)
    )
    if active_call.first():
        raise CallInProgressError()

    await _check_job_questions(db=db, job_id=job.id)


    if (
        getattr(telephony, "provider_name", "") in ("twilio", "exotel")
        and not getattr(telephony, "enable_mock_progression", False)
    ):
        await _verify_public_webhook_endpoint()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        provider=getattr(telephony, "provider_name", None) or settings.TELEPHONY_PROVIDER,
        voice_runtime=settings.VOICE_RUNTIME,
        provider_call_id=None,
        twilio_call_sid=None,
        status="pending",
        phone_number=to_number,
        latency_metrics=append_latency_marker(None, key="call_requested_at"),
        cost_breakdown=merge_cost_breakdown(
            None,
            provider=getattr(telephony, "provider_name", None) or settings.TELEPHONY_PROVIDER,
            notes=[
                f"telephony_provider={getattr(telephony, 'provider_name', None) or settings.TELEPHONY_PROVIDER}",
                f"voice_runtime={settings.VOICE_RUNTIME}",
            ],
        ),
    )
    db.add(call)
    await db.flush()
    await db.commit()

    outbound_urls = telephony.build_urls(resume_id=resume.id)
    outbound = telephony.start_outbound_call(
        to_number=to_number,
        answer_url=outbound_urls.answer_url,
        status_callback_url=outbound_urls.status_callback_url,
        recording_callback_url=outbound_urls.recording_callback_url,
    )

    call.provider = outbound.provider
    call.provider_call_id = outbound.call_sid
    call.twilio_call_sid = outbound.call_sid if outbound.provider == "twilio" else None
    call.status = outbound.status
    call.cost_breakdown = merge_cost_breakdown(
        call.cost_breakdown,
        provider=outbound.provider,
        notes=[
            f"telephony_provider={outbound.provider}",
            f"voice_runtime={settings.VOICE_RUNTIME}",
        ],
    )
    await db.commit()
    from sqlalchemy.orm import selectinload
    await db.refresh(call)
    
    # Re-fetch with messages loaded to avoid lazy loading error in Pydantic
    stmt = select(Call).where(Call.id == call.id).options(selectinload(Call.messages))
    result = await db.execute(stmt)
    call = result.scalar_one()

    if getattr(telephony, "enable_mock_progression", False) and outbound.provider == "mock":
        asyncio.create_task(_simulate_mock_call_progress(call.id))

    return CallStartResponse(provider=outbound.provider, call=call)


ACTIVE_CALL_STATUSES = ("pending", "queued", "ringing", "in_progress")
TERMINAL_CALL_STATUSES = ("completed", "failed", "no_answer", "busy", "cancelled")


@router.get("/api/jobs/{job_id}/calls", response_model=PaginatedCallsResponse)
async def list_calls(
    job_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Literal["created_at", "status", "phone_number"] = Query("created_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List call records for a job with server-side pagination and sorting."""
    owned_job = await db.execute(
        select(Job.id).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    if not owned_job.scalar_one_or_none():
        raise NotFoundError(resource="Job")

    sort_col = getattr(Call, sort_by)
    primary_order = desc(sort_col) if sort_order == "desc" else asc(sort_col)
    secondary_order = desc(Call.created_at) if sort_by != "created_at" else None

    total_result = await db.execute(
        select(func.count()).select_from(Call).where(Call.job_id == job_id)
    )
    total = total_result.scalar_one()

    completed_result = await db.execute(
        select(func.count()).select_from(Call).where(
            Call.job_id == job_id, Call.status == "completed"
        )
    )
    completed_count = completed_result.scalar_one()

    order_clauses = [primary_order, secondary_order] if secondary_order is not None else [primary_order]
    items_result = await db.execute(
        select(Call)
        .options(selectinload(Call.messages))
        .where(Call.job_id == job_id)
        .order_by(*order_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(items_result.scalars().all())
    for call in items:
        call.cost_breakdown = hydrate_cost_breakdown(
            existing=call.cost_breakdown,
            provider=call.provider,
            duration_seconds=call.duration_seconds,
        )

    active_result = await db.execute(
        select(Call)
        .options(selectinload(Call.messages))
        .where(Call.job_id == job_id, Call.status.in_(ACTIVE_CALL_STATUSES))
        .order_by(Call.created_at.desc())
    )
    active_calls = list(active_result.scalars().all())

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "completed_count": completed_count,
        "active_calls": active_calls,
    }


@router.get("/api/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get one call record scoped to the owning user."""
    result = await db.execute(
        select(Call)
        .options(selectinload(Call.messages))
        .join(Job, Call.job_id == Job.id)
        .where(Call.id == call_id, Job.user_id == current_user.id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(resource="Call")
    call.cost_breakdown = hydrate_cost_breakdown(
        existing=call.cost_breakdown,
        provider=call.provider,
        duration_seconds=call.duration_seconds,
    )
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

    recording_url = call.recording_url
    if not recording_url.endswith(".mp3") and not recording_url.endswith(".wav"):
        recording_url = f"{recording_url}.mp3"
    client_kwargs: dict = {
        "follow_redirects": True,
        "timeout": 30,
    }
    if call.provider == "twilio":
        if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
            raise ValidationError("Twilio credentials are not configured for recording playback.")
        client_kwargs["auth"] = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    elif call.provider == "exotel":
        if not settings.EXOTEL_API_KEY or not settings.EXOTEL_API_TOKEN:
            raise ValidationError("Exotel credentials are not configured for recording playback.")
        client_kwargs["auth"] = (settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN)

    async with httpx.AsyncClient(**client_kwargs) as client:
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
    call.ai_evaluation = evaluation.model_dump(mode="json")
    call.evaluation_score = (
        float(evaluation.overall_score)
        if evaluation.overall_score is not None
        else None
    )
    call.evaluation_summary = evaluation.behavioral_summary or evaluation.remarks
    
    if call.status == "queued":
        call.status = "completed"
    await db.flush()
    await db.commit()
    return CallEvaluationResponse(**call.ai_evaluation)


@router.get("/api/calls/{call_id}/analytics")
async def get_call_analytics(
    call_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch granular analytics for a call, including turn-by-turn data from LangSmith."""
    result = await db.execute(
        select(Call)
        .join(Job, Call.job_id == Job.id)
        .where(Call.id == call_id, Job.user_id == current_user.id)
    )
    call = result.scalar_one_or_none()
    if not call:
        raise NotFoundError(resource="Call")
    
    # Fetch from LangSmith
    turns = analytics_service.get_call_turn_analytics(str(call_id))
    
    return {
        "call_id": str(call_id),
        "turns": turns,
        "summary": {
            "total_latency_ms": sum(t["latency_ms"] for t in turns),
            "total_tokens": sum(t["total_tokens"] for t in turns),
            "total_cost_usd": sum(t["cost_usd"] for t in turns),
            "turn_count": len(turns),
        }
    }
