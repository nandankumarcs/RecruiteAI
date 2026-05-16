"""Browser-based telephony provider for local development and testing.

Mimics the Exotel wire protocol via a WebSocket the candidate joins from
their browser — no real PSTN call is placed, no telephony credits consumed.
Implements the same interface as ``ExotelTelephonyProvider`` /
``TwilioTelephonyProvider`` so it slots into ``TelephonyService`` as a peer.

This module is self-contained. Removing the simulator means deleting this
file plus the ``browser`` branches in ``telephony.py``, ``calls.py``,
``main.py``, ``pricing.py``, and the four bridge/TTS modules where
``_L16_PROVIDERS`` was introduced.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.config import get_settings
from app.core.security import create_access_token
from app.services.telephony import OutboundCallResult, OutboundCallUrls

settings = get_settings()

# Short-lived window for the candidate to open the sim page and accept the call.
# Long enough to comfortably switch tabs; short enough that a leaked URL expires fast.
SIM_TOKEN_TTL_MINUTES = 10


class BrowserTelephonyProvider:
    """Simulator provider — peer of Twilio/Exotel for dev/testing.

    Lifecycle:
      build_urls          -> returns the status webhook URL the frontend will POST to.
                             ``answer_url`` is unused by this provider (no real PSTN call).
      start_outbound_call -> creates a synthetic SIM-<uuid> call_sid; no external API call.
      end_call / say_and_hangup / start_recording / fetch_call_details -> no-ops
                          (recording happens automatically server-side via
                          SimulatorCallRecorder; the other methods have no
                          equivalent in a browser-only flow).
    """

    provider_name = "browser"
    enable_mock_progression = False  # bridge drives lifecycle, not a fake timer
    mock_mode = False                 # prevents TelephonyService swap to MockProvider

    def build_urls(self, *, resume_id: uuid.UUID) -> OutboundCallUrls:
        # Reuse Exotel's status webhook so the simulator exercises the same
        # production status-callback code path on accept/hangup/decline.
        base = settings.PUBLIC_URL.rstrip("/")
        return OutboundCallUrls(
            answer_url=f"{base}/webhooks/exotel/status",            # unused for browser
            status_callback_url=f"{base}/webhooks/exotel/status",   # reused intentionally
            recording_callback_url=None,                            # recording is local
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
            call_sid=f"SIM-{uuid.uuid4()}",
            status="queued",
            provider=self.provider_name,
        )

    def end_call(self, call_sid: str) -> None:
        # The frontend triggers websocket close + status webhook on hangup.
        return

    def say_and_hangup(self, call_sid: str, message: str) -> None:
        return

    def start_recording(self, call_sid: str, callback_url: str | None = None) -> None:
        # Recording is captured automatically by SimulatorCallRecorder; this is a no-op.
        return

    def fetch_call_details(self, call_sid: str) -> dict | None:
        return None


def mint_simulator_token(*, call_id: uuid.UUID, resume_id: uuid.UUID) -> str:
    """Short-lived JWT that authorizes the candidate's WebSocket join.

    Uses the existing ``SECRET_KEY`` / ``ALGORITHM`` (via
    :func:`app.core.security.create_access_token`) so no new cryptographic
    surface is added. The ``purpose`` claim distinguishes simulator tokens from
    regular API access tokens — the websocket handler refuses anything else.
    """
    return create_access_token(
        data={
            "sub": str(call_id),
            "call_id": str(call_id),
            "resume_id": str(resume_id),
            "purpose": "simulator_join",
        },
        expires_delta=timedelta(minutes=SIM_TOKEN_TTL_MINUTES),
    )
