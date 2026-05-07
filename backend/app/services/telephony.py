"""
Telephony service abstraction for outbound calls.

Uses Twilio when configured, otherwise falls back to a mock mode suitable for
local verification and tests.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()

try:
    from twilio.rest import Client as TwilioClient
except Exception:  # pragma: no cover
    TwilioClient = None


class OutboundCallResult(BaseModel):
    call_sid: str
    status: str
    provider: str


class TelephonyService:
    """Provider-backed outbound telephony service."""

    def __init__(self):
        self.enable_mock_progression = True
        self.mock_mode = bool(
            settings.TWILIO_MOCK_MODE
            or not settings.TWILIO_ACCOUNT_SID
            or not settings.TWILIO_AUTH_TOKEN
            or not settings.TWILIO_PHONE_NUMBER
            or TwilioClient is None
        )

        self._client = None
        if not self.mock_mode and TwilioClient is not None:
            self._client = TwilioClient(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )

    def start_outbound_call(
        self,
        *,
        to_number: str,
        twiml_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ) -> OutboundCallResult:
        if self.mock_mode or self._client is None:
            return OutboundCallResult(
                call_sid=f"MOCK-{uuid.uuid4()}",
                status="queued",
                provider="mock",
            )

        call = self._client.calls.create(
            to=to_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=twiml_url,
            record=True,
            recording_status_callback=recording_callback_url,
            recording_status_callback_event=["in-progress", "completed", "absent"],
            recording_status_callback_method="POST",
            status_callback=status_callback_url,
            status_callback_event=["initiated", "ringing", "answered", "completed"],
            status_callback_method="POST",
        )
        return OutboundCallResult(
            call_sid=call.sid,
            status=call.status or "queued",
            provider="twilio",
        )

    def end_call(self, call_sid: str) -> None:
        if self.mock_mode or self._client is None:
            return

        self._client.calls(call_sid).update(status="completed")

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        if self.mock_mode or self._client is None:
            return

        twiml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            f"<Response><Say>{message}</Say><Hangup/></Response>"
        )
        self._client.calls(call_sid).update(twiml=twiml)


def get_telephony_service() -> TelephonyService:
    """Dependency factory for telephony service."""
    return TelephonyService()
