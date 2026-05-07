"""Plivo webhooks and media stream routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Form, Query, WebSocket
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.call import Call
from app.services.call_evaluation import auto_evaluate_call_if_ready, call_is_finished
from app.services.observability import append_latency_marker
from app.services.pricing import estimate_telephony_cost, merge_cost_breakdown
from app.services.telephony import TelephonyService, get_telephony_service
from app.services.voice_runtime import VoiceRuntimeService, get_voice_runtime_service

settings = get_settings()

router = APIRouter(tags=["plivo-webhooks"])


PLIVO_STATUS_MAP = {
    "in-progress": "in_progress",
    "completed": "completed",
    "ringing": "ringing",
    "no-answer": "no_answer",
    "busy": "failed",
    "cancel": "failed",
    "timeout": "failed",
}


def _xml_response(body: str) -> Response:
    return Response(content=body, media_type="application/xml")


@router.api_route("/webhooks/plivo/answer", methods=["GET", "POST"])
async def plivo_answer_webhook(call_resume_id: str | None = None):
    if not call_resume_id:
        return _xml_response(
            "<Response><Speak>We could not identify the candidate for this interview call.</Speak><Hangup/></Response>"
        )

    websocket_base = (
        settings.PUBLIC_URL.replace("https://", "wss://")
        .replace("http://", "ws://")
        .rstrip("/")
    )
    stream_status_url = f"{settings.PUBLIC_URL.rstrip('/')}/webhooks/plivo/stream-status"
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<Response>"
        "<Stream "
        "bidirectional=\"true\" "
        "keepCallAlive=\"true\" "
        "contentType=\"audio/x-mulaw;rate=8000\" "
        f"statusCallbackUrl=\"{escape(stream_status_url)}\" "
        "statusCallbackMethod=\"POST\">"
        f"{escape(f'{websocket_base}/ws/plivo-media/{call_resume_id}')}"
        "</Stream>"
        "</Response>"
    )
    return _xml_response(xml)


@router.api_route("/webhooks/plivo/end-call", methods=["GET", "POST"])
async def plivo_end_call_webhook(message: str = Query("Thank you for your time today. Goodbye.")):
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        f"<Response><Speak>{escape(message)}</Speak><Hangup/></Response>"
    )
    return _xml_response(xml)


@router.api_route("/webhooks/plivo/status", methods=["GET", "POST"], status_code=204)
async def plivo_status_webhook(
    CallUUID: str | None = Form(None),
    CallStatus: str | None = Form(None),
    Duration: str | None = Form(None),
    bill_duration: str | None = Form(None),
    DialHangupCause: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    telephony: TelephonyService = Depends(get_telephony_service),
):
    if not CallUUID or not CallStatus:
        return Response(status_code=204)

    result = await db.execute(select(Call).where(Call.provider_call_id == CallUUID))
    call = result.scalar_one_or_none()
    if not call:
        return Response(status_code=204)

    mapped_status = PLIVO_STATUS_MAP.get(CallStatus, call.status)
    call.provider = "plivo"
    call.status = mapped_status
    if mapped_status == "in_progress" and call.started_at is None:
        call.started_at = datetime.now(timezone.utc)
        callback_url = (
            f"{settings.PUBLIC_URL.rstrip('/')}/webhooks/plivo/recording?call_id={call.id}"
        )
        telephony.start_recording(CallUUID, callback_url=callback_url)
    if call_is_finished(mapped_status) and call.ended_at is None:
        call.ended_at = datetime.now(timezone.utc)

    duration_value = Duration or bill_duration
    if duration_value and duration_value.isdigit():
        call.duration_seconds = int(duration_value)
    if call.duration_seconds:
        call.cost_breakdown = merge_cost_breakdown(
            call.cost_breakdown,
            provider="plivo",
            telephony_cost_usd=estimate_telephony_cost(
                provider="plivo",
                duration_seconds=call.duration_seconds,
            ),
        )
    if DialHangupCause:
        call.latency_metrics = append_latency_marker(call.latency_metrics, key="plivo_status_updated_at")

    call_id = call.id
    await db.flush()
    await db.commit()
    if mapped_status == "completed":
        await auto_evaluate_call_if_ready(call_id)
    return Response(status_code=204)


@router.api_route("/webhooks/plivo/recording", methods=["GET", "POST"], status_code=204)
async def plivo_recording_webhook(
    call_id: uuid.UUID | None = Query(None),
    RecordUrl: str | None = Form(None),
    RecordingID: str | None = Form(None),
    RecordingDuration: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    if call_id is None:
        return Response(status_code=204)

    call = await db.get(Call, call_id)
    if call is None:
        return Response(status_code=204)

    if RecordUrl:
        call.recording_url = RecordUrl
        call.recording_path = RecordingID or RecordUrl
    if RecordingDuration and RecordingDuration.isdigit():
        call.duration_seconds = int(RecordingDuration)
    if call.status == "in_progress":
        call.status = "completed"
    call.cost_breakdown = merge_cost_breakdown(
        call.cost_breakdown,
        provider="plivo",
        telephony_cost_usd=estimate_telephony_cost(
            provider="plivo",
            duration_seconds=call.duration_seconds,
        ),
    )
    await db.flush()
    await db.commit()
    await auto_evaluate_call_if_ready(call.id)
    return Response(status_code=204)


@router.api_route("/webhooks/plivo/stream-status", methods=["GET", "POST"], status_code=204)
async def plivo_stream_status_webhook():
    return Response(status_code=204)


@router.websocket("/ws/plivo-media/{resume_id}")
async def plivo_media_stream(
    websocket: WebSocket,
    resume_id: uuid.UUID,
    bridge: VoiceRuntimeService = Depends(get_voice_runtime_service),
):
    await bridge.handle(websocket, resume_id, provider="plivo")
