"""Provider adapter contracts for call v2 telephony events."""

from __future__ import annotations

from typing import Protocol, TypeAlias

from app.call_v2.events import (
    ClearOutboundAudio,
    SendAudioFrame,
    TelephonyAudioFrame,
    TelephonyDtmf,
    TelephonyStreamStarted,
    TelephonyStreamStopped,
)

TelephonyInboundEvent: TypeAlias = (
    TelephonyStreamStarted
    | TelephonyAudioFrame
    | TelephonyDtmf
    | TelephonyStreamStopped
)


class TelephonyAdapter(Protocol):
    """Normalizes provider wire messages and builds provider wire commands."""

    provider: str

    def parse_inbound_message(
        self,
        message: str | dict,
        *,
        backend_received_at_ms: int,
    ) -> TelephonyInboundEvent | None:
        """Convert a provider WebSocket message into a v2 event.

        Returns None for provider lifecycle messages that have no runtime
        meaning, such as a browser/simulator `connected` acknowledgement.
        """

    def build_send_audio(self, command: SendAudioFrame) -> dict:
        """Convert a normalized outbound audio command into provider JSON."""

    def build_clear_audio(self, command: ClearOutboundAudio) -> dict:
        """Convert a normalized clear-audio command into provider JSON."""

