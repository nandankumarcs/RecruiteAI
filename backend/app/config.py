"""
RecruiteAI Backend Configuration

Loads environment variables using Pydantic Settings.
All config values are centralized here — never read os.environ directly.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/recruiteai"

    # --- Auth / JWT ---
    SECRET_KEY: str = "recruiteai-super-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Seed User ---
    SEED_USER_EMAIL: str = "dinesh.tomar@yopmail.com"
    SEED_USER_PASSWORD: str = "Password@123"
    SEED_USER_NAME: str = "Dinesh Tomar"

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEXT_MODEL: str = "gpt-4o-mini"
    OPENAI_REALTIME_MODEL: str = "gpt-4o-mini-realtime-preview"
    OPENAI_REALTIME_VOICE: str = "coral"
    OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1"
    OPENAI_TEXT_INPUT_COST_PER_1M: float = 0.15
    OPENAI_TEXT_OUTPUT_COST_PER_1M: float = 0.6
    OPENAI_REALTIME_TEXT_INPUT_COST_PER_1M: float = 0.6
    OPENAI_REALTIME_TEXT_OUTPUT_COST_PER_1M: float = 2.4
    OPENAI_REALTIME_AUDIO_INPUT_COST_PER_1M: float = 10.0
    OPENAI_REALTIME_AUDIO_OUTPUT_COST_PER_1M: float = 20.0
    OPENAI_REALTIME_RUNTIME_LABEL: str = "openai_realtime"

    # --- Deepgram ---
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_STT_MODEL: str = "nova-2-phonecall"
    DEEPGRAM_TTS_MODEL: str = "aura-asteria-en"
    DEEPGRAM_STT_COST_PER_MINUTE_USD: float = 0.0043
    DEEPGRAM_TTS_COST_PER_1K_CHARS_USD: float = 0.03

    # --- Twilio ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_MOCK_MODE: bool = True
    TWILIO_ESTIMATED_COST_PER_MINUTE_USD: float = 0.013
    # Set to True in production to reject requests without a valid X-Twilio-Signature
    TWILIO_VALIDATE_SIGNATURES: bool = False


    # --- Runtime selection ---
    TELEPHONY_PROVIDER: str = "twilio"  # twilio, mock
    VOICE_RUNTIME: str = "openai_realtime"  # openai_realtime, deepgram_openai
    PIPELINE_REASONING_PROVIDER: str = "openai"


    # --- LangSmith ---
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "RecruiteAI"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_TRACING: bool = False

    # --- Storage ---
    STORAGE_PROVIDER: str = "local"  # "local" or "s3"
    STORAGE_LOCAL_PATH: str = "./uploads"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_S3_REGION: str = ""

    # --- App ---
    BACKEND_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    PUBLIC_URL: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call this instead of Settings() directly."""
    return Settings()
