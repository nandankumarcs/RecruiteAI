"""
RecruiteAI Database Models

All SQLAlchemy models re-exported from this package for convenience.
Import models here so Alembic can discover them for migrations.
"""

from app.models.user import User
from app.models.job import Job
from app.models.resume import Resume
from app.models.question import InterviewQuestion
from app.models.call import Call
from app.models.call_message import CallMessage
from app.models.audio_prompt_asset import AudioPromptAsset
from app.models.job_prompt_generation_run import JobPromptGenerationRun

__all__ = [
    "User",
    "Job",
    "Resume",
    "InterviewQuestion",
    "Call",
    "CallMessage",
    "AudioPromptAsset",
    "JobPromptGenerationRun",
]
