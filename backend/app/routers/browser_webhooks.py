"""WebSocket + auth endpoints for the browser telephony simulator.

This file is the only router-level surface added by the simulator. Delete the
file + remove its registration in ``main.py`` to fully uninstall.

Endpoints:
  - GET  /api/sim/token/{call_id}         — mint a short-lived join token (auth required)
  - WS   /ws/browser-media/{resume_id}    — Exotel-protocol websocket (token-auth via query param)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.security import decode_token
from app.database import async_session_factory, get_db
from app.models import Call, User
from app.services.simulator_recorder import RecordingWebSocket, SimulatorCallRecorder
from app.services.telephony_browser import mint_simulator_token
from app.services.voice_runtime import get_voice_runtime_service

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.get("/api/sim/token/{call_id}")
async def get_simulator_token(
    call_id: uuid.UUID,
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
    public = settings.PUBLIC_URL.rstrip("/")
    ws_base = (
        public.replace("https://", "wss://").replace("http://", "ws://")
    )
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

    await websocket.accept()
    logger.info(
        "Browser simulator websocket accepted (call=%s, resume=%s)",
        call_uuid,
        resume_uuid,
    )

    recorder = SimulatorCallRecorder(call_id=call_uuid)
    recording_ws = RecordingWebSocket(websocket, recorder)

    try:
        runtime = get_voice_runtime_service()
        await runtime.handle(recording_ws, resume_uuid, provider="browser")
    except Exception as e:
        logger.error("Browser simulator stream error: %s", e, exc_info=True)
    finally:
        # Persist the recording even on error — partial audio is still useful.
        if not recorder.is_empty():
            try:
                await _persist_simulator_recording(call_uuid, recorder)
            except Exception as e:
                logger.error(
                    "Failed to persist simulator recording (call=%s): %s",
                    call_uuid,
                    e,
                    exc_info=True,
                )


def _write_wav_sync(full_path: Path, wav_bytes: bytes) -> None:
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(wav_bytes)


async def _persist_simulator_recording(
    call_id: uuid.UUID, recorder: SimulatorCallRecorder
) -> None:
    """Write WAV bytes to local disk and stamp the Call row with recording_*.

    Design:
      - Storage abstraction (services/storage.py) takes an UploadFile, not bytes.
        We write directly under STORAGE_LOCAL_PATH/recordings to avoid a fake
        UploadFile wrapper. S3 support for simulator recordings is intentionally
        deferred — simulator is dev-only.
      - recording_url points at the existing auth-protected
        /api/calls/{id}/recording endpoint so the CallDetail page renders
        simulator recordings identically to Exotel/Twilio ones.
      - auto_evaluate_call_if_ready only reads `transcript`, never
        `recording_url` (call_evaluation.py:36-43), so the bridge's earlier
        `_update_call_finished` running before this finally block is fine.
    """
    wav_bytes = recorder.to_wav_bytes()
    base_dir = Path(settings.STORAGE_LOCAL_PATH) / "recordings"
    full_path = base_dir / f"{call_id}.wav"
    relative_path = f"recordings/{call_id}.wav"

    # `wave` + `open` are blocking; run in a thread so we don't stall the loop.
    await asyncio.to_thread(_write_wav_sync, full_path, wav_bytes)

    async with async_session_factory() as session:
        call = await session.get(Call, call_id)
        if call is None:
            return
        call.recording_path = relative_path
        public = settings.PUBLIC_URL.rstrip("/")
        call.recording_url = f"{public}/api/calls/{call_id}/recording"
        await session.commit()

    logger.info(
        "Saved simulator recording (call=%s, path=%s, size=%d bytes)",
        call_id,
        full_path,
        os.path.getsize(full_path) if full_path.exists() else 0,
    )
