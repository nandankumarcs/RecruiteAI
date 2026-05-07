"""Schemas for dashboard metrics."""

from pydantic import BaseModel


class DashboardMetricsResponse(BaseModel):
    total_jobs: int
    active_jobs: int
    paused_jobs: int
    closed_jobs: int
    total_calls: int
    active_calls: int
    completed_calls: int
    average_score: float | None
    total_estimated_cost_usd: float | None = None
    average_cost_per_call_usd: float | None = None
    realtime_calls: int = 0
    pipeline_calls: int = 0
