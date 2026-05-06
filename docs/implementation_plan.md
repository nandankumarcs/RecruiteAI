# RecruiteAI — Implementation Plan

> **Project Root:** `/Users/mac/RecruiteAI`
> **Last Updated:** 2026-05-06
> **Status:** Planning

---

## 1. Project Overview

RecruiteAI is an AI-powered recruiter platform that automates telephonic interview rounds. Users create jobs, upload candidate resumes, and trigger AI-driven phone interviews. The system extracts phone numbers from resumes, generates tailored interview questions using LangChain agents, initiates outbound calls via Twilio, conducts real-time voice interviews using OpenAI GPT-4o Realtime Mini, and records conversations with full transcripts and AI-generated evaluations.

### Key Decisions
- **Auth**: Email/password JWT authentication, first user seeded via migration
- **Resume Formats**: PDF + DOCX supported
- **Questions**: Auto-generated from resume + job description (no manual editing)
- **Storage**: Abstraction layer supporting both local filesystem and S3
- **Evaluation**: AI auto-scores candidate + stores remarks post-call
- **Concurrency**: One call at a time (sequential)
- **Testing**: Strict TDD — tests written before implementation
- **UI Components**: shadcn/ui (Tailwind CSS v4)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     REACT FRONTEND (Vite)                       │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐  │
│  │ Login    │ │Dashboard │ │ Job Detail│ │ Call Detail       │  │
│  │ Page     │ │ Page     │ │ Page      │ │ (Transcript+Eval)│  │
│  └──────────┘ └──────────┘ └───────────┘ └──────────────────┘  │
│         │            │            │              │               │
│         └────────────┴────────────┴──────────────┘               │
│                          │ REST API + WebSocket                  │
└──────────────────────────┼───────────────────────────────────────┘
                           │
┌──────────────────────────┼───────────────────────────────────────┐
│                  FASTAPI BACKEND (Python)                        │
│                          │                                       │
│  ┌───────────────────────┴───────────────────────────────┐      │
│  │                    API Layer                          │      │
│  │  /auth  /jobs  /resumes  /calls  /twilio-webhooks     │      │
│  └───────────────────────┬───────────────────────────────┘      │
│                          │                                       │
│  ┌───────────┐ ┌─────────┴──────┐ ┌──────────────────────┐      │
│  │ Auth      │ │ Service Layer  │ │  Agent Layer         │      │
│  │ Service   │ │                │ │  (LangChain)         │      │
│  │ (JWT)     │ │ • Job Service  │ │                      │      │
│  └───────────┘ │ • Resume Svc   │ │ • Resume Parser Agent│      │
│                │ • Call Service │ │ • Question Gen Agent │      │
│  ┌───────────┐ │ • Storage Svc  │ │ • Interview Agent    │      │
│  │ Telephony │ └────────────────┘ │ • Evaluation Agent   │      │
│  │ Service   │                    └──────────────────────┘      │
│  │ (Twilio)  │                                                  │
│  └─────┬─────┘                                                  │
│        │        ┌──────────────────────────────────────┐        │
│        │        │  WebSocket Bridge                     │        │
│        │        │  Twilio Media Stream ↔ OpenAI Realtime│        │
│        │        └──────────────────────────────────────┘        │
└────────┼────────────────────────────────────────────────────────┘
         │
    ┌────┴────┐    ┌───────────────┐    ┌──────────┐
    │ Twilio  │    │ OpenAI API    │    │PostgreSQL│
    │ Voice   │    │ • GPT-4o      │    │          │
    │ PSTN    │    │ • Realtime    │    │          │
    └─────────┘    └───────────────┘    └──────────┘
```

### Agent Architecture (4 Specialized Agents)

| Agent | Purpose | LLM | Trigger |
|---|---|---|---|
| **Resume Parser Agent** | Extract structured data (name, phone, email, skills, experience) from resume text | GPT-4o | On resume upload |
| **Question Generator Agent** | Generate 8-12 tailored interview questions from JD + resume | GPT-4o | Before call initiation |
| **Interview Agent** | Conduct real-time voice interview via Twilio + OpenAI Realtime | GPT-4o-realtime-mini | During phone call |
| **Evaluation Agent** | Score candidate and generate remarks from transcript | GPT-4o | After call completion |

---

## 3. Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Frontend | React + Vite + TypeScript | React 18, Vite 6 |
| UI Components | shadcn/ui + Tailwind CSS | Tailwind v4 |
| State | React Context + TanStack Query | v5 |
| Routing | React Router | v7 |
| Backend | FastAPI + Python | Python 3.11+ |
| ORM | SQLAlchemy 2.0 (async) | 2.0+ |
| Migrations | Alembic | Latest |
| Database | PostgreSQL | 16 |
| Auth | JWT (python-jose + passlib[bcrypt]) | — |
| AI/Agents | LangChain + OpenAI | Latest |
| Voice AI | OpenAI Realtime API (gpt-4o-mini-realtime-preview) | — |
| Telephony | Twilio Voice + Media Streams | — |
| Resume Parsing | pypdf + python-docx + regex | — |
| Storage | Local FS / S3 (boto3) abstraction | — |
| Testing (BE) | pytest + pytest-asyncio + httpx | — |
| Testing (FE) | Vitest + React Testing Library | — |
| Dev Tunneling | ngrok | — |

---

## 4. Database Schema

### 4.1 Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
-- Seed: dinesh.tomar@yopmail.com / Password@123
```

