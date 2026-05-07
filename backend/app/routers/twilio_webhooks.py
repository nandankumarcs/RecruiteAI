"""
Twilio webhooks router — minimal voice/status foundation for Phase 5.
"""

from __future__ import annotations
from datetime import datetime, timezone

import uuid

from fastapi import APIRouter, Depends, Form, WebSocket
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.call import Call
from app.services.call_evaluation import auto_evaluate_call_if_ready, call_is_finished
from app.services.realtime_bridge import RealtimeBridge, get_realtime_bridge

settings = get_settings()

router = APIRouter(tags=["twilio-webhooks"])

try:
    from twilio.twiml.voice_response import VoiceResponse
except Exception:  # pragma: no cover
    VoiceResponse = None


STATUS_MAP = {
    "initiated": "pending",
    "queued": "queued",
    "ringing": "ringing",
    "answered": "in_progress",
    "in-progress": "in_progress",
    "completed": "completed",
    "busy": "failed",
    "failed": "failed",
    "no-answer": "no_answer",
    "canceled": "failed",
}


@router.post("/webhooks/twilio/voice")
async def twilio_voice_webhook(call_resume_id: str | None = None):
    """Return TwiML that connects the live call audio to our websocket bridge."""
    if VoiceResponse is None:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>The interview service is being prepared. Please try again later.</Say><Hangup/></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    if not call_resume_id:
        response = VoiceResponse()
        response.say("We could not identify the candidate for this interview call.")
        response.hangup()
        return Response(content=str(response), media_type="application/xml")

    response = VoiceResponse()
    connect = response.connect()
    websocket_base = (
        settings.PUBLIC_URL.replace("https://", "wss://")
        .replace("http://", "ws://")
        .rstrip("/")
    )
    stream = connect.stream(
        url=f"{websocket_base}/ws/twilio-media/{call_resume_id}",
        status_callback=f"{settings.PUBLIC_URL.rstrip('/')}/webhooks/twilio/stream-status",
        status_callback_method="POST",
    )
    stream.parameter(name="resume_id", value=call_resume_id)
    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/twilio/status", status_code=204)
async def twilio_status_webhook(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str | None = Form(None),
    RecordingUrl: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Update a stored call record from Twilio status callbacks."""
    result = await db.execute(select(Call).where(Call.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()
    if not call:
        return Response(status_code=204)

    call.status = STATUS_MAP.get(CallStatus, call.status)
    if call.status == "in_progress" and call.started_at is None:
        call.started_at = datetime.now(timezone.utc)
    if call_is_finished(call.status) and call.ended_at is None:
        call.ended_at = datetime.now(timezone.utc)
    if CallDuration and CallDuration.isdigit():
        call.duration_seconds = int(CallDuration)
    if RecordingUrl:
        call.recording_url = RecordingUrl
    await db.flush()
    call_id = call.id
    await db.commit()
    if call.status == "completed":
        await auto_evaluate_call_if_ready(call_id)
    return Response(status_code=204)


@router.post("/webhooks/twilio/recording", status_code=204)
async def twilio_recording_webhook(
    CallSid: str = Form(...),
    RecordingUrl: str | None = Form(None),
    RecordingStatus: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Persist recording metadata for a completed or in-progress Twilio recording."""
    result = await db.execute(select(Call).where(Call.twilio_call_sid == CallSid))
    call = result.scalar_one_or_none()
    if not call:
        return Response(status_code=204)

    if RecordingUrl:
        call.recording_url = RecordingUrl
        call.recording_path = RecordingUrl
    if RecordingStatus == "completed" and call.status == "in_progress":
        call.status = "completed"
    call_id = call.id
    await db.flush()
    await db.commit()
    if call.status == "completed":
        await auto_evaluate_call_if_ready(call_id)
    return Response(status_code=204)


@router.post("/webhooks/twilio/stream-status", status_code=204)
async def twilio_stream_status_webhook():
    """Accept Twilio media stream lifecycle callbacks for observability."""
    return Response(status_code=204)


@router.websocket("/ws/twilio-media/{resume_id}")
async def twilio_media_stream(
    websocket: WebSocket,
    resume_id: uuid.UUID,
    bridge: RealtimeBridge = Depends(get_realtime_bridge),
):
    """Bidirectional websocket endpoint for Twilio media streams."""
    await bridge.handle(websocket, resume_id)
