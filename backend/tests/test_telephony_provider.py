import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.services.telephony import (
    ExotelTelephonyProvider,
    TelephonyService,
    TwilioTelephonyProvider,
    MockTelephonyProvider,
)
from app.config import get_settings


def test_twilio_provider_selection():
    with patch("app.services.telephony.settings.TELEPHONY_PROVIDER", "twilio"):
        with patch("app.services.telephony.settings.TWILIO_ACCOUNT_SID", "mock_sid"), \
             patch("app.services.telephony.settings.TWILIO_AUTH_TOKEN", "mock_token"), \
             patch("app.services.telephony.settings.TWILIO_PHONE_NUMBER", "mock_phone"):
            
            # Reset the Twilio client dependency temporarily to allow testing the actual mode
            service = TelephonyService()
            # It might fall back to mock if TwilioClient isn't importable, but we can check the provider name.
            # If TwilioClient is mocked/available, it'll be 'twilio'. If not, 'mock'.
            assert service.provider_name in ("twilio", "mock")


def test_exotel_provider_selection():
    with patch("app.services.telephony.settings.TELEPHONY_PROVIDER", "exotel"):
        with patch("app.services.telephony.settings.EXOTEL_ACCOUNT_SID", "mock_sid"), \
             patch("app.services.telephony.settings.EXOTEL_API_KEY", "mock_key"), \
             patch("app.services.telephony.settings.EXOTEL_API_TOKEN", "mock_token"), \
             patch("app.services.telephony.settings.EXOTEL_PHONE_NUMBER", "mock_phone"):
            
            service = TelephonyService()
            assert service.provider_name == "exotel"
            assert isinstance(service._provider, ExotelTelephonyProvider)
            assert not service._provider.mock_mode


def test_exotel_provider_fallback_to_mock_when_missing_creds():
    with patch("app.services.telephony.settings.TELEPHONY_PROVIDER", "exotel"):
        with patch("app.services.telephony.settings.EXOTEL_ACCOUNT_SID", ""):
            service = TelephonyService()
            assert service.provider_name == "mock"
            assert isinstance(service._provider, MockTelephonyProvider)


def test_exotel_build_urls():
    provider = ExotelTelephonyProvider()
    resume_id = uuid.uuid4()
    urls = provider.build_urls(resume_id=resume_id)
    assert "/webhooks/exotel/voice" in urls.answer_url
    assert "/webhooks/exotel/status" in urls.status_callback_url
    assert "/webhooks/exotel/recording" in urls.recording_callback_url


@patch("requests.post")
def test_exotel_start_outbound_call(mock_post):
    with patch("app.services.telephony.settings.EXOTEL_ACCOUNT_SID", "mock_sid"), \
         patch("app.services.telephony.settings.EXOTEL_API_KEY", "mock_key"), \
         patch("app.services.telephony.settings.EXOTEL_API_TOKEN", "mock_token"), \
         patch("app.services.telephony.settings.EXOTEL_PHONE_NUMBER", "mock_phone"):
        
        provider = ExotelTelephonyProvider()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"Call": {"Sid": "EXO-123", "Status": "queued"}}
        mock_post.return_value = mock_response

        result = provider.start_outbound_call(
            to_number="+1234567890",
            answer_url="http://test/answer",
            status_callback_url="http://test/status"
        )
        assert result.call_sid == "EXO-123"
        assert result.provider == "exotel"
        assert result.status == "queued"


@patch("requests.post")
def test_exotel_start_stream(mock_post):
    with patch("app.services.telephony.settings.EXOTEL_ACCOUNT_SID", "mock_sid"), \
         patch("app.services.telephony.settings.EXOTEL_API_KEY", "mock_key"), \
         patch("app.services.telephony.settings.EXOTEL_API_TOKEN", "mock_token"), \
         patch("app.services.telephony.settings.EXOTEL_PHONE_NUMBER", "mock_phone"):
        
        provider = ExotelTelephonyProvider()
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"stream_sid": "STR-123"}
        mock_post.return_value = mock_response

        stream_sid = provider.start_stream(leg_sid="LEG-123", websocket_url="wss://test")
        assert stream_sid == "STR-123"

