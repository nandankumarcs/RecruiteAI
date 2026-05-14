"""Async helpers for generating prompt audio assets in the background."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session_factory
from app.models.job_prompt_generation_run import JobPromptGenerationRun
from app.services.prompt_audio_service import get_prompt_audio_service

logger = logging.getLogger(__name__)

_scheduled_jobs: dict[uuid.UUID, asyncio.Task] = {}


async def generate_question_audio_for_job_task(job_id: uuid.UUID) -> None:
    prompt_audio = get_prompt_audio_service()
    run_id: uuid.UUID | None = None
    try:
        async with async_session_factory() as session:
            run = JobPromptGenerationRun(
                job_id=job_id,
                status="in_progress",
                started_at=datetime.now(timezone.utc),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id

        assets = await prompt_audio.ensure_question_audio_for_job(job_id)
        success_count = sum(1 for asset in assets if asset.status == "ready")
        failure_count = sum(1 for asset in assets if asset.status == "failed")

        async with async_session_factory() as session:
            run = await session.get(JobPromptGenerationRun, run_id)
            if run is not None:
                run.status = "completed"
                run.success_count = success_count
                run.failure_count = failure_count
                run.completed_at = datetime.now(timezone.utc)
                await session.commit()
    except Exception as exc:
        logger.exception("Question audio generation failed for job %s", job_id)
        if run_id is not None:
            async with async_session_factory() as session:
                run = await session.get(JobPromptGenerationRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.completed_at = datetime.now(timezone.utc)
                    run.error_summary = {"error": str(exc)}
                    await session.commit()
        raise
    finally:
        _scheduled_jobs.pop(job_id, None)


def schedule_generate_question_audio_for_job(
    job_id: uuid.UUID,
    *,
    delay_seconds: float = 1.0,
) -> asyncio.Task:
    existing = _scheduled_jobs.get(job_id)
    if existing and not existing.done():
        existing.cancel()

    async def runner() -> None:
        try:
            await asyncio.sleep(delay_seconds)
            await generate_question_audio_for_job_task(job_id)
        except asyncio.CancelledError:
            logger.debug("Cancelled pending audio generation for job %s", job_id)
            raise

    task = asyncio.create_task(runner(), name=f"generate-question-audio-{job_id}")
    _scheduled_jobs[job_id] = task
    return task


async def get_latest_generation_run(job_id: uuid.UUID) -> JobPromptGenerationRun | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(JobPromptGenerationRun)
            .where(JobPromptGenerationRun.job_id == job_id)
            .order_by(JobPromptGenerationRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
