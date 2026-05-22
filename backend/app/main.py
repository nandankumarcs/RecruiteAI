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
from pathlib import Path

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
from app.routers import auth, calls, dashboard, jobs, resumes, twilio_webhooks, exotel_webhooks, browser_webhooks

settings = get_settings()

# uvicorn's dictConfig only configures its own loggers.
# Add a dedicated handler so app.* loggers always emit regardless of root config.
_app_handler = logging.StreamHandler()
_app_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s: %(message)s"))
_app_handler.setLevel(logging.INFO)
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
_app_logger.addHandler(_app_handler)
_app_logger.propagate = False  # avoid double-printing via uvicorn root handler

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
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")

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
app.include_router(browser_webhooks.router)

@app.get("/healhttps{path:path}")
async def healhttps_fallback(path: str, request: Request):
    logger.info(f"Intercepted mangled Exotel URL: /healhttps{path}")
    params = dict(request.query_params)
    call_sid = params.get("CallSid")
    custom_field = params.get("CustomField")
    if call_sid and custom_field and custom_field not in ["{{CustomField}}", ""]:
        cache_exotel_call(call_sid, custom_field)
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
    """Exotel voice webhook — returns the AgentStream WebSocket URL."""
    params = dict(request.query_params)
    if request.method == "POST":
        try:
            form_data = await request.form()
            params.update(dict(form_data))
        except Exception as exc:
            logger.warning("exotel.voice_webhook: could not parse form data: %s", exc)

    custom_field = params.get("CustomField")
    if custom_field and custom_field not in ["{{CustomField}}", ""]:
        resume_id = custom_field

    call_sid = params.get("CallSid")
    if call_sid and resume_id and resume_id not in ["{{CustomField}}", "session", "passthru"]:
        cache_exotel_call(call_sid, resume_id)
        logger.info("exotel.voice_webhook: cached call_sid=%s resume_id=%s", call_sid, resume_id)

    logger.info(
        "exotel.voice_webhook: resume_id=%s call_sid=%s method=%s",
        resume_id,
        call_sid,
        request.method,
    )

    # Small delay to ensure any parallel API cache operations finish.
    await asyncio.sleep(0.2)

    public_url = settings.PUBLIC_URL.rstrip("/")
    stream_url = (
        f"{public_url.replace('https://', 'wss://').replace('http://', 'ws://')}"
        f"/ws/exotel-media/voice/{resume_id}"
    )
    logger.debug("exotel.voice_webhook: stream_url=%s", stream_url)
    return JSONResponse(content={"url": stream_url})



@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint — returns OK if the server is running."""
    return {"status": "ok", "service": "recruiteai-backend"}
