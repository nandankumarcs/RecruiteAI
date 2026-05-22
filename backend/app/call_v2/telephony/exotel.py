"""Exotel media-stream adapter for call v2."""

from __future__ import annotations

from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter


class ExotelMediaTelephonyAdapter(BrowserSimulatorTelephonyAdapter):
    """Adapter for Exotel's L16 media-stream envelope.

    The browser simulator intentionally mirrors Exotel's event shape. This
    subclass keeps provider identity explicit while reusing the same parser and
    outbound message builder.
    """

    provider = "exotel"
