"""
Twilio webhooks router — minimal voice/status foundation for Phase 5.
"""

from __future__ import annotations
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.call import Call

router = APIRouter(tags=["twilio-webhooks"])

try:
    from twilio.twiml.voice_response import VoiceResponse
except Exception:  # pragma: no cover
    VoiceResponse = None


STATUS_MAP = {
    "initiated": "pending",
    "queued": "queued",
    "ringing": "ringing",
    "in-progress": "in_progress",
    "completed": "completed",
    "busy": "failed",
    "failed": "failed",
    "no-answer": "no_answer",
    "canceled": "failed",
}


@router.post("/webhooks/twilio/voice")
async def twilio_voice_webhook(call_resume_id: str | None = None):
    """Return placeholder TwiML until the realtime bridge is implemented."""
    if VoiceResponse is None:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say>The interview service is being prepared. Please try again later.</Say><Hangup/></Response>"
        )
        return Response(content=xml, media_type="application/xml")

    response = VoiceResponse()
    response.say("The interview service is being prepared. Please try again later.")
    response.hangup()
    return Response(content=str(response), media_type="application/xml")


@router.post("/webhooks/twilio/status", status_code=204)
async def twilio_status_webhook(
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: str | None = Form(None),
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
    if call.status in {"completed", "failed", "no_answer"} and call.ended_at is None:
        call.ended_at = datetime.now(timezone.utc)
    if CallDuration and CallDuration.isdigit():
        call.duration_seconds = int(CallDuration)
    await db.flush()
    return Response(status_code=204)
