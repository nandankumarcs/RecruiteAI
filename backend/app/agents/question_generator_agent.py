"""
Question Generator Agent.

Generates a structured set of interview questions from a job posting.
Uses structured LLM output.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.models.job import Job
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
    """Generate interview questions for a job based on job description and requirements."""

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



    async def generate_questions(self, job: Job) -> QuestionGenerationResult:
        """Generate interview questions using AI based on job description. Raises exception if generation fails."""
        if self._structured_llm is None:
            raise ValueError("AI question generation is not available. OpenAI API key is not configured.")

        prompt = (
            "Generate 8 to 12 tailored interview questions for a recruiter-led phone screening. "
            "Use categories such as introduction, experience, technical, project, behavioral, situational, and closing. "
            "Return structured JSON with question_text, category, difficulty (1-5), and order_index. "
            "Questions should be concise and cover a good spread of categories.\n\n"
            f"Job title: {job.title}\n"
            f"Job description: {job.description}\n"
            f"Job requirements: {job.requirements or ''}\n"
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
                    metadata={"job_title": job.title},
                )
            
            if parsed is None:
                raise ValueError("AI returned invalid response format")
            
            normalized = self.normalize_result(parsed)
            
            if len(normalized.questions) < QUESTION_COUNT:
                raise ValueError(f"AI generated only {len(normalized.questions)} questions, expected at least {QUESTION_COUNT}")
            
            return normalized
            
        except Exception as e:
            # Re-raise with more context
            raise ValueError(f"Failed to generate questions: {str(e)}") from e


def get_question_generator_agent() -> QuestionGeneratorAgent:
    """Dependency factory for the question generator agent."""
    return QuestionGeneratorAgent()
