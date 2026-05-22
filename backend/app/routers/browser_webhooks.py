"""WebSocket + auth endpoints for the browser telephony simulator.

This file is the only router-level surface added by the simulator. Delete the
file + remove its registration in ``main.py`` to fully uninstall.

Endpoints:
  - GET  /api/sim/token/{call_id}         — mint a short-lived join token (auth required)
  - WS   /ws/browser-media/{resume_id}    — call v2 runtime (token-auth via query param)
  - WS   /ws/call-v2-sim/{call_id}        — call v2 fake-provider test harness
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.security import decode_token
from app.database import async_session_factory, get_db
from app.models import Call, User
from app.call_v2.runtime import get_call_v2_runtime
from app.call_v2.simulator import run_call_v2_simulator_websocket
from app.services.telephony_browser import mint_simulator_token

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.get("/api/sim/token/{call_id}")
async def get_simulator_token(
    call_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Mint a short-lived join token for the simulator websocket.

    Auth: normal dashboard JWT — only logged-in dashboard users may issue
    simulator tokens, mirroring how real outbound calls are gated.
    """
    result = await db.execute(select(Call).where(Call.id == call_id))
    call = result.scalar_one_or_none()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    if call.provider != "browser":
        raise HTTPException(
            status_code=400,
            detail="Simulator tokens are only valid for browser-provider calls",
        )
    if call.status in {"completed", "failed", "no_answer", "busy", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail=f"Call has already ended (status={call.status})",
        )

    token = mint_simulator_token(call_id=call.id, resume_id=call.resume_id)
    # Build ws_url from the actual request host so the simulator connects
    # to the right backend regardless of PUBLIC_URL (ngrok vs localhost).
    base = str(request.base_url).rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return {
        "token": token,
        "ws_url": f"{ws_base}/ws/browser-media/{call.resume_id}?token={token}",
        "call": {
            "id": str(call.id),
            "resume_id": str(call.resume_id),
            "provider_call_id": call.provider_call_id,
            "status": call.status,
        },
    }


@router.websocket("/ws/browser-media/{resume_id}")
async def browser_media_stream(websocket: WebSocket, resume_id: str):
    """Browser-side media stream — mirrors /ws/exotel-media handler.

    Auth: requires ``?token=<jwt>`` query param signed with ``SECRET_KEY``,
    ``purpose="simulator_join"``, with matching ``resume_id`` claim.
    """
    token = websocket.query_params.get("token")
    payload = decode_token(token) if token else None
    if (
        payload is None
        or payload.get("purpose") != "simulator_join"
        or payload.get("resume_id") != str(resume_id)
    ):
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid simulator token",
        )
        return

    try:
        resume_uuid = uuid.UUID(resume_id)
        call_uuid = uuid.UUID(payload["call_id"])
    except (ValueError, KeyError):
        await websocket.close(code=1003, reason="Invalid session ID")
        return

    # Refuse a second join if the call is already in progress (prevents two-tab races).
    async with async_session_factory() as session:
        call = await session.get(Call, call_uuid)
        if call is None:
            await websocket.close(code=1008, reason="Call not found")
            return
        if call.status in {"in_progress", "completed", "failed", "no_answer"}:
            await websocket.close(
                code=1008,
                reason=f"Call cannot accept simulator join (status={call.status})",
            )
            return

    # The v2 runtime accepts, creates the session, and drives the full call loop.
    # Call messages and trace are persisted by the v2 persistence layer.
    runtime = get_call_v2_runtime()
    await runtime.handle(websocket, resume_id=resume_uuid, provider="browser")


@router.websocket("/ws/call-v2-sim/{call_id}")
async def call_v2_simulator_stream(websocket: WebSocket, call_id: str):
    """Dev/test websocket harness for call v2 fake-provider sessions.

    Accepts simulator telephony envelopes plus explicit ``stt.*`` control events
    so tests can drive v2 session traces deterministically without real STT/TTS.
    """

    if not settings.CALL_V2_SIMULATOR_ENABLED:
        await websocket.close(code=1008, reason="Call v2 simulator disabled")
        return
    if (
        settings.CALL_V2_SIMULATOR_TOKEN
        and websocket.query_params.get("token") != settings.CALL_V2_SIMULATOR_TOKEN
    ):
        await websocket.close(code=1008, reason="Invalid call v2 simulator token")
        return
    real_audio = _truthy_query_param(websocket.query_params.get("real_audio"))
    if real_audio and not settings.CALL_V2_SIMULATOR_REAL_AUDIO_ENABLED:
        await websocket.close(code=1008, reason="Call v2 real audio simulator disabled")
        return
    if real_audio and not settings.OPENAI_API_KEY:
        await websocket.close(code=1008, reason="OPENAI_API_KEY required")
        return

    await run_call_v2_simulator_websocket(
        websocket,
        call_id=call_id,
        real_audio=real_audio,
    )


def _truthy_query_param(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
