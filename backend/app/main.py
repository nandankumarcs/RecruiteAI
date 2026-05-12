"""
RecruiteAI — FastAPI Application Entry Point

Configures the FastAPI app with:
- CORS middleware (allows frontend origin)
- Router registration (auth, jobs, resumes, calls, webhooks)
- Lifespan events (DB table creation + seed user on startup)
- Health check endpoint
"""

import logging
import os
from contextlib import asynccontextmanager

import sys
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import get_settings
from app.core.security import hash_password
from app.database import async_session_factory, engine, Base
from app.models import User  # noqa: F401 — import all models for table creation
from app.models import Job, Resume, InterviewQuestion, Call, CallMessage  # noqa: F401
from app.routers import auth, calls, dashboard, jobs, resumes, twilio_webhooks, exotel_webhooks

settings = get_settings()
logger = logging.getLogger(__name__)


def configure_langsmith_environment() -> None:
    """Mirror explicit settings into LangSmith environment variables when enabled."""
    if not settings.LANGSMITH_TRACING:
        return

    os.environ.setdefault("LANGSMITH_TRACING", "true")
    if settings.LANGSMITH_API_KEY:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
    if settings.LANGSMITH_PROJECT:
        os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
    if settings.LANGSMITH_ENDPOINT:
        os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)


async def ensure_runtime_schema() -> None:
    """Apply additive schema changes needed for local-dev startup without manual migration."""
    statements = [
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS provider VARCHAR(50) DEFAULT 'twilio'",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS voice_runtime VARCHAR(100) DEFAULT 'openai_realtime'",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS provider_call_id VARCHAR(255)",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS cost_breakdown JSON",
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS latency_metrics JSON",
        "UPDATE calls SET provider_call_id = twilio_call_sid WHERE provider_call_id IS NULL AND twilio_call_sid IS NOT NULL",
        "UPDATE calls SET provider = 'twilio' WHERE provider IS NULL",
        "UPDATE calls SET voice_runtime = 'openai_realtime' WHERE voice_runtime IS NULL",
    ]
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement))


async def seed_default_user():
    """
    Seed the first admin user if no users exist in the database.
    Credentials are read from environment variables.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(User).limit(1))
        existing_user = result.scalar_one_or_none()

        if existing_user is None:
            user = User(
                email=settings.SEED_USER_EMAIL,
                hashed_password=hash_password(settings.SEED_USER_PASSWORD),
                full_name=settings.SEED_USER_NAME,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            logger.info(f"Seeded default user: {settings.SEED_USER_EMAIL}")
        else:
            logger.info("Users already exist — skipping seed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan — runs on startup and shutdown.
    - Startup: Create DB tables (if not exist) and seed default user
    - Shutdown: Dispose engine connection pool
    """
    # Startup
    logger.info("Starting RecruiteAI backend...")
    configure_langsmith_environment()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_runtime_schema()
    logger.info("Database tables created/verified.")

    await seed_default_user()
    logger.info("RecruiteAI backend ready.")

    yield

    # Shutdown
    await engine.dispose()
    logger.info("RecruiteAI backend shut down.")


# --- Create FastAPI Application ---
app = FastAPI(
    title="RecruiteAI",
    description="AI-powered recruiter platform for automated telephonic interviews",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="/Users/mac/RecruiteAI/backend/static"), name="static")

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers ---
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(jobs.router)
app.include_router(resumes.router)
app.include_router(calls.router)
# Future routers will be added here:
app.include_router(twilio_webhooks.router)
app.include_router(exotel_webhooks.router)

@app.get("/healhttps{path:path}")
async def healhttps_fallback(path: str):
    logger.info(f"Intercepted mangled Exotel URL: /healhttps{path}")
    return {"status": "ok"}


@app.api_route("/v/{resume_id}.xml", methods=["GET", "POST"])
async def short_voice_webhook(resume_id: str, request: Request):
    return await exotel_voice_webhook(resume_id, request)

# Global cache for Exotel call SID to resume ID mapping
# In a production environment, this should be Redis
exotel_call_cache: dict[str, str] = {}

from app.services.telephony_cache import cache_exotel_call

@app.api_route("/webhooks/exotel/voice/{resume_id}", methods=["GET", "POST"])
async def exotel_voice_webhook(resume_id: str, request: Request):
    """
    Exotel voice webhook returning Twilio-style XML for streaming.
    """
    # Log everything for debugging
    params = dict(request.query_params)
    
    # Exotel often sends parameters in the POST body as form data
    if request.method == "POST":
        try:
            form_data = await request.form()
            params.update(dict(form_data))
        except Exception as e:
            logger.warning(f"Failed to parse form data in Exotel webhook: {e}")

    # PRIORITIZE CustomField from Query Parameters (Exotel reliably sends this)
    custom_field = params.get("CustomField")
    if custom_field and custom_field not in ["{{CustomField}}", ""]:
        resume_id = custom_field
    
    call_sid = params.get("CallSid")
    if call_sid and resume_id and resume_id not in ["{{CustomField}}", "session", "passthru"]:
        cache_exotel_call(call_sid, resume_id)
        print(f"!!! CACHED EXOTEL CALL !!! call_sid={call_sid}, resume_id={resume_id}", file=sys.stderr, flush=True)

    print(f"!!! VOICE WEBHOOK HIT !!! resume_id={resume_id} (from custom_field: {custom_field})", file=sys.stderr, flush=True)
    
    # Small delay to ensure any parallel API cache operations finish
    await asyncio.sleep(0.2)
    
    # DEFINITIVE FORMAT FROM EXOTEL VOICEBOT DOCS:
    # { "url": "wss://..." }
    public_url = "deadline-enjoy-generally-sorry.trycloudflare.com"
    stream_url = f"wss://{public_url}/ws/exotel-media/voice/{resume_id}"
    
    response_payload = {
        "url": stream_url
    }
    
    print(f"!!! SENDING DEFINITIVE JSON RESPONSE !!!\n{response_payload}", file=sys.stderr, flush=True)
    return JSONResponse(content=response_payload)



@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint — returns OK if the server is running."""
    return {"status": "ok", "service": "recruiteai-backend"}
