"""Telephony abstraction with Twilio and mock implementations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from xml.sax.saxutils import escape

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


@dataclass(frozen=True)
class OutboundCallUrls:
    answer_url: str
    status_callback_url: str
    recording_callback_url: str | None = None


class MockTelephonyProvider:
    provider_name = "mock"
    enable_mock_progression = True

    def build_urls(self, *, resume_id: uuid.UUID) -> OutboundCallUrls:
        base = settings.PUBLIC_URL.rstrip("/")
        return OutboundCallUrls(
            answer_url=f"{base}/webhooks/mock/voice?call_resume_id={resume_id}",
            status_callback_url=f"{base}/webhooks/mock/status",
            recording_callback_url=f"{base}/webhooks/mock/recording",
        )

    def start_outbound_call(
        self,
        *,
        to_number: str,
        answer_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ) -> OutboundCallResult:
        return OutboundCallResult(
            call_sid=f"MOCK-{uuid.uuid4()}",
            status="queued",
            provider=self.provider_name,
        )

    def end_call(self, call_sid: str) -> None:
        return

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        return

    def start_recording(self, call_sid: str, callback_url: str | None = None) -> None:
        return


class TwilioTelephonyProvider:
    provider_name = "twilio"
    enable_mock_progression = False

    def __init__(self) -> None:
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

    def build_urls(self, *, resume_id: uuid.UUID) -> OutboundCallUrls:
        base = settings.PUBLIC_URL.rstrip("/")
        return OutboundCallUrls(
            answer_url=f"{base}/webhooks/twilio/voice?call_resume_id={resume_id}",
            status_callback_url=f"{base}/webhooks/twilio/status",
            recording_callback_url=f"{base}/webhooks/twilio/recording",
        )

    def start_outbound_call(
        self,
        *,
        to_number: str,
        answer_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ) -> OutboundCallResult:
        if self.mock_mode or self._client is None:
            return MockTelephonyProvider().start_outbound_call(
                to_number=to_number,
                answer_url=answer_url,
                status_callback_url=status_callback_url,
                recording_callback_url=recording_callback_url,
            )

        call = self._client.calls.create(
            to=to_number,
            from_=settings.TWILIO_PHONE_NUMBER,
            url=answer_url,
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
            provider=self.provider_name,
        )

    def end_call(self, call_sid: str) -> None:
        if self.mock_mode or self._client is None:
            return
        self._client.calls(call_sid).update(status="completed")

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        if self.mock_mode or self._client is None:
            return
        safe_message = escape(message)
        twiml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            f"<Response><Say>{safe_message}</Say><Hangup/></Response>"
        )
        self._client.calls(call_sid).update(twiml=twiml)

    def start_recording(self, call_sid: str, callback_url: str | None = None) -> None:
        return


class TelephonyService:
    """Facade that selects the configured telephony provider."""

    def __init__(self):
        provider_name = (settings.TELEPHONY_PROVIDER or "twilio").strip().lower()
        if provider_name == "twilio":
            self._provider = TwilioTelephonyProvider()
        else:
            self._provider = MockTelephonyProvider()

        if getattr(self._provider, "mock_mode", False):
            self._provider = MockTelephonyProvider()

        self.provider_name = self._provider.provider_name
        self.enable_mock_progression = self._provider.enable_mock_progression

    def build_urls(self, *, resume_id: uuid.UUID) -> OutboundCallUrls:
        return self._provider.build_urls(resume_id=resume_id)

    def start_outbound_call(
        self,
        *,
        to_number: str,
        answer_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ) -> OutboundCallResult:
        return self._provider.start_outbound_call(
            to_number=to_number,
            answer_url=answer_url,
            status_callback_url=status_callback_url,
            recording_callback_url=recording_callback_url,
        )

    def end_call(self, call_sid: str) -> None:
        self._provider.end_call(call_sid)

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        self._provider.say_and_hangup(call_sid, message)

    def start_recording(self, call_sid: str, callback_url: str | None = None) -> None:
        self._provider.start_recording(call_sid, callback_url)


def get_telephony_service() -> TelephonyService:
    """Dependency factory for telephony service."""
    return TelephonyService()
