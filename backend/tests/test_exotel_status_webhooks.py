from __future__ import annotations

import pytest
from httpx import AsyncClient

import app.routers.exotel_webhooks as exotel_webhooks_module
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume


@pytest.mark.asyncio
async def test_exotel_status_webhook_persists_recording_url(
    client: AsyncClient,
    db_session,
    test_user,
):
    job = Job(
        user_id=test_user.id,
        title="Backend Engineer",
        description="Build APIs",
        requirements="FastAPI",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Recording Candidate",
        phone_number="+917900000000",
        email="recording@example.com",
        file_path="/tmp/recording.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "backend engineer"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        provider="exotel",
        provider_call_id="EXO-STATUS-1",
        status="in_progress",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/exotel/status",
        data={
            "CallSid": "EXO-STATUS-1",
            "Status": "completed",
            "RecordingUrl": "https://api.exotel.com/recordings/exo-status-1.mp3",
            "RecordingDuration": "42",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.recording_url == "https://api.exotel.com/recordings/exo-status-1.mp3"
    assert call.recording_path == "https://api.exotel.com/recordings/exo-status-1.mp3"
    assert call.duration_seconds == 42


@pytest.mark.asyncio
async def test_exotel_status_webhook_reconciles_missing_recording_url(
    client: AsyncClient,
    db_session,
    test_user,
    monkeypatch,
):
    job = Job(
        user_id=test_user.id,
        title="Backend Engineer",
        description="Build APIs",
        requirements="FastAPI",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Reconcile Candidate",
        phone_number="+917911111111",
        email="reconcile@example.com",
        file_path="/tmp/reconcile.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "backend engineer"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        provider="exotel",
        provider_call_id="EXO-STATUS-2",
        status="in_progress",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    async def immediate_reconcile(call_id, call_sid: str):
        refreshed = await db_session.get(Call, call_id)
        refreshed.recording_url = f"https://api.exotel.com/recordings/{call_sid}.mp3"
        refreshed.recording_path = refreshed.recording_url
        refreshed.duration_seconds = 55
        await db_session.commit()

    created_tasks = []

    def fake_create_task(coro):
        task = exotel_webhooks_module.asyncio.get_running_loop().create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr(exotel_webhooks_module, "_reconcile_exotel_recording", immediate_reconcile)
    monkeypatch.setattr(exotel_webhooks_module.asyncio, "create_task", fake_create_task)

    response = await client.post(
        "/webhooks/exotel/status",
        data={
            "CallSid": "EXO-STATUS-2",
            "Status": "completed",
        },
    )

    assert response.status_code == 204
    assert created_tasks, "expected reconciliation task to be scheduled"
    await created_tasks[0]
    await db_session.refresh(call)
    assert call.recording_url == "https://api.exotel.com/recordings/EXO-STATUS-2.mp3"
    assert call.recording_path == "https://api.exotel.com/recordings/EXO-STATUS-2.mp3"
    assert call.duration_seconds == 55
