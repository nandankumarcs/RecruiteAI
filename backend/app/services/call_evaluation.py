"""Helpers for post-call automatic evaluation."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.agents.evaluation_agent import EvaluationAgent
from app.database import async_session_factory
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume


async def auto_evaluate_call_if_ready(
    call_id: uuid.UUID,
    *,
    evaluation_agent: EvaluationAgent | None = None,
) -> bool:
    """Evaluate a completed call if it has a transcript and no saved evaluation yet."""
    agent = evaluation_agent or EvaluationAgent()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Call, Job, Resume)
            .join(Job, Call.job_id == Job.id)
            .join(Resume, Call.resume_id == Resume.id)
            .where(Call.id == call_id)
        )
        row = result.one_or_none()
        if not row:
            return False

        call, job, resume = row
        if call.ai_evaluation is not None:
            return False
        if call.status != "completed":
            return False
        if not call.transcript or not call.transcript.strip():
            return False

        evaluation = await agent.evaluate_call(call=call, job=job, resume=resume)
        call.ai_evaluation = evaluation.model_dump()
        await session.commit()
        return True


def call_is_finished(status: str | None) -> bool:
    """Return whether a call status represents a terminal state."""
    return status in {"completed", "failed", "no_answer"}
