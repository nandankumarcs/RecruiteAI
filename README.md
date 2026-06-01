# RecruiteAI

AI-powered recruitment platform for automated telephonic interviews — job setup, resume parsing, AI screening calls, transcript capture, and candidate evaluation.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite, TypeScript, Tailwind v4, shadcn/ui |
| Backend | FastAPI, SQLAlchemy 2 (async), PostgreSQL, Alembic |
| LLM (live calls) | Groq — llama-4-scout-17b |
| LLM (async agents) | OpenAI — gpt-4o-mini |
| Telephony | Exotel / Twilio (mock mode for local dev) |
| STT | Deepgram nova-2 |
| TTS | Sarvam bulbul:v3 / Deepgram Aura |

---

## Prerequisites

- **Python 3.13** (3.14+ not supported — pydantic-core build fails)
- **Node.js 20+**
- **PostgreSQL** running locally
- **ngrok** — only needed for live telephony calls

---

## Setup

### 1. Clone

```bash
git clone https://github.com/nandankumarcs/RecruiteAI.git
cd RecruiteAI
```

### 2. Backend

```bash
cd backend

# Create virtualenv (Python 3.13 required)
python3.13 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — see Environment Variables below

# Create the database
createdb recruiteai

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend: `http://localhost:8000`  
API docs: `http://localhost:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

---

## Environment Variables

Create `backend/.env` by copying `backend/.env.example`. The minimum required to get the app running locally:

### Required

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | e.g. `postgresql+asyncpg://postgres:postgres@localhost:5432/recruiteai` |
| `SECRET_KEY` | JWT signing key — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `OPENAI_API_KEY` | Used for resume parsing, evaluation, and question generation |

### LLM Provider (live calls)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_PROVIDER` | `openai` | Set to `groq` to use Groq for live call agent |
| `GROQ_API_KEY` | — | Required if `AGENT_PROVIDER=groq` |
| `GROQ_AGENT_MODEL` | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq model |
| `GROQ_FREE_TIER` | `True` | Set to `False` when on a paid Groq plan |

### Voice Pipeline

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_RUNTIME` | `deepgram_openai` | `deepgram_openai` (Deepgram STT + TTS) or `openai_realtime` |
| `TTS_PROVIDER` | `deepgram` | `deepgram` or `sarvam` |
| `STT_PROVIDER` | `deepgram` | `deepgram` |
| `DEEPGRAM_API_KEY` | — | Required for STT (and TTS if `TTS_PROVIDER=deepgram`) |
| `SARVAM_API_KEY` | — | Required if `TTS_PROVIDER=sarvam` |

### Telephony

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEPHONY_PROVIDER` | `mock` | `exotel`, `twilio`, or `mock` |
| `PUBLIC_URL` | `http://localhost:8000` | Public HTTPS URL for webhooks (ngrok for local live calls) |
| `EXOTEL_ACCOUNT_SID` | — | Exotel credentials |
| `EXOTEL_API_KEY` | — | |
| `EXOTEL_API_TOKEN` | — | |
| `EXOTEL_PHONE_NUMBER` | — | Outbound number |
| `EXOTEL_FLOW_URL` | — | ExoML flow URL |
| `TWILIO_ACCOUNT_SID` | — | Twilio credentials (if using Twilio) |
| `TWILIO_AUTH_TOKEN` | — | |
| `TWILIO_PHONE_NUMBER` | — | |

### Seed User

On first startup the backend seeds a default login:

| Variable | Default |
|----------|---------|
| `SEED_USER_EMAIL` | `admin@example.com` |
| `SEED_USER_PASSWORD` | `ChangeMe123!` |
| `SEED_USER_NAME` | `Admin User` |

Change these in `.env` before running for the first time, or update the password after first login.

### Storage

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_PROVIDER` | `local` | `local` (uploads/) or `s3` |
| `AWS_ACCESS_KEY_ID` | — | Required if `STORAGE_PROVIDER=s3` |
| `AWS_SECRET_ACCESS_KEY` | — | |
| `AWS_S3_BUCKET` | — | |
| `AWS_S3_REGION` | — | |

---

## Local Development Modes

### Mock mode (no phone credentials needed)

```env
TELEPHONY_PROVIDER=mock
AGENT_PROVIDER=openai   # or groq
```

Simulates call progression and generates a sample transcript. Good for testing the full flow without any telephony setup.

### Browser simulator (real audio, no phone)

```env
TELEPHONY_PROVIDER=mock
CALL_V2_SIMULATOR_ENABLED=true
```

Opens an in-browser mic/speaker session so you can speak to the AI interviewer directly. No Exotel/Twilio account needed.

### Live calls (Exotel/Twilio)

```bash
# 1. Start ngrok
ngrok http 8000

# 2. Set in .env
PUBLIC_URL=https://your-subdomain.ngrok-free.app
TELEPHONY_PROVIDER=exotel   # or twilio

# 3. Restart backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Webhook URLs are passed dynamically per call — no manual dashboard configuration needed.

---

## Tests

```bash
# Backend
cd backend
source venv/bin/activate
pytest

# Run a specific test
pytest tests/test_call_v2_session.py -xvs

# Frontend type-check
cd frontend
npm run build
```

---

## Company Name in Calls

Set `COMPANY_NAME` in `.env` to customise the call opener:

```env
COMPANY_NAME=Acme Corp
# "Hello, this is a call from Acme Corp..."
```
