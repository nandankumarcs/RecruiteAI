"""Tests for deterministic call evaluation."""

from __future__ import annotations

import uuid

from app.agents.evaluation_agent import EvaluationAgent
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume


def test_fallback_evaluation_produces_stable_schema():
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
    call = Call(
        id=uuid.uuid4(),
        job_id=job.id,
        resume_id=resume.id,
        phone_number=resume.phone_number,
        status="completed",
        transcript=(
            "AI: Tell me about your experience.\n"
            "Candidate: I used Python and FastAPI to build an LLM workflow project.\n"
            "AI: What tradeoffs did you face?\n"
            "Candidate: I had to choose between retrieval quality and latency because our users needed fast responses.\n"
        ),
    )

    agent = EvaluationAgent(enable_llm=False)
    result = agent.fallback_evaluate(call=call, job=job, resume=resume)

    assert result.schema_version == "evaluation.v1"
    assert 1 <= result.overall_score <= 10
    assert 1 <= result.technical_score <= 10
    assert result.strengths
    assert result.weaknesses
    assert result.recommendation in {"advance", "hold", "reject"}
