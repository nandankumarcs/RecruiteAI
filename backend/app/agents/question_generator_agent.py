"""
Question Generator Agent.

Generates a structured set of interview questions from a job posting and
parsed resume data. Uses structured LLM output when available and falls back
to deterministic question generation for local/test environments.
"""

from __future__ import annotations

from collections import OrderedDict

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.models.job import Job
from app.models.resume import Resume
from app.services.ai_models import build_structured_chat_model
from app.services.observability import summarize_text_model_usage

settings = get_settings()


QUESTION_COUNT = 8


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    question_text: str
    category: str
    difficulty: int = 1
    order_index: int = 0


class QuestionGenerationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str = "questions.v1"
    questions: list[GeneratedQuestion] = Field(default_factory=list)


class QuestionGeneratorAgent:
    """Generate interview questions for a job, optionally tailored to a resume."""

    def __init__(self, enable_llm: bool | None = None):
        self.enable_llm = (
            bool(settings.OPENAI_API_KEY)
            if enable_llm is None
            else enable_llm
        )
        self._structured_llm = None

        if self.enable_llm:
            self._structured_llm = build_structured_chat_model(
                schema=QuestionGenerationResult,
                run_name="question_generator",
                metadata={"component": "question_generator"},
            )

    def _canonicalize_question(
        self, item: GeneratedQuestion | dict, order_index: int
    ) -> GeneratedQuestion:
        question = item if isinstance(item, GeneratedQuestion) else GeneratedQuestion(**item)
        difficulty = min(max(int(question.difficulty or 1), 1), 5)
        category = (question.category or "general").strip().lower()

        return question.model_copy(
            update={
                "question_text": question.question_text.strip(),
                "category": category,
                "difficulty": difficulty,
                "order_index": order_index,
            }
        )

    def normalize_result(self, result: QuestionGenerationResult) -> QuestionGenerationResult:
        questions = [
            self._canonicalize_question(item, index)
            for index, item in enumerate(result.questions, start=1)
            if (item.question_text if isinstance(item, GeneratedQuestion) else item.get("question_text", "")).strip()
        ]
        return QuestionGenerationResult(schema_version="questions.v1", questions=questions[:12])

    def _resume_skills(self, resume: Resume) -> list[str]:
        parsed_data = resume.parsed_data or {}
        skills = parsed_data.get("skills") or []
        seen: OrderedDict[str, None] = OrderedDict()
        for skill in skills:
            cleaned = str(skill).strip()
            if cleaned:
                seen[cleaned] = None
        return list(seen.keys())

    def _resume_projects(self, resume: Resume) -> list[dict]:
        parsed_data = resume.parsed_data or {}
        projects = parsed_data.get("projects") or []
        return [project for project in projects if isinstance(project, dict)]

    def fallback_generate(self, job: Job, resume: Resume | None = None) -> QuestionGenerationResult:
        """Deterministic question generation for tests and local usage."""
        if resume:
            skills = self._resume_skills(resume)
            projects = self._resume_projects(resume)
            summary = (resume.parsed_data or {}).get("summary") or "their background"
            top_skill = skills[0] if skills else "your core technical strengths"
            second_skill = skills[1] if len(skills) > 1 else top_skill
            project_name = projects[0]["name"] if projects else "a recent project"
            project_stack = ", ".join(projects[0].get("technologies", [])[:3]) if projects else ""
        else:
            skills = []
            projects = []
            summary = "the candidate's background"
            top_skill = "core technical skills"
            second_skill = "relevant domain expertise"
            project_name = "prior professional experience"
            project_stack = ""

        requirements = job.requirements or job.description

        questions = [
            GeneratedQuestion(
                question_text=f"Can you give me a concise overview of your background and why you're interested in the {job.title} role?",
                category="introduction",
                difficulty=1,
            ),
            GeneratedQuestion(
                question_text=f"How does your previous experience prepare you for the specific challenges of a {job.title} at our company?",
                category="experience",
                difficulty=2,
            ),
            GeneratedQuestion(
                question_text=f"This role requires {requirements}. Can you walk me through a specific instance where you applied {top_skill} effectively?",
                category="technical",
                difficulty=3,
            ),
            GeneratedQuestion(
                question_text=f"What is the most complex technical trade-off you've had to make when working with {second_skill}?",
                category="technical",
                difficulty=4,
            ),
            GeneratedQuestion(
                question_text=f"Tell me about a time when you had to take ownership of a critical project. What was the outcome?",
                category="behavioral",
                difficulty=3,
            ),
            GeneratedQuestion(
                question_text=f"If you were to encounter a major technical roadblock in your first month as our {job.title}, how would you approach solving it?",
                category="situational",
                difficulty=3,
            ),
            GeneratedQuestion(
                question_text=f"What are your long-term career goals, and how does this role specifically align with them?",
                category="closing",
                difficulty=2,
            ),
        ]

        return self.normalize_result(QuestionGenerationResult(questions=questions))

    async def generate_questions(self, job: Job, resume: Resume | None = None) -> QuestionGenerationResult:
        fallback = self.fallback_generate(job, resume)
        if self._structured_llm is None:
            return fallback

        if resume:
            parsed_data = resume.parsed_data or {}
            candidate_context = (
                f"Candidate name: {resume.candidate_name or ''}\n"
                f"Candidate summary: {parsed_data.get('summary', '')}\n"
                f"Candidate skills: {', '.join(parsed_data.get('skills', []))}\n"
                f"Candidate experience: {parsed_data.get('experience', [])}\n"
                f"Candidate projects: {parsed_data.get('projects', [])}\n"
            )
        else:
            candidate_context = "No specific candidate provided. Generate generic but high-quality questions for this role."

        prompt = (
            "Generate 8 to 12 tailored interview questions for a recruiter-led phone screening. "
            "Use categories such as introduction, experience, technical, project, behavioral, situational, and closing. "
            "Return structured JSON with question_text, category, difficulty (1-5), and order_index. "
            "Questions should be concise and cover a good spread of categories.\n\n"
            f"Job title: {job.title}\n"
            f"Job description: {job.description}\n"
            f"Job requirements: {job.requirements or ''}\n"
            f"{candidate_context}\n"
        )

        try:
            result = await self._structured_llm.ainvoke(prompt)
            parsed = result.get("parsed") if isinstance(result, dict) else None
            raw = result.get("raw") if isinstance(result, dict) else None
            if raw is not None:
                summarize_text_model_usage(
                    agent_name="question_generator",
                    model=settings.OPENAI_TEXT_MODEL or settings.OPENAI_MODEL,
                    usage=getattr(raw, "usage_metadata", None),
                    metadata={"job_title": job.title, "resume_id": str(resume.id) if resume else None},
                )
            if parsed is None:
                return fallback
            normalized = self.normalize_result(parsed)
            if len(normalized.questions) < QUESTION_COUNT:
                return fallback
            return normalized
        except Exception:
            return fallback


def get_question_generator_agent() -> QuestionGeneratorAgent:
    """Dependency factory for the question generator agent."""
    return QuestionGeneratorAgent()
