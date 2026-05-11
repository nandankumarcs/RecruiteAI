from __future__ import annotations

import logging
from typing import Any
from langsmith import Client
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self):
        self.client = Client(
            api_key=settings.LANGSMITH_API_KEY,
            api_url=settings.LANGSMITH_ENDPOINT,
        ) if settings.LANGSMITH_API_KEY else None
        self.project_name = settings.LANGSMITH_PROJECT

    def get_call_turn_analytics(self, call_id: str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        
        try:
            # Filter runs by call_id in metadata
            runs = self.client.list_runs(
                project_name=self.project_name,
                filter=f'and(eq(metadata.call_id, "{call_id}"))',
                execution_order=1
            )
            
            analytics = []
            for run in runs:
                # Extract latency and cost from run
                turn_data = {
                    "start_time": run.start_time.isoformat() if run.start_time else None,
                    "end_time": run.end_time.isoformat() if run.end_time else None,
                    "latency_ms": (run.end_time - run.start_time).total_seconds() * 1000 if run.start_time and run.end_time else 0,
                    "input_tokens": run.prompt_tokens or 0,
                    "output_tokens": run.completion_tokens or 0,
                    "total_tokens": run.total_tokens or 0,
                    "cost_usd": run.total_cost or 0,
                    "name": run.name,
                    "run_url": self.client.get_run_url(run=run) if self.client else None,
                }

                analytics.append(turn_data)
            
            # Sort by start time
            analytics.sort(key=lambda x: x["start_time"] or "")
            return analytics
        except Exception as e:
            logger.error(f"Failed to fetch LangSmith analytics for call {call_id}: {e}")
            return []

analytics_service = AnalyticsService()
