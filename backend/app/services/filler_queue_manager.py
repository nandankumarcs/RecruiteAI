"""
Filler Queue Manager Service

Manages filler audio selection and queueing rules for masking compute gaps
during voice calls. Implements threshold-based logic to determine when to play
short filler utterances (e.g., "understood", "got it") to improve perceived
responsiveness without creating verbal spam.

**Validates: Requirements 6.2, 6.4**
"""

from datetime import datetime, timezone
from typing import Optional

from app.config import get_settings


class FillerQueueManager:
    """
    Manages filler audio selection and queueing rules.
    
    Implements threshold-based logic to determine when filler audio should be
    played to mask compute gaps during voice calls. Ensures fillers are only
    used when necessary (latency exceeds threshold) and prevents excessive
    filler usage through cooldown periods.
    
    **Validates: Requirements 6.2, 6.4**
    """
    
    # Only play filler if gap exceeds this threshold (ms)
    FILLER_THRESHOLD_MS = 300
    
    # Minimum time between consecutive fillers (ms)
    FILLER_COOLDOWN_MS = 5000
    
    def __init__(self, prompt_audio_service):
        """
        Initialize FillerQueueManager with prompt audio service dependency.
        
        Args:
            prompt_audio_service: Service for retrieving pre-generated audio assets
        """
        self.prompt_audio = prompt_audio_service
        
        # Available filler keys for selection
        self._filler_keys = [
            "filler_understood",
            "filler_got_it",
            "filler_okay",
            "filler_thanks",
            "filler_sure",
            "filler_one_moment"
        ]
    
    async def should_play_filler(
        self,
        *,
        estimated_latency_ms: int,
        last_filler_played_at: Optional[datetime] = None,
        main_prompt_ready: bool = False,
        last_filler_key: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if filler should play based on latency threshold and cooldown.
        
        Implements the following rules:
        1. Skip if main prompt already ready
        2. Skip if estimated latency < FILLER_THRESHOLD_MS
        3. Skip if filler played recently (within FILLER_COOLDOWN_MS)
        4. Otherwise, select and return filler key
        
        Args:
            estimated_latency_ms: Estimated time until main prompt is ready (ms)
            last_filler_played_at: Timestamp of last filler playback (optional)
            main_prompt_ready: Whether the main prompt is already ready
        
        Returns:
            Tuple of (should_play, filler_key):
                - should_play: True if filler should be played
                - filler_key: Selected filler key if should_play is True, None otherwise
        
        **Validates: Requirements 6.2, 6.4**
        """
        # Rule 0: Global disable via config
        if not get_settings().PIPELINE_FILLERS_ENABLED:
            return (False, None)

        # Rule 1: Skip if main prompt ready
        if main_prompt_ready:
            return (False, None)
        
        # Rule 2: Skip if latency below threshold
        if estimated_latency_ms < self.FILLER_THRESHOLD_MS:
            return (False, None)
        
        # Rule 3: Check cooldown
        if last_filler_played_at:
            now = datetime.now(timezone.utc)
            reference = last_filler_played_at
            if reference.tzinfo is None:
                reference = reference.replace(tzinfo=timezone.utc)
            time_since_last = (now - reference).total_seconds() * 1000
            if time_since_last < self.FILLER_COOLDOWN_MS:
                return (False, None)

        # Rule 4: Select filler
        filler_key = self._select_filler_key(last_filler_key=last_filler_key)
        return (True, filler_key)
    
    async def get_filler_asset(self, filler_key: str):
        """
        Retrieve ready filler asset from prompt audio service.
        
        Args:
            filler_key: Template key for the filler asset
        
        Returns:
            AudioPromptAsset if found and ready, None otherwise
        """
        return await self.prompt_audio.get_ready_audio_asset(
            template_key=filler_key
        )
    
    def _select_filler_key(self, last_filler_key: Optional[str] = None) -> str:
        """
        Select next filler key using round-robin to avoid repetition.
        
        Args:
            last_filler_key: Previously played filler key (optional)
        
        Returns:
            Selected filler key from available filler keys
        """
        if not last_filler_key:
            return self._filler_keys[0]
        
        try:
            last_index = self._filler_keys.index(last_filler_key)
            next_index = (last_index + 1) % len(self._filler_keys)
            return self._filler_keys[next_index]
        except ValueError:
            # If last_filler_key not found, return first key
            return self._filler_keys[0]
