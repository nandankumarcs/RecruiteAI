"""Exotel webhooks router — maps Exotel's API formats into our internal structures."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

from fastapi import APIRouter, Depends, Form, Request, WebSocket
from fastapi.responses import Response, JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.call_v2.runtime import get_call_v2_runtime
from app.config import get_settings
from app.database import async_session_factory, get_db
from app.models.call import Call
from app.services.telephony import get_telephony_service
from app.services.telephony_cache import get_cached_resume_id

logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter(tags=["exotel-webhooks"])

_UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)

# Map Exotel status to our internal normalized statuses
EXOTEL_STATUS_MAP = {
    "ringing": "ringing",
    "in-progress": "in_progress",
    "completed": "completed",
    "busy": "failed",
    "failed": "failed",
    "no-answer": "no_answer",
    "canceled": "failed",
}


def _coerce_duration_seconds(params: dict) -> int | None:
    for key in ("RecordingDuration", "Duration", "CallDuration"):
        value = params.get(key)
        if value in (None, ""):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


async def _reconcile_exotel_recording(call_id, call_sid: str) -> None:
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(2 * attempt)

        details = await asyncio.to_thread(get_telephony_service().fetch_call_details, call_sid)
        if not details:
            continue

        call_payload = details.get("Call") or {}
        recording_url = call_payload.get("RecordingUrl")
        duration_seconds = _coerce_duration_seconds(call_payload)
        if not recording_url:
            continue

        async with async_session_factory() as session:
            call = await session.get(Call, call_id)
            if call is None:
                return
            call.recording_url = recording_url
            call.recording_path = recording_url
            if duration_seconds is not None:
                call.duration_seconds = duration_seconds
            await session.commit()
        logger.info(
            "Backfilled Exotel recording metadata from call details",
            extra={"call_id": str(call_id), "call_sid": call_sid, "attempt": attempt + 1},
        )
        return


# Voice webhook moved to main.py temporarily for debugging


@router.post("/webhooks/exotel/status", status_code=204)
async def exotel_status_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a stored call record from Exotel status callbacks."""
    # Exotel sends parameters in form-encoded body
    form_data = await request.form()
    params = dict(form_data)
    query_params = dict(request.query_params)
    params.update(query_params)
    
    print(f"=== EXOTEL STATUS WEBHOOK HIT === ALL PARAMS: {params}")
    logger.info(f"=== EXOTEL STATUS WEBHOOK HIT === Params: {params}")

    CallSid = params.get("CallSid")
    Status = params.get("Status")

    if not CallSid or not Status:
        logger.warning(f"Exotel status update missing CallSid ({CallSid}) or Status ({Status})")
        return Response(status_code=204)

    logger.debug(f"Exotel status update: CallSid={CallSid}, Status={Status}")

    result = await db.execute(select(Call).where(Call.provider_call_id == CallSid))
    call = result.scalar_one_or_none()
    
    if not call:
        logger.warning(f"Exotel status update for unknown CallSid: {CallSid}")
        return Response(status_code=204)

    normalized_status = EXOTEL_STATUS_MAP.get(Status.lower(), call.status)
    call.status = normalized_status
    call.provider = "exotel"
    recording_url = params.get("RecordingUrl")
    if recording_url:
        call.recording_url = recording_url
        call.recording_path = recording_url

    duration_seconds = _coerce_duration_seconds(params)
    if duration_seconds is not None:
        call.duration_seconds = duration_seconds
    
    await db.commit()
    if (
        normalized_status == "completed"
        and not call.recording_url
        and call.provider_call_id
    ):
        asyncio.create_task(_reconcile_exotel_recording(call.id, call.provider_call_id))
    return Response(status_code=204)


@router.post("/webhooks/exotel/recording", status_code=204)
async def exotel_recording_webhook(
    CallSid: str = Form(None),
    RecordingUrl: str = Form(None),
    RecordingDuration: str = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Callback when recording is available."""
    if not CallSid or not RecordingUrl:
        return Response(status_code=204)

    result = await db.execute(select(Call).where(Call.provider_call_id == CallSid))
    call = result.scalar_one_or_none()
    if not call:
        return Response(status_code=204)

    call.recording_url = RecordingUrl
    call.recording_path = RecordingUrl
    if RecordingDuration:
        try:
            call.duration_seconds = int(RecordingDuration)
        except ValueError:
            pass

    await db.commit()
    return Response(status_code=204)


@router.websocket("/ws/exotel-media/{resume_id:path}")
@router.websocket("/webhooks/exotel-stream/{resume_id:path}")
async def exotel_media_stream(websocket: WebSocket, resume_id: str):
    """WebSocket entry point for Exotel's AgentStream (call v2 runtime).

    Exotel requires the WebSocket handshake to complete immediately or it sends
    a 403, so we accept before starting the (async) session setup inside the
    v2 runtime.  The v2 runtime's handle() re-checks the application state and
    will not call accept() a second time.

    resume_id resolution order:
    1. UUID found directly in the path (normal case).
    2. UUID in query params (CustomField, resume_id, call_resume_id).
    3. In-process memory cache (survives within the same server process).
    4. Most-recent Exotel call row in the DB (last-resort dev fallback when the
       server restarted and cleared the in-process cache before Exotel connected).
    """
    await websocket.accept()

    logger.debug("Exotel media stream: url=%s params=%s", websocket.url, dict(websocket.query_params))

    match = _UUID_PATTERN.search(resume_id)
    if match:
        resume_id = match.group(0)
    else:
        new_id = (
            websocket.query_params.get("CustomField")
            or websocket.query_params.get("resume_id")
            or websocket.query_params.get("call_resume_id")
        )
        if new_id:
            match = _UUID_PATTERN.search(new_id)
            if match:
                resume_id = match.group(0)

        if not _UUID_PATTERN.match(resume_id):
            cached_id = get_cached_resume_id()
            if cached_id:
                resume_id = cached_id

        if not _UUID_PATTERN.match(resume_id):
            async with async_session_factory() as session:
                result = await session.execute(
                    select(Call.resume_id)
                    .where(Call.provider == "exotel")
                    .order_by(desc(Call.created_at))
                    .limit(1)
                )
                latest_resume_id = result.scalar_one_or_none()
                if latest_resume_id:
                    resume_id = str(latest_resume_id)

    logger.debug("Exotel media stream: resolved resume_id=%s", resume_id)

    try:
        resume_uuid = uuid.UUID(resume_id)
    except ValueError:
        logger.error("Could not resolve a valid UUID from Exotel path: %r", resume_id)
        await websocket.close(code=1003, reason="Invalid session ID")
        return

    runtime = get_call_v2_runtime()
    await runtime.handle(websocket, resume_id=resume_uuid, provider="exotel")
