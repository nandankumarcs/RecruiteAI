# RecruiteAI — Agent Guide

AI-powered recruitment platform: automated telephonic interviews, resume parsing, AI screening calls, transcript capture, candidate evaluation.

## Architecture

Two independent apps (not a monorepo with shared tooling):

| App | Path | Stack | Port |
|-----|------|-------|------|
| Backend | `backend/` | FastAPI, SQLAlchemy 2 async, PostgreSQL, Alembic, LangChain | 8000 |
| Frontend | `frontend/` | React 19, Vite 8, TypeScript 6, Tailwind 4, radix-ui (shadcn) | 5173 |

## Critical Constraints

- **Python 3.13 required** — 3.14+ fails to build pydantic-core
- **Node.js 20+** required
- PostgreSQL must be running before backend starts

## Developer Commands

### Backend

```bash
cd backend
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit: DATABASE_URL, SECRET_KEY, OPENAI_API_KEY
alembic upgrade head   # migrations (also auto-creates tables on startup)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # set VITE_API_URL=http://localhost:8000/api
npm run dev
```

### Tests

```bash
# Backend — pytest (async, uses isolated schema `recruiteai_test`)
cd backend && source venv/bin/activate
pytest

# Single test
pytest tests/test_auth.py -k test_login

# Frontend — no unit tests; typecheck via build
cd frontend && npm run build   # runs tsc -b && vite build
```

### Lint

```bash
cd frontend && npm run lint   # eslint
# Backend has no lint config
```

## Backend Architecture Notes

- **Entry point**: `backend/app/main.py` — creates `app` FastAPI instance
- **Routers**: `auth`, `dashboard`, `jobs`, `resumes`, `calls`, `twilio_webhooks`, `exotel_webhooks`
- **Call v2 runtime** (`backend/app/call_v2/`): primary runtime for Exotel. Handles telephony, STT, endpointing/speculation, agent, TTS, persistence, and trace. Exotel calls are routed here exclusively — the v1 services never see an Exotel provider.
- **v1 call services** (`backend/app/services/`): `realtime_bridge.py` (OpenAI Realtime, Twilio/browser), `deepgram_runtime.py` (Deepgram STT + GPT-4o + TTS, browser only now), `voice_runtime.py` (dispatcher for browser/Twilio), `telephony.py` (Twilio/Exotel/browser/mock facade), `resume_processor.py`, `call_evaluation.py`. These remain active for browser-provider and Twilio calls (Phase 12 deferred).
- **Startup behavior**: `Base.metadata.create_all` runs on startup (auto-creates tables). Alembic migrations exist but are not strictly required for local dev. A `ensure_runtime_schema()` function applies additive ALTER TABLE statements for columns not yet in migrations.
- **Seed user**: Created on first startup if no users exist. Defaults from `backend/app/config.py`: `nandan.kumar@crownstack.com` / `Password@123`
- **Telephony modes**: `TELEPHONY_PROVIDER` = `twilio` | `exotel` | `browser` | `mock`. Mock mode simulates calls without credentials.
- **Voice runtimes**: Exotel always uses `call_v2` (hardcoded in `routers/calls.py`). Other providers use `VOICE_RUNTIME` = `openai_realtime` | `deepgram_openai`. `TTS_PROVIDER` = `deepgram` | `sarvam`.
- **Exotel URL mangling**: Exotel mangles `/health` to `/healhttps` — there's a catch-all route for this.
- **CORS**: Wide open (`allow_origins=["*"]`) — fine for dev, tighten for production.
- **Storage**: `STORAGE_PROVIDER=local` stores resumes in `backend/uploads/`. S3 also supported.

## Call V2 Development Rules

Call v2 is the primary call runtime for Exotel on the `codex/call-v2-planning` branch. Phases 1–11 are complete and the live acceptance call passed. Phase 12 (Twilio adapter) is deferred. Read `docs/call-v2/README.md` first, then follow the documents in order.

Core v2 principles:

- Build a general-purpose calling agent runtime; recruitment is the first configuration, not a hard-coded runtime assumption.
- Keep boundaries explicit: telephony adapter, audio codec, STT engine, endpointing/speculation, call agent, TTS/audio resolver, persistence, and trace logging.
- The LLM call agent owns conversation policy from instructions, scope, tools, questions, context, and conversation history.
- Runtime owns mechanics: stream lifecycle, generation ids, cancellation, persistence, tool execution safety, TTS playback, barge-in, post-TTS guard, and provider cleanup.
- Do not add a v1/v2 runtime flag. The branch and implementation path are the isolation boundary.
- Simulator/browser testing comes first, then Exotel, then Twilio.

Speculation rules:

- Speculative processing may read context but must not persist transcript, execute tools, start TTS, update durable call state, or end the call until the turn is confirmed.
- Every tentative/confirmed turn, agent run, and TTS task must carry a generation id.
- Only the latest confirmed generation may speak.
- Endpointing must consider inbound audio timing, not just delayed STT event arrival time.
- Keep a post-TTS guard state so candidate speech immediately after assistant audio is not ignored.

Cache rules:

- Cache is an audio delivery optimization only. It must never decide what the agent should say.
- Use exact approved audio cache hits only after the agent has chosen `spoken_text`.
- Do not semantic-cache live conversation responses.
- Do not persistently cache candidate-specific text, question explanations, clarification responses, or previous-answer-dependent follow-ups.
- Cache misses must safely fall back to live TTS.

Testing and implementation rules:

- Build one module and one seam at a time; a module is not done until its downstream seam passes.
- Every practical bug found in manual/live testing must become an automated test, fixture, simulator scenario, or manual checklist item.
- Every simulator and live call test should produce a trace with provider events, STT events, endpointing decisions, agent run lifecycle, cache decisions, TTS lifecycle, cancellations, and persistence commits.
- Manual simulator testing should include human candidate testing and ChatGPT Voice candidate testing.
- Refactor freely when it improves the architecture, but add regression coverage before changing behavior that other code depends on.
- Do not leave stale codeblocks, commented-out alternatives, unused helpers, dead flags, or shadow implementations after a change.
- If a requested change conflicts with the v2 architecture, phase boundaries, or test gates, push back and explain the safer path instead of following it blindly.
- At the end of every implementation phase, perform a dedicated self-review of the changed code against the plan, existing runtime behavior, seam contracts, tests, and cleanup rules before declaring the phase complete.

## Test Fixtures (backend)

- `client` — async HTTP client with test DB session (ASGITransport)
- `test_user` — creates a user in test DB
- `auth_headers` — JWT token for test user
- `authenticated_client` — client with auth headers pre-set
- Tests run in isolated PostgreSQL schema `recruiteai_test`, created/dropped per session

## Live Calls (ngrok)

```bash
ngrok http 8000
# Set PUBLIC_URL=https://<ngrok-url> in .env, restart backend
```

## Docker Compose

`docker-compose.yml` only runs PostgreSQL (16) and nginx. Backend/frontend services are commented out — dev runs natively.

## File Conventions

- Analysis/test markdown files (`TASK_*.md`, `*_ANALYSIS.md`, `*_RESULTS.md`) are gitignored scratch artifacts — safe to ignore
- `graphify-out/` is a generated code navigation report (gitignored)
- `scratch/` is a temporary workspace (gitignored)
