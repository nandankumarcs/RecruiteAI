# RecruiteAI

AI-powered telephonic recruiter platform using Twilio, OpenAI Realtime API, FastAPI, and React.

## Stack
- **Frontend**: React 18, Vite, TypeScript, Tailwind CSS v4, shadcn/ui
- **Backend**: FastAPI (Python 3.11+), PostgreSQL, SQLAlchemy 2.0 (Async), Alembic
- **AI/Agents**: LangChain, OpenAI Realtime API (WebSockets)
- **Telephony**: Twilio Voice

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL
- `ngrok` (for Twilio webhook testing)

### 2. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy env and fill in credentials
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

### 3. Frontend Setup
```bash
cd frontend
npm install

# Copy env
cp .env.example .env.local

# Start dev server
npm run dev
```

### 4. Telephony Webhook (Twilio)
Since Twilio needs to reach your local backend for WebSockets/Webhooks, run ngrok:
```bash
ngrok http 8000
```
Then update your Twilio phone number configuration:
- **Webhook**: `https://<your-ngrok-url>/api/twilio/incoming-call` (POST)

## Testing
Run backend tests (TDD):
```bash
cd backend
python -m pytest
```
