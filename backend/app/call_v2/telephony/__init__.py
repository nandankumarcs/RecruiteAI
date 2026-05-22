"""Telephony adapter foundation for call v2."""

from app.call_v2.telephony.base import TelephonyAdapter, TelephonyInboundEvent
from app.call_v2.telephony.exotel import ExotelMediaTelephonyAdapter
from app.call_v2.telephony.simulator import BrowserSimulatorTelephonyAdapter

__all__ = [
    "BrowserSimulatorTelephonyAdapter",
    "ExotelMediaTelephonyAdapter",
    "TelephonyAdapter",
    "TelephonyInboundEvent",
]
