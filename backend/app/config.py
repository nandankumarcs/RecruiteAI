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

    # --- Sarvam ---
    SARVAM_API_KEY: str = ""
    SARVAM_TTS_MODEL: str = "bulbul:v3"
    SARVAM_TTS_SPEAKER: str = "priya"
    SARVAM_TTS_LANGUAGE: str = "en-IN"
    SARVAM_TTS_SAMPLE_RATE: int = 8000
    SARVAM_TTS_CODEC: str = "linear16"
    SARVAM_TTS_PACE: float = 1.2
    SARVAM_TTS_TRANSPORT: str = "websocket"  # websocket, http
    SARVAM_TTS_USE_HTTP_STREAM: bool = True
    SARVAM_TTS_WEBSOCKET_URL: str = "wss://api.sarvam.ai/text-to-speech/ws"
    SARVAM_TTS_FIRST_BYTE_TIMEOUT_SECONDS: float = 2.0
    SARVAM_TTS_COMPLETION_TIMEOUT_SECONDS: float = 15.0
    SARVAM_ESTIMATED_COST_INR_PER_10K_CHARS: float = 30.0
    PIPELINE_TTS_JITTER_BUFFER_MS: int = 200
    PIPELINE_STT_ENDPOINTING_MS: int = 500
    PIPELINE_STT_UTTERANCE_END_MS: int = 1000

    # --- Twilio Telephony ---
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    TWILIO_ESTIMATED_COST_PER_MINUTE_USD: float = 0.013
    TWILIO_VALIDATE_SIGNATURES: bool = False

    # --- Exotel Telephony ---
    EXOTEL_ACCOUNT_SID: str = ""
    EXOTEL_API_KEY: str = ""
    EXOTEL_API_TOKEN: str = ""
    EXOTEL_PHONE_NUMBER: str = ""
    EXOTEL_SUBDOMAIN: str = "api.exotel.com"
    EXOTEL_FLOW_URL: str = "http://my.exotel.com/crownstack1/exoml/start_voice/1244328"
    EXOTEL_ESTIMATED_COST_PER_MINUTE_USD: float = 0.005
    EXOTEL_VALIDATE_SIGNATURES: bool = False

    # --- Runtime selection ---
    TELEPHONY_PROVIDER: str = "twilio"  # twilio, exotel, mock
    VOICE_RUNTIME: str = "openai_realtime"  # openai_realtime, deepgram_openai
    PIPELINE_REASONING_PROVIDER: str = "openai"
    TTS_PROVIDER: str = "deepgram"  # deepgram, sarvam


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

    # --- Resume Processing Session Management ---
    RESUME_SESSION_TTL_HOURS: int = 1  # Session cleanup after inactivity (in hours)
    RESUME_SESSION_CLEANUP_INTERVAL_MINUTES: int = 5  # How often to run cleanup task
    SSE_KEEPALIVE_INTERVAL_SECONDS: int = 15  # SSE keepalive interval
    RESUME_SESSION_TTL_SECONDS: int = 3600  # 1 hour - session cleanup after inactivity (deprecated, use RESUME_SESSION_TTL_HOURS)
    RESUME_KEEPALIVE_INTERVAL_SECONDS: int = 15  # SSE keepalive interval (deprecated, use SSE_KEEPALIVE_INTERVAL_SECONDS)
    RESUME_EVENT_QUEUE_SIZE: int = 1000  # Maximum events per session queue
    RESUME_MAX_PER_SESSION: int = 100  # Maximum resumes per upload session

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — call this instead of Settings() directly."""
    return Settings()
