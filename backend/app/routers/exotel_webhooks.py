"""
Exotel webhooks router — maps Exotel's API formats into our internal structures.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session_factory, get_db
from app.models.call import Call
from app.services.telephony import get_telephony_service

# For now we use the same signature pattern if needed, or disable it
# from app.dependencies.exotel_signature import verify_exotel_signature

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

settings = get_settings()

router = APIRouter(tags=["exotel-webhooks"])

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
    
    await db.commit()
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
    if RecordingDuration:
        try:
            call.duration_seconds = int(RecordingDuration)
        except ValueError:
            pass

    await db.commit()
    return Response(status_code=204)

# Note: WebSocket endpoint for Media is mounted in `main.py` usually 
# or handled via `twilio_webhooks.py` currently if the path matches.
# But we'll add the new Exotel websocket path explicitly.

from fastapi import WebSocket
from app.services.voice_runtime import get_voice_runtime_service
from app.services.telephony_cache import get_cached_resume_id
import uuid

@router.websocket("/ws/exotel-media/{resume_id:path}")
@router.websocket("/webhooks/exotel-stream/{resume_id:path}")
async def exotel_media_stream(websocket: WebSocket, resume_id: str):
    """WebSocket endpoint for Exotel's AgentStream protocol."""
    # MANDATORY: Accept immediately to prevent 403 Forbidden on handshake
    await websocket.accept()
    
    # Log the full URL and params for debugging
    import sys
    sys.stderr.write(f"WebSocket URL: {websocket.url}\n")
    sys.stderr.write(f"WebSocket Query Params: {websocket.query_params}\n")
    sys.stderr.flush()

    # 1. Try to find a UUID in the mangled resume_id string using regex
    import re
    uuid_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
    
    # Search in the path first
    match = uuid_pattern.search(resume_id)
    if match:
        resume_id = match.group(0)
    else:
        # 2. Search in query params
        new_id = (
            websocket.query_params.get("CustomField") 
            or websocket.query_params.get("resume_id")
            or websocket.query_params.get("call_resume_id")
        )
        if new_id:
            match = uuid_pattern.search(new_id)
            if match:
                resume_id = match.group(0)
        
        # 3. Fallback to cache if still no luck
        if not uuid_pattern.match(resume_id):
            cached_id = get_cached_resume_id()
            if cached_id:
                resume_id = cached_id

        # 4. Last-resort dev fallback for Exotel flow URLs that arrive without
        # our UUID in the WebSocket path after a server reload clears memory cache.
        if not uuid_pattern.match(resume_id):
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

    sys.stderr.write(f"DEBUG: Final Resolved resume_id: {resume_id}\n")
    sys.stderr.flush()
    
    try:
        resume_uuid = uuid.UUID(resume_id)
    except ValueError:
        logger.error(f"FATAL: Could not resolve a valid UUID from: {resume_id}")
        await websocket.close(code=1003, reason="Invalid session ID")
        return

    try:
        runtime = get_voice_runtime_service()
        # runtime.handle will NO LONGER call websocket.accept() if it checks state
        await runtime.handle(websocket, resume_uuid, provider="exotel")
    except Exception as e:
        logger.error(f"Error in Exotel media stream: {e}", exc_info=True)
        # Check if already accepted before closing
        try:
            if not websocket.client_state.name == "DISCONNECTED":
                await websocket.close()
        except:
            pass
