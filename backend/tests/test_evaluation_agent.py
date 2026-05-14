"""Tests for post-call evaluation behavior."""

from __future__ import annotations

import uuid

from app.agents.evaluation_agent import (
    EvaluationAgent,
    EvaluationRecommendation,
    EvaluationStatus,
)
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume


def _build_job_and_resume() -> tuple[Job, Resume]:
    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="AI Engineer",
        description="Build AI interview systems.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    resume = Resume(
        id=uuid.uuid4(),
        job_id=job.id,
        candidate_name="Jane Candidate",
        phone_number="+1 222 333 4444",
        email="jane@example.com",
        file_path="/tmp/jane.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"skills": ["Python", "FastAPI", "LLMs"]},
    )
    return job, resume


def test_opener_only_call_returns_insufficient_data():
    job, resume = _build_job_and_resume()
    call = Call(
        id=uuid.uuid4(),
        job_id=job.id,
        resume_id=resume.id,
        phone_number=resume.phone_number,
        status="completed",
        transcript="Assistant: Hello! I'm calling about your application. Can we continue with the screening?",
    )

    agent = EvaluationAgent(enable_llm=False)
    result = agent.fallback_evaluate(call=call, job=job, resume=resume)

    assert result.schema_version == "evaluation.v2"
    assert result.status == EvaluationStatus.INSUFFICIENT_DATA
    assert result.recommendation == EvaluationRecommendation.INSUFFICIENT_DATA
    assert result.overall_score is None
    assert result.behavioral_score is None


def test_candidate_disengaged_call_returns_non_scorable_outcome():
    job, resume = _build_job_and_resume()
    call = Call(
        id=uuid.uuid4(),
        job_id=job.id,
        resume_id=resume.id,
        phone_number=resume.phone_number,
        status="completed",
        transcript=(
            "Assistant: Is now a good time for a short screening?\n"
            "User: Sure.\n"
            "Assistant: Tell me about yourself.\n"
            "User: Next question.\n"
            "Assistant: Tell me about your Python experience.\n"
            "User: I'm not interested.\n"
            "Assistant: Thank you. Goodbye."
        ),
    )

    agent = EvaluationAgent(enable_llm=False)
    result = agent.fallback_evaluate(call=call, job=job, resume=resume)

    assert result.status == EvaluationStatus.CANDIDATE_DISENGAGED
    assert result.recommendation == EvaluationRecommendation.INSUFFICIENT_DATA
    assert result.overall_score is None


def test_fallback_evaluation_produces_stable_schema_for_real_transcript():
    job, resume = _build_job_and_resume()
    call = Call(
        id=uuid.uuid4(),
        job_id=job.id,
        resume_id=resume.id,
        phone_number=resume.phone_number,
        status="completed",
        transcript=(
            "Assistant: Tell me about your experience.\n"
            "User: I used Python and FastAPI to build an LLM workflow project.\n"
            "Assistant: What tradeoffs did you face?\n"
            "User: I had to choose between retrieval quality and latency because our users needed fast responses.\n"
        ),
    )

    agent = EvaluationAgent(enable_llm=False)
    result = agent.fallback_evaluate(call=call, job=job, resume=resume)

    assert result.schema_version == "evaluation.v2"
    assert result.status == EvaluationStatus.COMPLETED
    assert result.overall_score is not None and 1 <= result.overall_score <= 10
    assert result.technical_score is not None and 1 <= result.technical_score <= 10
    assert result.strengths
    assert result.weaknesses
    assert result.recommendation in {
        EvaluationRecommendation.ADVANCE,
        EvaluationRecommendation.HOLD,
        EvaluationRecommendation.REJECT,
    }
