"""Dashboard metrics router."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.call import Call
from app.models.job import Job
from app.models.user import User
from app.schemas.dashboard import DashboardMetricsResponse
from app.services.pricing import hydrate_cost_breakdown

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _delta_ms(metrics: dict, start_key: str, end_key: str) -> float | None:
    start = metrics.get(start_key)
    end = metrics.get(end_key)
    if not start or not end:
        return None
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        delta = (e - s).total_seconds() * 1000.0
        return delta if delta > 0 else None
    except (ValueError, TypeError):
        return None


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

    latencies = []
    for call in call_rows:
        delta = _delta_ms(
            call.latency_metrics or {},
            "stream_connected_at",
            "first_assistant_audio_at",
        )
        if delta is not None:
            latencies.append(delta)

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
        pipeline_calls=sum(1 for call in call_rows if call.voice_runtime == "deepgram_openai"),
        v2_calls=sum(1 for call in call_rows if call.voice_runtime == "call_v2"),
        average_latency_ms=(sum(latencies) / len(latencies) if latencies else None),
    )


@router.get("/benchmark")
async def get_runtime_benchmark(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-runtime aggregate metrics over all completed calls for this user.

    Groups calls by their actual voice_runtime label, so new runtimes appear
    automatically without code changes. Each entry reports cost, latency, and
    quality independently.
    """
    call_rows = (
        await db.execute(
            select(Call)
            .join(Job, Call.job_id == Job.id)
            .where(Job.user_id == current_user.id, Call.status == "completed")
        )
    ).scalars().all()

    runtimes = sorted({c.voice_runtime for c in call_rows if c.voice_runtime})
    result: dict = {}

    for runtime in runtimes:
        calls = [c for c in call_rows if c.voice_runtime == runtime]

        costs = [
            float((hydrate_cost_breakdown(
                existing=c.cost_breakdown,
                provider=c.provider,
                duration_seconds=c.duration_seconds,
            ) or {}).get("estimated_total_usd") or 0)
            for c in calls
        ]

        ttfa_values = [
            v for c in calls
            if (v := _delta_ms(c.latency_metrics or {}, "stream_connected_at", "first_assistant_audio_at")) is not None
        ]

        answer_values = [
            v for c in calls
            if (v := _delta_ms(c.latency_metrics or {}, "call_requested_at", "call_answered_at")) is not None
        ]

        scores = [
            float(c.ai_evaluation.get("overall_score"))
            for c in calls
            if isinstance(c.ai_evaluation, dict) and c.ai_evaluation.get("overall_score") is not None
        ]

        cost_breakdown_agg: dict[str, float] = {
            "llm_usd": 0.0,
            "stt_usd": 0.0,
            "tts_usd": 0.0,
            "telephony_usd": 0.0,
        }
        for c in calls:
            bd = hydrate_cost_breakdown(
                existing=c.cost_breakdown,
                provider=c.provider,
                duration_seconds=c.duration_seconds,
            ) or {}
            for key in cost_breakdown_agg:
                cost_breakdown_agg[key] += float((bd.get("costs") or {}).get(key) or 0)

        result[runtime] = {
            "call_count": len(calls),
            "cost": {
                "total_usd": round(sum(costs), 4),
                "average_per_call_usd": round(sum(costs) / len(costs), 4) if costs else None,
                "breakdown_totals_usd": {k: round(v, 4) for k, v in cost_breakdown_agg.items()},
            },
            "latency": {
                "avg_time_to_first_audio_ms": round(sum(ttfa_values) / len(ttfa_values), 1) if ttfa_values else None,
                "p50_time_to_first_audio_ms": (
                    round(sorted(ttfa_values)[len(ttfa_values) // 2], 1) if ttfa_values else None
                ),
                "avg_answer_latency_ms": round(sum(answer_values) / len(answer_values), 1) if answer_values else None,
            },
            "quality": {
                "avg_ai_score": round(sum(scores) / len(scores), 2) if scores else None,
                "scored_call_count": len(scores),
            },
        }

    return {"runtimes": result}
