"""Focused tests for cost optimization infrastructure."""

from __future__ import annotations

import uuid

import pytest
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


def test_twilio_provider_builds_expected_urls(monkeypatch):
    monkeypatch.setattr(telephony_module.settings, "PUBLIC_URL", "https://voice.example.test")
    provider = telephony_module.TwilioTelephonyProvider()

    urls = provider.build_urls(resume_id=uuid.UUID("11111111-1111-1111-1111-111111111111"))

    assert urls.answer_url == (
        "https://voice.example.test/webhooks/twilio/voice"
        "?call_resume_id=11111111-1111-1111-1111-111111111111"
    )
    assert urls.status_callback_url == "https://voice.example.test/webhooks/twilio/status"
    assert urls.recording_callback_url == "https://voice.example.test/webhooks/twilio/recording"


def test_voice_runtime_service_selects_openai_realtime_by_default(monkeypatch):
    selected: list[str] = []

    class FakeRealtimeBridge:
        def __init__(self):
            selected.append("realtime")

    monkeypatch.setattr(voice_runtime_module, "RealtimeBridge", FakeRealtimeBridge)

    voice_runtime_module.VoiceRuntimeService()

    assert selected == ["realtime"]

