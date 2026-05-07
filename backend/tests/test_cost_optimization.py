"""Focused tests for cost optimization infrastructure."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume
from app.services import telephony as telephony_module
from app.services import voice_runtime as voice_runtime_module
from app.services.pricing import hydrate_cost_breakdown


def test_hydrate_cost_breakdown_backfills_legacy_telephony_cost():
    cost_breakdown = hydrate_cost_breakdown(
        existing=None,
        provider="twilio",
        duration_seconds=135,
    )

    assert cost_breakdown is not None
    assert cost_breakdown["provider"] == "twilio"
    assert cost_breakdown["costs"]["telephony_usd"] > 0
    assert cost_breakdown["estimated_total_usd"] == cost_breakdown["costs"]["telephony_usd"]


def test_plivo_provider_builds_expected_urls(monkeypatch):
    monkeypatch.setattr(telephony_module.settings, "PUBLIC_URL", "https://voice.example.test")
    provider = telephony_module.PlivoTelephonyProvider()

    urls = provider.build_urls(resume_id=uuid.UUID("11111111-1111-1111-1111-111111111111"))

    assert urls.answer_url == (
        "https://voice.example.test/webhooks/plivo/answer"
        "?call_resume_id=11111111-1111-1111-1111-111111111111"
    )
    assert urls.status_callback_url == "https://voice.example.test/webhooks/plivo/status"
    assert urls.recording_callback_url == "https://voice.example.test/webhooks/plivo/recording"


@pytest.mark.asyncio
async def test_plivo_answer_webhook_includes_bidirectional_stream(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(
        telephony_module.settings,
        "PUBLIC_URL",
        "https://voice.example.test",
    )
    from app.routers import plivo_webhooks as plivo_router_module

    monkeypatch.setattr(
        plivo_router_module.settings,
        "PUBLIC_URL",
        "https://voice.example.test",
    )

    response = await client.post(
        "/webhooks/plivo/answer",
        params={"call_resume_id": "22222222-2222-2222-2222-222222222222"},
    )

    assert response.status_code == 200
    body = response.text
    assert "bidirectional=\"true\"" in body
    assert "audio/x-mulaw;rate=8000" in body
    assert "/webhooks/plivo/stream-status" in body
    assert "wss://voice.example.test/ws/plivo-media/22222222-2222-2222-2222-222222222222" in body


@pytest.mark.asyncio
async def test_plivo_status_webhook_updates_status_and_cost(
    client: AsyncClient,
    db_session,
    test_user,
):
    job = Job(
        user_id=test_user.id,
        title="Voice Role",
        description="Test role",
        requirements="Python",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Plivo Candidate",
        phone_number="+1 555 444 3333",
        email="plivo@example.com",
        file_path="/tmp/plivo.pdf",
        file_type="pdf",
        raw_text="Candidate",
        status="parsed",
        parsed_data={"summary": "Parsed"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        provider="plivo",
        provider_call_id="PLIVO-CALL-1",
        status="queued",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    response = await client.post(
        "/webhooks/plivo/status",
        data={
            "CallUUID": "PLIVO-CALL-1",
            "CallStatus": "completed",
            "Duration": "120",
        },
    )

    assert response.status_code == 204
    await db_session.refresh(call)
    assert call.status == "completed"
    assert call.duration_seconds == 120
    assert call.cost_breakdown is not None
    assert call.cost_breakdown["costs"]["telephony_usd"] > 0


def test_voice_runtime_service_selects_pipeline_runtime(monkeypatch):
    selected: list[str] = []

    class FakeRealtimeBridge:
        def __init__(self):
            selected.append("realtime")

    class FakePipelineRuntime:
        def __init__(self):
            selected.append("pipeline")

    monkeypatch.setattr(
        voice_runtime_module,
        "RealtimeBridge",
        FakeRealtimeBridge,
    )
    monkeypatch.setattr(
        voice_runtime_module,
        "DeepgramOpenAIPipelineRuntime",
        FakePipelineRuntime,
    )
    monkeypatch.setattr(
        voice_runtime_module.settings,
        "VOICE_RUNTIME",
        "deepgram_openai_pipeline",
    )

    voice_runtime_module.VoiceRuntimeService()

    assert selected == ["pipeline"]
