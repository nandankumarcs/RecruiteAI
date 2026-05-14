# RecruiteAI

AI recruiter workflow for job setup, resume parsing, interview question generation, outbound interview calls, transcript capture, and AI evaluation.

## Stack

- Frontend: React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui
- Backend: FastAPI, SQLAlchemy 2 async, PostgreSQL, Alembic
- AI: OpenAI API, LangChain
- Telephony: Twilio Voice with media streaming

## What Works Today

- Authenticated recruiter login
- Job CRUD and dashboard metrics
- Resume upload, parsing, structured candidate data, and resume detail modal
- Interview question generation per resume
- Outbound interview call creation
- Live call status tracking
- Transcript capture and AI evaluation
- Call detail page with transcript, evaluation, and recording playback

## Prerequisites

- Python 3.11 or newer
- Node.js 20 or newer
- PostgreSQL
- `ngrok` for real Twilio testing

## Backend Setup

```bash
cd /Users/mac/RecruiteAI/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend base URL: [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Frontend Setup

```bash
cd /Users/mac/RecruiteAI/frontend
npm install
cp .env.example .env.local
npm run dev -- --host 127.0.0.1 --port 5175
```

Frontend URL: [http://127.0.0.1:5175](http://127.0.0.1:5175)

If `VITE_API_URL` is unset, the frontend defaults to `http://127.0.0.1:8000/api`.

## Default Local Login

The backend seeds a default user on startup using environment variables. In the current local setup, the seeded login is:

- Email: `dinesh.tomar@yopmail.com`
- Password: `Password@123`

## Environment Notes

Key backend values:

- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_REALTIME_MODEL`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `TWILIO_MOCK_MODE`
- `PUBLIC_URL`
- `FRONTEND_URL`

### Resume Processing Session Management

The resume upload progress streaming feature uses the following configuration:

- `RESUME_SESSION_TTL_HOURS` (default: 1) - How long to keep inactive processing sessions before cleanup
- `RESUME_SESSION_CLEANUP_INTERVAL_MINUTES` (default: 5) - How often to run the session cleanup task
- `SSE_KEEPALIVE_INTERVAL_SECONDS` (default: 15) - How often to send keepalive events on SSE connections

These settings control the lifecycle of resume processing sessions and Server-Sent Events (SSE) connections used for real-time progress streaming.

## Running in Mock Call Mode

For local product development without placing real phone calls:

- set `TWILIO_MOCK_MODE=true`
- start backend and frontend normally
- start a call from the app

The backend will simulate call progression and create a sample transcript for verification.

## Running Real Twilio Calls Locally

Twilio needs a public HTTPS endpoint for both webhooks and media streaming.

### 1. Start ngrok

```bash
ngrok http 8000
```

### 2. Point the backend at the public URL

Set:

- `PUBLIC_URL=https://your-ngrok-subdomain.ngrok-free.dev`
- `TWILIO_MOCK_MODE=false`

Then restart the backend.

### 3. Twilio callbacks used by this app

The backend generates and uses these endpoints:

- Voice webhook: `/webhooks/twilio/voice`
- Status callback: `/webhooks/twilio/status`
- Recording callback: `/webhooks/twilio/recording`
- Media websocket: `/ws/twilio-media/{resume_id}`

You do not need to hardcode a phone-number voice webhook for outbound-only testing. The app passes the callback URLs when it creates the outbound call.

## Tests

Backend:

```bash
cd /Users/mac/RecruiteAI/backend
./venv/bin/python -m pytest
```

Frontend build verification:

```bash
cd /Users/mac/RecruiteAI/frontend
npm run build
```

## Helpful Product Flows

### Phase 2 style verification

1. Login
2. Create a job
3. Open the job detail page
4. Upload a resume
5. Confirm parsed candidate details appear

### Phase 4 to 6 style verification

1. Generate questions for a parsed resume
2. Start a call
3. Open the call detail page
4. Confirm transcript appears
5. Confirm evaluation appears automatically after completion or run it manually
6. Play the recording if one is available

## Repo Notes

- Resume uploads are stored under backend-managed upload paths
- Real recordings are fetched through an authenticated backend proxy
- Tests use an isolated schema so they do not collide with the live local app database