### 4.2 Jobs Table
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    requirements TEXT,
    status VARCHAR(50) DEFAULT 'active',  -- active, paused, closed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### 4.3 Resumes Table
```sql
CREATE TABLE resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_name VARCHAR(255),
    phone_number VARCHAR(50),
    email VARCHAR(255),
    file_path VARCHAR(500) NOT NULL,
    file_type VARCHAR(10) NOT NULL,  -- pdf, docx
    raw_text TEXT,
    parsed_data JSONB,  -- {skills:[], experience:[], education:[]}
    status VARCHAR(50) DEFAULT 'uploaded',  -- uploaded, parsed, called, completed
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.4 Interview Questions Table
```sql
CREATE TABLE interview_questions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    category VARCHAR(50),  -- introduction, technical, behavioral, situational
    difficulty INTEGER DEFAULT 1,  -- 1-5
    order_index INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.5 Calls Table
```sql
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id UUID REFERENCES resumes(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    twilio_call_sid VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    -- pending, ringing, in_progress, completed, failed, no_answer
    phone_number VARCHAR(50) NOT NULL,
    duration_seconds INTEGER,
    recording_url VARCHAR(500),
    recording_path VARCHAR(500),
    transcript TEXT,
    ai_evaluation JSONB,
    -- {overall_score:int, categories:{technical:int, communication:int,
    --  experience:int}, remarks:str, strengths:[], weaknesses:[]}
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 4.6 Call Messages Table
```sql
CREATE TABLE call_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID REFERENCES calls(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- assistant, user
    content TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 5. Project Structure

```
RecruiteAI/
├── docs/
│   ├── implementation_plan.md      # This file
│   ├── wireframes.md               # Detailed UI wireframes
│   └── handoff.md                  # Session continuity document
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn components (auto-generated)
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── Header.tsx
│   │   │   │   └── AppLayout.tsx
│   │   │   ├── jobs/
│   │   │   │   ├── CreateJobDialog.tsx
│   │   │   │   ├── JobCard.tsx
│   │   │   │   └── JobStatusBadge.tsx
│   │   │   ├── resumes/
│   │   │   │   ├── ResumeUploader.tsx
│   │   │   │   ├── ResumeTable.tsx
│   │   │   │   └── ResumeDetailSheet.tsx
│   │   │   └── calls/
│   │   │       ├── CallStatusBadge.tsx
│   │   │       ├── TranscriptViewer.tsx
│   │   │       ├── EvaluationCard.tsx
│   │   │       └── CallProgressIndicator.tsx
│   │   ├── pages/
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── JobsPage.tsx
│   │   │   ├── JobDetailPage.tsx
│   │   │   └── CallDetailPage.tsx
│   │   ├── services/
│   │   │   └── api.ts              # Axios/fetch API client
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useJobs.ts
│   │   │   ├── useResumes.ts
│   │   │   └── useCalls.ts
│   │   ├── lib/
│   │   │   └── utils.ts            # shadcn utility (cn helper)
│   │   ├── context/
│   │   │   └── AuthContext.tsx
│   │   ├── types/
│   │   │   └── index.ts            # Shared TypeScript interfaces
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── components.json             # shadcn config
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app + CORS + lifespan
│   │   ├── config.py               # Pydantic Settings
│   │   ├── database.py             # Async SQLAlchemy engine + session
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── job.py
│   │   │   ├── resume.py
│   │   │   ├── question.py
│   │   │   ├── call.py
│   │   │   └── call_message.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── job.py
│   │   │   ├── resume.py
│   │   │   ├── call.py
│   │   │   └── question.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── jobs.py
│   │   │   ├── resumes.py
│   │   │   ├── calls.py
│   │   │   └── twilio_webhooks.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── auth_service.py
│   │   │   ├── job_service.py
│   │   │   ├── resume_service.py
│   │   │   ├── call_service.py
│   │   │   └── storage_service.py  # Local + S3 abstraction
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── resume_parser_agent.py
│   │   │   ├── question_generator_agent.py
│   │   │   ├── interview_agent.py     # OpenAI Realtime bridge
│   │   │   └── evaluation_agent.py
│   │   ├── telephony/
│   │   │   ├── __init__.py
│   │   │   ├── twilio_client.py
│   │   │   ├── media_stream_handler.py
│   │   │   └── realtime_bridge.py     # Twilio ↔ OpenAI WS bridge
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── security.py           # JWT encode/decode, password hash
│   │   │   ├── dependencies.py       # get_current_user, get_db
│   │   │   └── exceptions.py         # Custom exception classes
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── helpers.py
│   ├── tests/
│   │   ├── conftest.py               # Fixtures: test DB, client, auth
│   │   ├── test_auth.py
│   │   ├── test_jobs.py
│   │   ├── test_resumes.py
│   │   ├── test_calls.py
│   │   ├── test_resume_parser.py
│   │   ├── test_question_generator.py
│   │   └── test_storage.py
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── alembic.ini
│   ├── requirements.txt
│   └── .env
│
├── uploads/                          # Resume storage (local)
├── recordings/                       # Call recordings (local)
├── docker-compose.yml                # PostgreSQL dev
├── .env.example
├── .gitignore
└── README.md
```

---

## 6. API Endpoints

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Login → returns JWT access + refresh tokens |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Get current user profile |

### Jobs
| Method | Path | Description |
|---|---|---|
| POST | `/api/jobs` | Create a new job |
| GET | `/api/jobs` | List all jobs (with counts) |
| GET | `/api/jobs/{id}` | Get job detail |
| PUT | `/api/jobs/{id}` | Update job |
| DELETE | `/api/jobs/{id}` | Delete job (cascade) |

### Resumes
| Method | Path | Description |
|---|---|---|
| POST | `/api/jobs/{job_id}/resumes` | Upload resume(s) — multipart |
| GET | `/api/jobs/{job_id}/resumes` | List resumes for job |
| GET | `/api/resumes/{id}` | Get resume detail |
| DELETE | `/api/resumes/{id}` | Delete resume |

### Calls
| Method | Path | Description |
|---|---|---|
| POST | `/api/resumes/{resume_id}/calls` | Initiate a call |
| GET | `/api/calls` | List all calls |
| GET | `/api/calls/{id}` | Get call detail + transcript |
| GET | `/api/jobs/{job_id}/calls` | List calls for a job |

### Twilio Webhooks
| Method | Path | Description |
|---|---|---|
| POST | `/twilio/voice` | TwiML response for media stream |
| WS | `/twilio/media-stream` | WebSocket for Twilio audio |
| POST | `/twilio/status` | Call status callback |

---

## 7. Phased Implementation

### Phase 1: Foundation & Project Setup
**Goal**: Scaffold both projects, configure DB, auth, and verify basic connectivity.

**Tasks:**
1. Initialize Vite React TypeScript project in `frontend/`
2. Install and configure shadcn/ui + Tailwind v4
3. Set up FastAPI project in `backend/`
4. Configure SQLAlchemy async + Alembic migrations
5. Create all database models
6. Run initial migration + seed first user
7. Implement JWT auth (login, refresh, me)
8. Set up pytest with async test fixtures
9. Write auth tests
10. Create docker-compose.yml for PostgreSQL
11. Set up .env.example with all required vars

**Verification:**
- `pytest` passes for auth endpoints
- Can login via curl/httpx and get JWT
- Database tables created correctly

---

### Phase 2: Job Management + Storage Layer
**Goal**: Full CRUD for jobs with storage abstraction.

**Tasks:**
1. Implement storage abstraction (LocalStorage + S3Storage)
2. Write storage service tests
3. Implement Job CRUD service + router
4. Write job API tests
5. Build frontend Login page
6. Build frontend Dashboard page (stats cards)
7. Build frontend Jobs page (list + create dialog)
8. Connect frontend to backend API

**Verification:**
- All job CRUD tests pass
- Storage tests pass for local provider
- Browser: Login → Dashboard → Create Job → See job in list

---

### Phase 3: Resume Management + Parser Agent
**Goal**: Upload resumes, parse them, extract structured data.

**Tasks:**
1. Implement Resume Parser Agent (LangChain)
   - PDF text extraction (pypdf)
   - DOCX text extraction (python-docx)
   - Phone number regex extraction
   - GPT-4o structured data extraction (name, email, skills, experience)
2. Write parser agent tests (mock OpenAI)
3. Implement resume upload endpoint (multipart)
4. Implement resume CRUD service + router
5. Write resume API tests
6. Build frontend Job Detail page with resume upload
7. Build ResumeUploader component (drag & drop)
8. Build ResumeTable component

**Verification:**
- Parser correctly extracts phone from sample PDFs/DOCX
- All resume API tests pass
- Browser: Open job → Upload PDF → See parsed candidate info

---

### Phase 4: Question Generation Agent
**Goal**: Auto-generate interview questions from JD + resume.

**Tasks:**
1. Implement Question Generator Agent (LangChain)
   - Takes job description + resume parsed data
   - Generates 8-12 questions across categories
   - Returns structured question list with categories + difficulty
2. Write question generator tests (mock OpenAI)
3. Integrate question generation into call initiation flow
4. Write integration tests

**Verification:**
- Mock tests pass for question generation
- Questions generated match expected schema
- Categories are properly distributed

---

### Phase 5: Telephony + Interview Agent
**Goal**: Twilio outbound calls + OpenAI Realtime voice interview.

**Tasks:**
1. Set up Twilio client (outbound calls)
2. Implement TwiML webhook endpoint
3. Implement WebSocket media stream handler
4. Build Realtime Bridge (Twilio audio ↔ OpenAI Realtime API)
   - G.711 µ-law audio format handling
   - System prompt with interviewer persona + questions
   - Conversation turn management
   - Transcript capture from realtime events
5. Implement call initiation flow:
   - Generate questions → Create call record → Twilio outbound → Bridge
6. Implement call status callback handler
7. Store transcript + recording on call completion
8. Write telephony tests (mock Twilio + OpenAI)
9. Build frontend call trigger button
10. Build CallProgressIndicator (live status via WebSocket)

**Verification:**
- Unit tests pass for all telephony components
- End-to-end: Click "Start Call" → Phone rings → AI interviews → Transcript saved
- (Manual) Test with real phone number

---

### Phase 6: Evaluation Agent + Call Detail UI
**Goal**: Post-call AI evaluation and full call detail view.

**Tasks:**
1. Implement Evaluation Agent (LangChain)
   - Takes transcript + job requirements
   - Scores: overall (1-10), technical, communication, experience
   - Generates remarks, strengths, weaknesses
2. Trigger evaluation automatically after call completion
3. Write evaluation agent tests
4. Build frontend Call Detail page
   - TranscriptViewer (speaker-labeled, timestamped)
   - EvaluationCard (scores + remarks)
   - Audio playback (if recording available)
5. Update Dashboard with call statistics

**Verification:**
- Evaluation tests pass with mock transcripts
- Browser: View call → See transcript → See AI evaluation scores + remarks

---

### Phase 7: Polish & Hardening
**Goal**: Error handling, loading states, responsive design, final testing.

**Tasks:**
1. Add error boundaries and toast notifications
2. Add loading skeletons throughout
3. Responsive design audit
4. End-to-end flow testing
5. Security audit (input validation, SQL injection, XSS)
6. README with setup instructions

**Verification:**
- Full E2E flow works
- No console errors
- Responsive on tablet + desktop

---

## 8. Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/recruiteai

# Auth
SECRET_KEY=your-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Seed User
SEED_USER_EMAIL=dinesh.tomar@yopmail.com
SEED_USER_PASSWORD=Password@123
SEED_USER_NAME=Dinesh Tomar

# OpenAI
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o
OPENAI_REALTIME_MODEL=gpt-4o-mini-realtime-preview

# Twilio
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_PHONE_NUMBER=+1234567890

# Storage
STORAGE_PROVIDER=local
STORAGE_LOCAL_PATH=./uploads
# S3 (when STORAGE_PROVIDER=s3)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_BUCKET=
AWS_S3_REGION=

# App
BACKEND_PORT=8000
FRONTEND_PORT=5173
PUBLIC_URL=https://your-ngrok-url.ngrok.io
```

---

## 9. Testing Strategy

### Backend Tests (pytest)
- **Unit tests**: Each service method, each agent (mocked LLM)
- **Integration tests**: Each API endpoint with test DB
- **Fixtures**: Test database, authenticated client, sample data
- **Mocking**: OpenAI calls mocked at agent level, Twilio mocked

### Frontend Tests (Vitest)
- **Component tests**: Each component renders correctly
- **Integration tests**: Page-level with mocked API
- **E2E**: Browser verification after each phase

### Coverage Targets
- Backend services: >80%
- API endpoints: >80%
- Frontend components: >70%
