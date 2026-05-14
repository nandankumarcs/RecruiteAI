# RecruiteAI

AI-powered recruitment platform for automated telephonic interviews — job setup, resume parsing, AI screening calls, transcript capture, and candidate evaluation.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI, SQLAlchemy 2 (async), PostgreSQL, Alembic |
| AI | OpenAI API (GPT-4o, Realtime API), LangChain |
| Telephony | Twilio / Exotel with media streaming |
| STT/TTS | Deepgram, Sarvam |

## Prerequisites

- **Python 3.13** (3.14+ not supported — pydantic-core build fails)
- **Node.js 20+**
- **PostgreSQL** running and accessible
- **ngrok** (only needed for live telephony calls)

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/nandankumarcs/RecruiteAI.git
cd RecruiteAI
```

### 2. Backend

```bash
cd backend

# Create virtualenv with Python 3.13
python3.13 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — fill in DATABASE_URL, SECRET_KEY, OPENAI_API_KEY at minimum

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend runs at: `http://localhost:8000`
API docs at: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend

npm install

# Configure environment
cp .env.example .env.local
# Edit .env.local — set VITE_API_URL=http://localhost:8000/api

npm run dev
```

Frontend runs at: `http://localhost:5173`

---

## Environment Variables

Copy `.env.example` to `.env` in the `backend/` directory. Fields marked **[REQUIRED]** must be set before the app will start.

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string e.g. `postgresql+asyncpg://user:pass@localhost:5432/recruiteai` |
| `SECRET_KEY` | JWT signing key — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `OPENAI_API_KEY` | OpenAI API key |

### Telephony (set one provider)

| Variable | Description |
|----------|-------------|
| `TELEPHONY_PROVIDER` | `twilio`, `exotel`, or `mock` (default: `mock` for local dev) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | Twilio outbound number |
| `EXOTEL_ACCOUNT_SID` | Exotel account SID |
| `EXOTEL_API_KEY` | Exotel API key |
| `EXOTEL_API_TOKEN` | Exotel API token |
| `EXOTEL_PHONE_NUMBER` | Exotel outbound number |
| `EXOTEL_FLOW_URL` | Exotel ExoML flow URL for your account |

### App URLs (required for live telephony)

| Variable | Default | Description |
|----------|---------|-------------|
| `PUBLIC_URL` | `http://localhost:8000` | Publicly reachable backend URL (use ngrok URL for local live calls) |
| `FRONTEND_URL` | `http://localhost:5173` | Frontend URL (used for CORS) |

### STT / TTS

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPGRAM_API_KEY` | — | Required if using Deepgram STT/TTS |
| `SARVAM_API_KEY` | — | Required if `TTS_PROVIDER=sarvam` |
| `VOICE_RUNTIME` | `deepgram_openai` | `openai_realtime` or `deepgram_openai` |
| `TTS_PROVIDER` | `deepgram` | `deepgram` or `sarvam` |

### Seed User

On first startup the backend creates a default user from these values:

| Variable | Default |
|----------|---------|
| `SEED_USER_EMAIL` | `admin@example.com` |
| `SEED_USER_PASSWORD` | `ChangeMe123!` |
| `SEED_USER_NAME` | `Admin User` |

Change these in `.env` before running for the first time.

---

## Running Without Real Phone Calls (Mock Mode)

Set `TELEPHONY_PROVIDER=mock` in `.env`. The backend will simulate call progression and generate a sample transcript — no Twilio/Exotel credentials needed.

---

## Running Live Calls Locally (ngrok)

Live telephony requires a public HTTPS endpoint for webhooks and media streaming.

```bash
# 1. Start ngrok
ngrok http 8000

# 2. Update .env
PUBLIC_URL=https://your-subdomain.ngrok-free.app

# 3. Restart backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The app passes all webhook URLs dynamically when placing calls — no manual Twilio/Exotel dashboard config needed for outbound-only testing.

---

## Running Tests

```bash
# Backend
cd backend
source venv/bin/activate
pytest

# Frontend type-check
cd frontend
npm run build
```

---

## Storage

Resumes are stored locally under `backend/uploads/` by default (`STORAGE_PROVIDER=local`).

For S3, set:
```
STORAGE_PROVIDER=s3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=...
AWS_S3_REGION=...
```
