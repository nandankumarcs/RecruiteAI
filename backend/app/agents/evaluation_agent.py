"""
Evaluation Agent.

Produces a structured post-call evaluation from the transcript and job context.
Uses an LLM when available and deterministic heuristics in local/test mode.
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

    def fallback_evaluate(self, *, call: Call, job: Job, resume: Resume) -> EvaluationResult:
        transcript = call.transcript or ""
        lower = transcript.lower()
        skills = ((resume.parsed_data or {}).get("skills") or [])[:5]
        skill_hits = sum(1 for skill in skills if skill.lower() in lower)
        utterance_count = len([line for line in transcript.splitlines() if line.strip()])
        word_count = len(re.findall(r"\b\w+\b", transcript))

        technical_score = min(10, max(4, 5 + skill_hits))
        communication_score = min(10, max(4, 4 + min(4, utterance_count // 2) + (1 if word_count > 120 else 0)))
        experience_score = min(10, max(4, 5 + (1 if "project" in lower else 0) + (1 if "intern" in lower or "experience" in lower else 0)))
        overall_score = round((technical_score + communication_score + experience_score) / 3)

        strengths: list[str] = []
        weaknesses: list[str] = []

        if skill_hits >= 2:
            strengths.append("Connected prior technical experience to the role requirements.")
        if utterance_count >= 4:
            strengths.append("Provided reasonably detailed answers during the conversation.")
        if "why" in lower or "because" in lower:
            strengths.append("Showed some explanation behind decisions and examples.")

        if word_count < 80:
            weaknesses.append("Limited transcript depth makes the assessment less certain.")
        if skill_hits == 0 and skills:
            weaknesses.append("Did not clearly reference the strongest skills visible on the resume.")
        if "um" in lower or "not sure" in lower:
            weaknesses.append("Some answers appeared hesitant or underdeveloped.")

        if not strengths:
            strengths.append("Maintained baseline relevance to the interview context.")
        if not weaknesses:
            weaknesses.append("More specific examples would improve confidence in the evaluation.")

        recommendation = "advance" if overall_score >= 8 else "hold" if overall_score >= 6 else "reject"
        remarks = (
            f"Candidate shows {['limited', 'developing', 'solid', 'strong'][min(max((overall_score - 4) // 2, 0), 3)]} "
            f"alignment for the {job.title} role based on the available transcript."
        )

        return EvaluationResult(
            overall_score=overall_score,
            technical_score=technical_score,
            communication_score=communication_score,
            experience_score=experience_score,
            remarks=remarks,
            strengths=strengths[:3],
            weaknesses=weaknesses[:3],
            recommendation=recommendation,
        )

    async def evaluate_call(self, *, call: Call, job: Job, resume: Resume) -> EvaluationResult:
        fallback = self.fallback_evaluate(call=call, job=job, resume=resume)
        if self._structured_llm is None:
            return fallback

        prompt = (
            "Evaluate this interview transcript for a recruiter. "
            "Return structured output with overall_score, technical_score, communication_score, "
            "experience_score, remarks, strengths, weaknesses, and recommendation. "
            "Scores must be 1-10. Keep the assessment grounded in the transcript.\n\n"
            f"Job title: {job.title}\n"
            f"Job description: {job.description}\n"
            f"Job requirements: {job.requirements or ''}\n"
            f"Candidate name: {resume.candidate_name or ''}\n"
            f"Transcript:\n{(call.transcript or '')[:16000]}"
        )

        try:
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
                return fallback
            return EvaluationResult(**parsed.model_dump(), schema_version="evaluation.v1")
        except Exception:
            return fallback


def get_evaluation_agent() -> EvaluationAgent:
    """Dependency factory for evaluation agent."""
    return EvaluationAgent()
