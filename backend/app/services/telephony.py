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


class ExotelTelephonyProvider:
    provider_name = "exotel"
    enable_mock_progression = False

    def __init__(self) -> None:
        self.mock_mode = bool(
            not settings.EXOTEL_ACCOUNT_SID
            or not settings.EXOTEL_API_KEY
            or not settings.EXOTEL_API_TOKEN
            or not settings.EXOTEL_PHONE_NUMBER
        )
        if self.mock_mode:
            import sys
            print(f"DEBUG: Exotel Mock Mode Active. Missing: SID={not settings.EXOTEL_ACCOUNT_SID}, KEY={not settings.EXOTEL_API_KEY}, TOKEN={not settings.EXOTEL_API_TOKEN}, PHONE={not settings.EXOTEL_PHONE_NUMBER}", file=sys.stderr, flush=True)
            
        self._base_url = f"https://{settings.EXOTEL_SUBDOMAIN}/v2/accounts/{settings.EXOTEL_ACCOUNT_SID}"
        self._auth = (settings.EXOTEL_API_KEY, settings.EXOTEL_API_TOKEN)

    def build_urls(self, *, resume_id: uuid.UUID) -> OutboundCallUrls:
        base = settings.PUBLIC_URL.rstrip("/")
        return OutboundCallUrls(
            answer_url=f"{base}/webhooks/exotel/voice/{resume_id}",
            status_callback_url=f"{base}/webhooks/exotel/status",
            recording_callback_url=f"{base}/webhooks/exotel/recording",
        )

    def start_outbound_call(
        self,
        *,
        to_number: str,
        answer_url: str,
        status_callback_url: str,
        recording_callback_url: str | None = None,
    ) -> OutboundCallResult:
        if self.mock_mode:
            return MockTelephonyProvider().start_outbound_call(
                to_number=to_number,
                answer_url=answer_url,
                status_callback_url=status_callback_url,
                recording_callback_url=recording_callback_url,
            )

        import requests
        
        base_url = f"https://{settings.EXOTEL_SUBDOMAIN}/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}"
        print(f"DEBUG: Exotel Url={answer_url}")
        # Ensure number has +91 prefix for India if not already present
        clean_number = to_number.strip()
        if clean_number.startswith("+"):
            clean_number = clean_number[1:]
        
        if clean_number.startswith("0"):
            clean_number = "91" + clean_number[1:]
        elif len(clean_number) == 10 and not clean_number.startswith("91"):
            clean_number = "91" + clean_number
        
        resume_id = answer_url.rstrip("/").split("/")[-1]
        payload = {
            "From": clean_number,  # The Customer
            "CallerId": settings.EXOTEL_PHONE_NUMBER, # The ExoPhone
            "Url": "http://my.exotel.com/crownstack1/exoml/start_voice/1244328",
            "CustomField": resume_id,
            "StatusCallback": status_callback_url,
            "Record": "true",
        }
        
        try:
            response = requests.post(f"{base_url}/Calls/connect.json", auth=self._auth, data=payload, timeout=10)
            print(f"DEBUG: Exotel Response Status: {response.status_code}")
            print(f"DEBUG: Exotel Response Body: {response.text}")
            response.raise_for_status()
            data = response.json()
            call_sid = data.get("Call", {}).get("Sid", "") or f"EXO-{uuid.uuid4()}"
            status = data.get("Call", {}).get("Status", "queued")
            
            # Cache the mapping for media stream fallback
            if call_sid and resume_id:
                from app.services.telephony_cache import cache_exotel_call
                cache_exotel_call(call_sid, resume_id)
            
            return OutboundCallResult(
                call_sid=call_sid,
                status=status,
                provider=self.provider_name,
            )
        except Exception as e:
            # Fallback for dev if API call fails but we want to simulate
            import logging
            logging.error(f"Exotel outbound call failed: {e}")
            return MockTelephonyProvider().start_outbound_call(
                to_number=to_number,
                answer_url=answer_url,
                status_callback_url=status_callback_url,
            )

    def start_stream(self, *, leg_sid: str, websocket_url: str) -> str:
        """Exotel-specific: start bi-directional media stream on a call leg."""
        if self.mock_mode:
            return ""
        import requests
        payload = {
            "direction": "bidirectional",
            "url": websocket_url,
            "content_type": "audio/L16;rate=8000"
        }
        try:
            url = f"{self._base_url}/legs/{leg_sid}/actions/start_stream"
            response = requests.post(url, auth=self._auth, json=payload, timeout=5)
            print(f"DEBUG: Exotel Response Status: {response.status_code}")
            print(f"DEBUG: Exotel Response Body: {response.text}")
            response.raise_for_status()
            response_json = response.json()
            return response_json.get("stream_sid", "")
        except Exception as e:
            import logging
            logging.error(f"Exotel start_stream failed: {e}")
            return ""

    def end_call(self, call_sid: str) -> None:
        if self.mock_mode:
            return
        import requests
        try:
            requests.post(
                f"{self._base_url}/calls/{call_sid}",
                auth=self._auth,
                data={"Status": "completed"},
                timeout=5
            )
        except Exception:
            pass

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        if self.mock_mode:
            return
        # Basic say and hangup via Exotel API
        pass

    def start_recording(self, call_sid: str, callback_url: str | None = None) -> None:
        return


class TwilioTelephonyProvider:
    provider_name = "twilio"
    enable_mock_progression = False

    def __init__(self) -> None:
        self.mock_mode = bool(
            getattr(settings, "TWILIO_MOCK_MODE", False)
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

        clean_number = to_number.strip()
        if not clean_number.startswith("+"):
            if len(clean_number) == 10:
                clean_number = "+91" + clean_number
            else:
                clean_number = "+" + clean_number

        call = self._client.calls.create(
            to=clean_number,
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
        elif provider_name == "exotel":
            self._provider = ExotelTelephonyProvider()
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
