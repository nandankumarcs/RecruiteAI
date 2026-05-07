"""Voice runtime dispatcher."""

from __future__ import annotations

from app.config import get_settings
from app.services.deepgram_runtime import DeepgramOpenAIPipelineRuntime
from app.services.realtime_bridge import RealtimeBridge

settings = get_settings()


class VoiceRuntimeService:
    """Selects the configured runtime while keeping a single router contract."""

    def __init__(self):
        runtime_name = (settings.VOICE_RUNTIME or "openai_realtime").strip().lower()
        if runtime_name == "deepgram_openai_pipeline":
            self._runtime = DeepgramOpenAIPipelineRuntime()
        else:
            self._runtime = RealtimeBridge()

    async def handle(self, websocket, resume_id, provider: str = "twilio"):
        await self._runtime.handle(websocket, resume_id, provider=provider)


def get_voice_runtime_service() -> VoiceRuntimeService:
    return VoiceRuntimeService()
