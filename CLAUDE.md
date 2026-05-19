# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo layout

Monorepo with two top-level apps:

- `backend/` — FastAPI + SQLAlchemy 2 async + PostgreSQL. Entry: `backend/app/main.py`. Settings centralized in `backend/app/config.py` (Pydantic Settings — never read `os.environ` directly; add new vars there).
- `frontend/` — Vite + React 19 + TypeScript + Tailwind v4 + shadcn/ui. Entry: `frontend/src/main.tsx`. Pages under `src/pages/`, feature components grouped under `src/components/{calls,jobs,resumes,layout,ui}`.

## Common commands

Backend (from `backend/`, with `venv` activated):

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # dev server, docs at /docs
alembic upgrade head                                        # apply migrations
alembic revision --autogenerate -m "msg"                    # new migration
pytest                                                      # full suite (asyncio auto-mode)
pytest tests/test_calls.py::test_name -xvs                  # single test
```

Frontend (from `frontend/`):

```bash
npm run dev      # Vite dev server on :5173
npm run build    # tsc -b && vite build (also serves as type-check)
npm run lint     # eslint
```

Python 3.13 is required (3.14+ breaks pydantic-core). See [README.md](README.md) for full env-var reference.

## High-level architecture

The product is an automated telephonic interviewer. One end-to-end flow spans most of the codebase:

1. **Job + resume intake** → `routers/jobs.py`, `routers/resumes.py`. Resumes upload through `services/storage.py` (local or S3) and are parsed by `agents/resume_parser_agent.py` via the pipeline in `services/resume_processor.py` + `services/resume_session_manager.py`.
2. **Question generation** → `agents/question_generator_agent.py` produces interview questions stored in `models/question.py`. Prompt assembly lives in `services/prompt_templates.py`; pre-generated TTS audio for prompts is cached via `services/prompt_audio_service.py` + `tasks/audio_generation.py` and surfaced through `models/audio_prompt_asset.py`.
3. **Call placement** → `routers/calls.py` invokes `services/telephony.py` (provider-agnostic façade with Twilio/Exotel/mock backends; `TELEPHONY_PROVIDER` env switches them). `telephony_cache.py` deduplicates outbound attempts.
4. **Live call media bridge** → `routers/twilio_webhooks.py` and `routers/exotel_webhooks.py` receive provider webhooks and open media-stream websockets. `services/realtime_bridge.py` wires the provider's audio stream to a voice runtime selected by `services/runtime_selection_layer.py`:
   - `services/voice_runtime.py` — OpenAI Realtime API path.
   - `services/deepgram_runtime.py` — Deepgram STT + GPT-4o + Deepgram/Sarvam TTS path.
   - `services/tts_providers.py` — pluggable TTS (Deepgram/Sarvam).
   - `services/filler_queue_manager.py` — interjects filler phrases to mask LLM latency.
5. **Persistence + evaluation** → Turn-by-turn transcripts saved as `CallMessage` rows (`models/call_message.py`). After call completion `agents/evaluation_agent.py` (driven from `services/call_evaluation.py`) scores the candidate and writes results onto `models/call.py`. `services/pricing.py` computes per-call cost; `services/observability.py` and `services/analytics.py` feed `routers/dashboard.py`.

LangSmith tracing is opt-in via `LANGSMITH_TRACING=true` — `main.py:configure_langsmith_environment` mirrors settings into env vars.

## Schema management quirk

`main.py:ensure_runtime_schema` runs additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements on startup so local dev keeps working without manual migration steps. Real schema changes still go through Alembic — this is a safety net, not a replacement.

## Telephony providers

`TELEPHONY_PROVIDER` chooses `twilio`, `exotel`, or `mock`. Mock mode synthesizes a call without external credentials and is the default for local development. For live calls, `PUBLIC_URL` must be a public HTTPS endpoint (ngrok during local testing) — webhook URLs are passed per-call rather than configured in the provider dashboard.

## Voice runtime selection

`VOICE_RUNTIME` env: `openai_realtime` (single-model path) or `deepgram_openai` (Deepgram STT → GPT-4o → TTS). `TTS_PROVIDER` selects `deepgram` or `sarvam`. The selection layer logs and persists which runtime served each call so cost/latency reports can compare them.

## Tests

`pytest` runs from `backend/`. `pytest.ini` enables `asyncio_mode = auto` (no need to decorate every async test). Tests live in `backend/tests/` and mirror module names (e.g. `test_realtime_bridge.py`, `test_runtime_selection_layer.py`). There is no frontend test runner — `npm run build` is the type-check gate.

## Codebase navigation

Per [.cursorrules](.cursorrules), prefer `graphify-out/GRAPH_REPORT.md` ("Community Hubs" and "God Nodes" sections) over wide greps when orienting in unfamiliar areas — it's token-efficient. Generate it with `/graphify` if it doesn't exist.

## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore the codebase.** The graph is faster, cheaper (fewer tokens), and gives you structural context (callers, dependents, test coverage) that file scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep/Glob
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with `callers_of` / `callees_of` / `imports_of` / `tests_for`
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key MCP Tools

| Tool                        | Use when                                               |
| --------------------------- | ------------------------------------------------------ |
| `semantic_search_nodes`     | Finding functions/classes by name or concept           |
| `query_graph`               | Tracing callers, callees, imports, tests, dependencies |
| `detect_changes`            | Reviewing code changes — gives risk-scored analysis    |
| `get_review_context`        | Need source snippets for review — token-efficient      |
| `get_impact_radius`         | Understanding blast radius of a change                 |
| `get_affected_flows`        | Finding which execution paths are impacted             |
| `get_architecture_overview` | Understanding high-level codebase structure            |
| `list_communities`          | Discovering logical module groupings                   |
| `refactor_tool`             | Planning renames, finding dead code                    |
| `get_flow_tool`             | Tracing a specific execution flow end-to-end           |

### CLI Commands (also wired as hooks)

| Command                                        | When it runs                | Purpose                                |
| ---------------------------------------------- | --------------------------- | -------------------------------------- |
| `uvx code-review-graph update --skip-flows`    | After every Edit/Write/Bash | Keeps graph in sync with latest code   |
| `uvx code-review-graph status`                 | Session start               | Confirms graph is healthy              |
| `uvx code-review-graph detect-changes --brief` | Pre-commit                  | Risk-scored summary of what's changing |

### Workflow

1. Graph auto-updates after every file edit (via `PostToolUse` hook).
2. Start exploration with `semantic_search_nodes` or `get_architecture_overview`.
3. Use `detect_changes` + `get_review_context` for all code reviews.
4. Use `get_impact_radius` before any refactor or deletion.
5. Use `query_graph` pattern="tests_for" to check test coverage before shipping.

## Engineering discipline — how to approach problems

**Fix root causes, never symptoms.**
Before writing any fix, ask: *is this addressing why the problem exists, or just hiding it?* A heuristic added on top of a broken design is a symptom fix. Heuristics accumulate, conflict, and create new bugs. When you find yourself adding a third band-aid to the same area, stop — the design is wrong.

**Understand before acting.**
Read the relevant code fully. Trace the actual execution path. Check what previous fixes exist and why they were made. Rushing to implement before understanding is how fixes void each other. If a fix seems simple but the area is complex, spend more time reading — never less.

**New fixes must not void existing ones.**
Before implementing, explicitly check: does this interact with any recent change? Which invariants does the existing code depend on? A fix that breaks a previous fix is worse than no fix. List the relevant recent changes mentally and verify compatibility.

**Architectural changes over accumulated patches.**
When multiple band-aids point at the same area, step back and redesign that area cleanly. The cost of one proper redesign is always lower than the accumulated cost of maintaining a pile of heuristics. When in doubt, propose a clean design first, then implement.

**Automated tests before manual testing.**
For any behavioral change, write tests that encode the invariants first. Tests are how we know a fix works AND doesn't break anything. If you can't express the expected behavior as a test, you don't understand it well enough to implement.

## Conventions worth knowing

- All settings flow through `app/config.py:Settings`; add new env vars there and access via `get_settings()`.
- Service modules in `app/services/` are the integration seam — routers stay thin and delegate.
- Agents (`app/agents/`) are the LLM-facing layer (LangChain). Prompts are kept in `services/prompt_templates.py`.
- Models import order matters for table creation — `main.py` imports them explicitly with `# noqa: F401`.
