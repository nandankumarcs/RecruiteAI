"""
Evaluation Agent.

Uses an LLM to produce a structured post-call evaluation from the transcript and job context.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume
from app.services.ai_models import build_structured_chat_model
from app.services.observability import summarize_text_model_usage

settings = get_settings()


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "evaluation.v1"
    overall_score: int
    technical_score: int
    communication_score: int
    experience_score: int
    remarks: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    behavioral_score: int = Field(description="Score for soft skills (clarity, confidence, hesitation) from 1 to 10.")
    behavioral_summary: str = Field(description="Summary of behavioral observations (e.g. 'Highly confident', 'Frequently hesitated').")
    recommendation: str = "hold"


class EvaluationAgent:
    """Evaluate a completed or transcript-bearing interview call."""

    def __init__(self, enable_llm: bool | None = None):
        self.enable_llm = (
            bool(settings.OPENAI_API_KEY)
            if enable_llm is None
            else enable_llm
        )
        self._structured_llm = None

        if self.enable_llm:
            self._structured_llm = build_structured_chat_model(
                schema=EvaluationResult,
                run_name="evaluation_agent",
                metadata={"component": "evaluation_agent"},
            )

    async def evaluate_call(self, *, call: Call, job: Job, resume: Resume) -> EvaluationResult:
        if self._structured_llm is None:
            raise ValueError("AI Evaluation model is not configured. Please check your OPENAI_API_KEY.")

        prompt = (
            "Evaluate this interview transcript for a recruiter. "
            "Return structured output with overall_score, technical_score, communication_score, "
            "experience_score, behavioral_score, behavioral_summary, remarks, strengths, weaknesses, and recommendation. "
            "Scores must be 1-10. Keep the assessment grounded in the transcript. "
            "For behavioral evaluation, look for signs of hesitation, pauses, clarity of thought, and confidence.\n\n"
            f"Job title: {job.title}\n"
            f"Job description: {job.description}\n"
            f"Job requirements: {job.requirements or ''}\n"
            f"Candidate name: {resume.candidate_name or ''}\n"
            f"Transcript:\n{(call.transcript or '')[:16000]}"
        )

        structured = await self._structured_llm.ainvoke(prompt)
        parsed = structured.get("parsed") if isinstance(structured, dict) else None
        raw = structured.get("raw") if isinstance(structured, dict) else None
        
        if raw is not None:
            summarize_text_model_usage(
                agent_name="evaluation_agent",
                model=settings.OPENAI_TEXT_MODEL or settings.OPENAI_MODEL,
                usage=getattr(raw, "usage_metadata", None),
                metadata={"job_title": job.title, "call_id": str(call.id)},
            )
            
        if parsed is None:
            raise ValueError("AI model failed to produce a structured evaluation for this transcript.")
            
        return EvaluationResult(**parsed.model_dump())


def get_evaluation_agent() -> EvaluationAgent:
    """Dependency factory for evaluation agent."""
    return EvaluationAgent()
