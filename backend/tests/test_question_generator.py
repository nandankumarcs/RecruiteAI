"""Tests for deterministic question generation."""

from __future__ import annotations

import uuid

from app.agents.question_generator_agent import QuestionGeneratorAgent
from app.models.job import Job
from app.models.resume import Resume


def test_fallback_question_generation_produces_stable_schema():
    """Fallback generation should return a usable, structured question set."""
    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="AI Engineer",
        description="Build recruiter-facing AI workflows.",
        requirements="Python, FastAPI, LangChain, semantic search",
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
        parsed_data={
            "summary": "GenAI engineer with internship experience.",
            "skills": ["Python", "FastAPI", "LangChain"],
            "projects": [
                {
                    "name": "Resume Parser",
                    "technologies": ["Python", "FastAPI", "PostgreSQL"],
                }
            ],
        },
    )

    agent = QuestionGeneratorAgent(enable_llm=False)
    result = agent.fallback_generate(job, resume)

    assert result.schema_version == "questions.v1"
    assert len(result.questions) == 8
    assert result.questions[0].category == "introduction"
    assert result.questions[0].order_index == 1
    assert any(question.category == "technical" for question in result.questions)
    assert any(question.category == "project" for question in result.questions)
    assert all(1 <= question.difficulty <= 5 for question in result.questions)
