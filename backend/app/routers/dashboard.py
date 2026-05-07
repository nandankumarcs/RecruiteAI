"""Dashboard metrics router."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.call import Call
from app.models.job import Job
from app.models.user import User
from app.schemas.dashboard import DashboardMetricsResponse
from app.services.pricing import hydrate_cost_breakdown

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetricsResponse)
async def get_dashboard_metrics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job_rows = (
        await db.execute(select(Job).where(Job.user_id == current_user.id))
    ).scalars().all()
    call_rows = (
        await db.execute(
            select(Call)
            .join(Job, Call.job_id == Job.id)
            .where(Job.user_id == current_user.id)
        )
    ).scalars().all()

    scores = [
        float(call.ai_evaluation.get("overall_score"))
        for call in call_rows
        if isinstance(call.ai_evaluation, dict) and call.ai_evaluation.get("overall_score") is not None
    ]
    hydrated_costs = [
        hydrate_cost_breakdown(
            existing=call.cost_breakdown,
            provider=call.provider,
            duration_seconds=call.duration_seconds,
        )
        for call in call_rows
    ]
    estimated_costs = [
        float((cost or {}).get("estimated_total_usd") or 0)
        for cost in hydrated_costs
        if cost
    ]

    return DashboardMetricsResponse(
        total_jobs=len(job_rows),
        active_jobs=sum(1 for job in job_rows if job.status == "active"),
        paused_jobs=sum(1 for job in job_rows if job.status == "paused"),
        closed_jobs=sum(1 for job in job_rows if job.status == "closed"),
        total_calls=len(call_rows),
        active_calls=sum(1 for call in call_rows if call.status in {"queued", "ringing", "in_progress"}),
        completed_calls=sum(1 for call in call_rows if call.status == "completed"),
        average_score=(round(sum(scores) / len(scores), 1) if scores else None),
        total_estimated_cost_usd=(round(sum(estimated_costs), 4) if estimated_costs else None),
        average_cost_per_call_usd=(
            round(sum(estimated_costs) / len(estimated_costs), 4) if estimated_costs else None
        ),
        realtime_calls=sum(1 for call in call_rows if call.voice_runtime == "openai_realtime"),
        pipeline_calls=sum(
            1 for call in call_rows if call.voice_runtime == "deepgram_openai_pipeline"
        ),
    )
