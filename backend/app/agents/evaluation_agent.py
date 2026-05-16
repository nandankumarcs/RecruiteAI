"""
Evaluation Agent.

Uses an LLM to produce a structured post-call evaluation from the transcript and
job context, while handling low-signal transcripts honestly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.models.call import Call
from app.models.job import Job
from app.models.resume import Resume
from app.services.ai_models import build_structured_chat_model
from app.services.observability import summarize_text_model_usage

settings = get_settings()


class EvaluationStatus(StrEnum):
    COMPLETED = "completed_evaluation"
    INSUFFICIENT_DATA = "insufficient_data"
    CANDIDATE_DISENGAGED = "candidate_disengaged"
    CALL_QUALITY_ISSUE = "call_quality_issue"


class EvaluationConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvaluationRecommendation(StrEnum):
    ADVANCE = "advance"
    HOLD = "hold"
    REJECT = "reject"
    INSUFFICIENT_DATA = "insufficient_data"


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "evaluation.v2"
    status: EvaluationStatus = EvaluationStatus.COMPLETED
    confidence: EvaluationConfidence = EvaluationConfidence.MEDIUM
    overall_score: int | None = None
    technical_score: int | None = None
    communication_score: int | None = None
    experience_score: int | None = None
    remarks: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    behavioral_score: int | None = Field(
        default=None,
        description="Score for soft skills (clarity, confidence, hesitation) from 1 to 10 when evaluable.",
    )
    behavioral_summary: str | None = Field(
        default=None,
        description="Summary of behavioral observations when evaluable.",
    )
    recommendation: EvaluationRecommendation = EvaluationRecommendation.HOLD


@dataclass(slots=True)
class TranscriptTurn:
    role: str
    content: str


@dataclass(slots=True)
class TranscriptEvidence:
    assistant_turn_count: int
    user_turn_count: int
    candidate_word_count: int
    substantive_user_turn_count: int
    disengaged_user_turn_count: int
    trivial_user_turn_count: int
    transcript_health_flags: list[str]


ROLE_RE = re.compile(r"^\s*(assistant|candidate|user|ai)\s*:\s*(.*)$", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z0-9']+")
META_PATTERNS = (
    "next question",
    "next questions",
    "what is this again",
    "what do you want to know",
    "how many questions",
    "can you explain a bit more",
    "can you repeat",
    "repeat the question",
    "hello?",
)
DISENGAGED_PATTERNS = (
    "not interested",
    "bye",
    "goodbye",
    "disconnect",
    "end the call",
    "skip this",
)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def _classify_user_turn(text: str) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return "trivial"
    if any(pattern in normalized for pattern in DISENGAGED_PATTERNS):
        return "disengaged"
    if any(pattern in normalized for pattern in META_PATTERNS):
        return "meta"
    if _word_count(normalized) <= 3:
        return "trivial"
    return "substantive"


def _extract_turns(transcript: str | None) -> list[TranscriptTurn]:
    if not transcript:
        return []

    turns: list[TranscriptTurn] = []
    for line in transcript.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = ROLE_RE.match(stripped)
        if match:
            role = match.group(1).lower()
            content = match.group(2).strip()
        else:
            role = "unknown"
            content = stripped
        if content:
            turns.append(TranscriptTurn(role=role, content=content))
    return turns


def _analyze_transcript_evidence(transcript: str | None, *, call: "Call | None" = None) -> TranscriptEvidence:
    turns = _extract_turns(transcript)
    assistant_turns = [turn for turn in turns if turn.role == "assistant"]
    user_turns = [turn for turn in turns if turn.role in {"user", "candidate"}]
    transcript_health_flags: list[str] = []

    if transcript and "Assistant: Assistant:" in transcript:
        transcript_health_flags.append("duplicate_assistant_prefix")

    repeated_assistant_prompt = False
    previous_normalized_assistant: str | None = None
    for turn in assistant_turns:
        normalized = _normalize_text(turn.content.rstrip("?.!"))
        if normalized and previous_normalized_assistant == normalized:
            repeated_assistant_prompt = True
            break
        previous_normalized_assistant = normalized
    if repeated_assistant_prompt:
        transcript_health_flags.append("repeated_assistant_prompt")

    classifications = [_classify_user_turn(turn.content) for turn in user_turns]
    substantive_user_turn_count = sum(1 for item in classifications if item == "substantive")
    disengaged_user_turn_count = sum(1 for item in classifications if item == "disengaged")
    trivial_user_turn_count = sum(1 for item in classifications if item in {"trivial", "meta"})

    fragment_like_turns = sum(
        1
        for turn, cls in zip(user_turns, classifications, strict=False)
        if cls == "substantive" and _word_count(turn.content) <= 5 and not turn.content.strip().endswith((".", "!", "?"))
    )
    if user_turns and fragment_like_turns >= max(2, len(user_turns) // 2):
        transcript_health_flags.append("high_fragment_ratio")

    # Fix 4b: surface AI interruption count from latency_metrics
    ai_interruption_count: int = 0
    if call is not None:
        ai_interruption_count = int(
            (call.latency_metrics or {}).get("ai_interruption_count", 0)
        )
    if ai_interruption_count >= 3:
        transcript_health_flags.append(f"ai_interrupted_candidate_{ai_interruption_count}x")

    candidate_word_count = sum(_word_count(turn.content) for turn in user_turns)
    return TranscriptEvidence(
        assistant_turn_count=len(assistant_turns),
        user_turn_count=len(user_turns),
        candidate_word_count=candidate_word_count,
        substantive_user_turn_count=substantive_user_turn_count,
        disengaged_user_turn_count=disengaged_user_turn_count,
        trivial_user_turn_count=trivial_user_turn_count,
        transcript_health_flags=transcript_health_flags,
    )


def _build_insufficient_data_result(
    *,
    status: EvaluationStatus,
    remarks: str,
    weaknesses: list[str],
    strengths: list[str] | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        status=status,
        confidence=EvaluationConfidence.LOW,
        overall_score=None,
        technical_score=None,
        communication_score=None,
        experience_score=None,
        behavioral_score=None,
        behavioral_summary="Not enough reliable candidate evidence to score this call.",
        remarks=remarks,
        strengths=strengths or [],
        weaknesses=weaknesses,
        recommendation=EvaluationRecommendation.INSUFFICIENT_DATA,
    )


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

    def _preflight_result(self, *, call: Call) -> tuple[TranscriptEvidence, EvaluationResult | None]:
        evidence = _analyze_transcript_evidence(call.transcript, call=call)

        if evidence.user_turn_count == 0:
            return evidence, _build_insufficient_data_result(
                status=EvaluationStatus.INSUFFICIENT_DATA,
                remarks="The call contains only assistant speech, so there is no candidate evidence to evaluate.",
                weaknesses=["No candidate response was captured in the transcript."],
            )

        if evidence.disengaged_user_turn_count > 0 and evidence.substantive_user_turn_count == 0:
            return evidence, _build_insufficient_data_result(
                status=EvaluationStatus.CANDIDATE_DISENGAGED,
                remarks="The candidate did not meaningfully engage with the screening, so a grounded interview evaluation is not available.",
                strengths=["The candidate acknowledged the call."],
                weaknesses=["The candidate declined to engage with the screening questions."],
            )

        if evidence.candidate_word_count < 12 or evidence.substantive_user_turn_count == 0:
            return evidence, _build_insufficient_data_result(
                status=EvaluationStatus.INSUFFICIENT_DATA,
                remarks="The transcript is too short or low-signal to support a reliable interview evaluation.",
                weaknesses=["There is not enough candidate content to score technical or experience fit."],
            )

        if evidence.transcript_health_flags and evidence.substantive_user_turn_count <= 1:
            return evidence, _build_insufficient_data_result(
                status=EvaluationStatus.CALL_QUALITY_ISSUE,
                remarks="The transcript appears fragmented or unstable, so the candidate cannot be scored reliably from this call alone.",
                weaknesses=["Transcript quality issues reduce confidence in the captured answers."],
            )

        return evidence, None

    def _build_prompt(self, *, call: Call, job: Job, resume: Resume, evidence: TranscriptEvidence) -> str:
        transcript_health = ", ".join(evidence.transcript_health_flags) if evidence.transcript_health_flags else "none detected"
        ai_interruption_count = int((call.latency_metrics or {}).get("ai_interruption_count", 0))
        interruption_note = (
            f"IMPORTANT: The AI system interrupted the candidate {ai_interruption_count} times during this call "
            "(fired a response before the candidate finished speaking). Many of the candidate's short or "
            "incomplete answers are a direct consequence of being cut off, not a reflection of their knowledge "
            "or communication ability. Do NOT penalise communication_score or technical_score for incomplete "
            "answers that coincide with these interruptions. If ai_interruption_count >= 3, set "
            "status=call_quality_issue and reduce confidence to 'low'; evaluate only the substantive "
            "turns where the candidate was allowed to finish.\n"
        ) if ai_interruption_count >= 3 else ""

        return (
            "Evaluate this interview transcript for a recruiter.\n"
            "Return structured output with status, confidence, overall_score, technical_score, "
            "communication_score, experience_score, behavioral_score, behavioral_summary, remarks, strengths, weaknesses, and recommendation.\n"
            "Allowed status values: completed_evaluation, insufficient_data, candidate_disengaged, call_quality_issue.\n"
            "Allowed recommendation values: advance, hold, reject, insufficient_data.\n"
            "If there is not enough evidence to judge the candidate fairly, set a non-scorable status and recommendation=insufficient_data.\n"
            "Never infer experience, technical depth, or confidence from the job description alone.\n"
            "Only score technical ability if the candidate actually answered technical questions.\n"
            "If the transcript is fragmented, interrupted, or clearly low quality, lower confidence or use call_quality_issue.\n"
            "For completed_evaluation, scores must be 1-10. For non-scorable outcomes, leave scores null.\n"
            f"{interruption_note}\n"
            f"Job title: {job.title}\n"
            f"Job description: {job.description}\n"
            f"Job requirements: {job.requirements or ''}\n"
            f"Candidate name: {resume.candidate_name or ''}\n"
            f"Evidence summary: user_turns={evidence.user_turn_count}, substantive_user_turns={evidence.substantive_user_turn_count}, "
            f"candidate_word_count={evidence.candidate_word_count}, ai_interruption_count={ai_interruption_count}, "
            f"transcript_health={transcript_health}\n"
            f"Transcript:\n{(call.transcript or '')[:16000]}"
        )

    def fallback_evaluate(self, *, call: Call, job: Job, resume: Resume) -> EvaluationResult:
        evidence, preflight = self._preflight_result(call=call)
        if preflight is not None:
            return preflight

        requirement_tokens = {
            token.lower()
            for token in WORD_RE.findall(job.requirements or "")
            if len(token) > 2
        }
        transcript_lower = (call.transcript or "").lower()
        matched_requirements = sum(1 for token in requirement_tokens if token in transcript_lower)

        communication = min(8, max(3, 4 + evidence.substantive_user_turn_count - evidence.trivial_user_turn_count // 2))
        technical = min(8, max(2, 3 + matched_requirements))
        experience = min(8, max(2, 3 + min(evidence.substantive_user_turn_count, 3)))
        behavioral = min(8, max(3, communication - (1 if evidence.transcript_health_flags else 0)))
        overall = round((technical + communication + experience + behavioral) / 4)

        weaknesses = []
        if evidence.transcript_health_flags:
            weaknesses.append("Transcript quality issues reduced confidence in parts of the conversation.")
        if evidence.trivial_user_turn_count > evidence.substantive_user_turn_count:
            weaknesses.append("Several responses were brief or lacked detail.")
        if technical <= 4:
            weaknesses.append("Technical depth was not demonstrated consistently in the transcript.")

        strengths = []
        if matched_requirements:
            strengths.append("The candidate referenced some job-relevant technologies.")
        if evidence.substantive_user_turn_count >= 3:
            strengths.append("The candidate provided multiple substantive responses.")

        recommendation = (
            EvaluationRecommendation.ADVANCE
            if overall >= 8
            else EvaluationRecommendation.HOLD
            if overall >= 5
            else EvaluationRecommendation.REJECT
        )
        confidence = (
            EvaluationConfidence.MEDIUM
            if evidence.transcript_health_flags
            else EvaluationConfidence.HIGH
        )
        behavioral_summary = (
            "Reasonably clear and engaged responses."
            if behavioral >= 6
            else "Some hesitation or limited detail was visible in the responses."
        )

        return EvaluationResult(
            status=EvaluationStatus.COMPLETED,
            confidence=confidence,
            overall_score=overall,
            technical_score=technical,
            communication_score=communication,
            experience_score=experience,
            behavioral_score=behavioral,
            behavioral_summary=behavioral_summary,
            remarks="This evaluation is based only on the evidence present in the transcript.",
            strengths=strengths or ["The candidate provided enough information to complete a basic evaluation."],
            weaknesses=weaknesses or ["The transcript leaves some uncertainty about depth and consistency."],
            recommendation=recommendation,
        )

    async def evaluate_call(self, *, call: Call, job: Job, resume: Resume) -> EvaluationResult:
        evidence, preflight = self._preflight_result(call=call)
        if preflight is not None:
            return preflight

        if self._structured_llm is None:
            return self.fallback_evaluate(call=call, job=job, resume=resume)

        prompt = self._build_prompt(call=call, job=job, resume=resume, evidence=evidence)
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
