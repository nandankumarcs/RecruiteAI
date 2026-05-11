"""Voice runtime dispatcher."""

from __future__ import annotations

import logging

from app.config import get_settings
from app.services.deepgram_runtime import DeepgramOpenAIPipelineRuntime
from app.services.realtime_bridge import RealtimeBridge

settings = get_settings()
logger = logging.getLogger(__name__)


class VoiceRuntimeService:
    """Selects the configured runtime while keeping a single router contract."""

    def __init__(self):
        self._runtime_name = settings.VOICE_RUNTIME
        self._openai_runtime = RealtimeBridge()
        self._deepgram_runtime = DeepgramOpenAIPipelineRuntime()

    async def handle(self, websocket, resume_id, provider: str = "twilio"):
        if self._runtime_name == "deepgram_openai":
            runtime = self._deepgram_runtime
        else:
            runtime = self._openai_runtime
        
        logger.info("Using voice runtime: %s", type(runtime).__name__)
        await runtime.handle(websocket, resume_id, provider=provider)



def get_voice_runtime_service() -> VoiceRuntimeService:
    return VoiceRuntimeService()

