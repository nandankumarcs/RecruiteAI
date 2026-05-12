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
    allow_origins=[
        settings.FRONTEND_URL, 
        "http://localhost:5173", 
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175"
    ],
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

    # If Passthrough passed literal {{CustomField}} or 'passthru' in the path, extract from query params
    if resume_id in ["{{CustomField}}", "passthru"] or "%7B%7BCustomField%7D%7D" in request.url.path:
        resume_id = params.get("CustomField", resume_id)

    call_sid = params.get("CallSid")
    if call_sid and resume_id and resume_id != "{{CustomField}}":
        cache_exotel_call(call_sid, resume_id)
        print(f"!!! CACHED EXOTEL CALL !!! call_sid={call_sid}, resume_id={resume_id}", file=sys.stderr, flush=True)

    print(f"!!! VOICE WEBHOOK HIT !!! resume_id={resume_id}", file=sys.stderr, flush=True)
    
    # User feedback suggests that Connect Applet with Dynamic URL expects JSON.
    # While we use Stream applet, if it's configured as a dynamic URL, it might also expect JSON.
    # We check the Accept header or just provide JSON if it looks like a dynamic URL call.
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header or params.get("format") == "json":
        # Dynamic Connect response format
        return {
            "destination": {
                "numbers": [params.get("To", "")]
            },
            "record": True,
            "max_ringing_duration": 45,
            "max_conversation_duration": 3600
        }

    # Default to ExoML (XML)
    xml_content = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    return Response(content=xml_content, media_type="application/xml")



@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint — returns OK if the server is running."""
    return {"status": "ok", "service": "recruiteai-backend"}
