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
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- Seed User ---
    SEED_USER_EMAIL: str = "nandan.kumar@crownstack.com"
    SEED_USER_PASSWORD: str = "Password@123"
    SEED_USER_NAME: str = "Nandan Kumar"

    # --- Agent provider ---
    # "openai" uses OPENAI_TEXT_MODEL; "groq" uses GROQ_AGENT_MODEL via Groq's OpenAI-compatible API.
    AGENT_PROVIDER: str = "openai"
    GROQ_API_KEY: str = ""
    GROQ_AGENT_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # --- OpenAI ---
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEXT_MODEL: str = "gpt-4o-mini"
    OPENAI_REALTIME_MODEL: str = "gpt-4o-mini-realtime-preview"
    OPENAI_REALTIME_VOICE: str = "coral"
    OPENAI_TRANSCRIPTION_MODEL: str = "whisper-1"
    OPENAI_TRANSCRIPTION_LANGUAGE: str = "en"
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "coral"
    OPENAI_TTS_SPEED: float = 1.0
    OPENAI_TEXT_INPUT_COST_PER_1M: float = 0.15
    OPENAI_TEXT_OUTPUT_COST_PER_1M: float = 0.6
    OPENAI_REALTIME_TEXT_INPUT_COST_PER_1M: float = 0.6
    OPENAI_REALTIME_TEXT_OUTPUT_COST_PER_1M: float = 2.4
    OPENAI_REALTIME_AUDIO_INPUT_COST_PER_1M: float = 10.0
    OPENAI_REALTIME_AUDIO_OUTPUT_COST_PER_1M: float = 20.0
    OPENAI_REALTIME_RUNTIME_LABEL: str = "openai_realtime"

    # --- Deepgram ---
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_STT_MODEL: str = "nova-3"
    # Browser-sim audio is wideband (16 kHz+), not 8 kHz telephone narrowband.
    # nova-2-phonecall (the typical production model) returns garbage transcripts
    # with confidence=0 on wideband input — indistinguishable from echo, which
    # breaks the silence-nudge feature in the simulator. Use a wideband-tuned
    # model only when provider=browser. Production phone calls (exotel/twilio)
    # continue to use DEEPGRAM_STT_MODEL.
    DEEPGRAM_STT_MODEL_BROWSER: str = "nova-3"
    DEEPGRAM_STT_LANGUAGE: str = "en-IN"   # Indian English accent model
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
    PIPELINE_FILLERS_ENABLED: bool = False   # set True to re-enable filler phrases
    PIPELINE_TTS_JITTER_BUFFER_MS: int = 200
    PIPELINE_STT_ENDPOINTING_MS: int = 1500   # default conservative; override in .env (e.g. 500 for speculative mode)
    PIPELINE_STT_UTTERANCE_END_MS: int = 2500  # 1000→2500: gives candidate time to finish
    PIPELINE_USER_FRAGMENT_GRACE_MS: int = 2000 # 1500→2000: covers slower speakers
    PIPELINE_MIN_TURN_SECONDS: float = 1.5     # 1.0→1.5: require 1.5s of speech before LLM
    # Speculative LLM execution: fire LLM at endpointing silence, commit after this extra window.
    # Net silence before AI responds = PIPELINE_STT_ENDPOINTING_MS + PIPELINE_SPECULATIVE_CONFIRMATION_MS.
    # Set to 0 to disable speculative mode (commit immediately at endpointing).
    PIPELINE_SPECULATIVE_CONFIRMATION_MS: int = 1000
    # Silence-nudge escalation: when the candidate is silent after the AI
    # finishes speaking, fire a gentle nudge at NUDGE_MS, a stronger nudge at
    # ESCALATE_MS, and end the call at ENDCALL_MS. Set NUDGE_MS to 0 to
    # disable the feature entirely. Timer resets the moment the candidate
    # starts speaking (Deepgram SttSpeechStarted or any interim/final/endpoint).
    PIPELINE_SILENCE_NUDGE_MS: int = 5000
    PIPELINE_SILENCE_NUDGE_ESCALATE_MS: int = 12000
    PIPELINE_SILENCE_ENDCALL_MS: int = 20000
    # Word-count based progression: after candidate speaks >= this many words
    # since the current question was asked, force-advance regardless of answer
    # quality. Prevents LLM from looping on semantically "weak" answers from
    # ESL candidates who may phrase responses differently.
    PIPELINE_PROGRESSION_MIN_WORDS: int = 20

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
    EXOTEL_FLOW_URL: str = ""
    EXOTEL_ESTIMATED_COST_PER_MINUTE_USD: float = 0.005
    EXOTEL_VALIDATE_SIGNATURES: bool = False

    # --- Runtime selection ---
    TELEPHONY_PROVIDER: str = "twilio"  # twilio, exotel, mock
    VOICE_RUNTIME: str = "openai_realtime"  # openai_realtime, deepgram_openai
    PIPELINE_REASONING_PROVIDER: str = "openai"
    TTS_PROVIDER: str = "deepgram"  # deepgram, sarvam
    STT_PROVIDER: str = "deepgram"  # deepgram, openai
    OPENAI_STT_TURN_DETECTION_MODE: str = "server_vad"  # server_vad, manual_commit
    CALL_V2_INTERACTIVE_STYLE_ENABLED: bool = True


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
    COMPANY_NAME: str = ""  # Shown in the call opener: "Hello {name}, this is a call from {COMPANY_NAME}..."
    CALL_V2_SIMULATOR_ENABLED: bool = True
    CALL_V2_SIMULATOR_TOKEN: str = ""
    CALL_V2_SIMULATOR_REAL_AUDIO_ENABLED: bool = True

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
