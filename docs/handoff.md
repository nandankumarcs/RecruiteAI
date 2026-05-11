# RecruiteAI — Handoff (Fresh-Chat Ready)

> Last Updated: 2026-05-11  
> Project Root: `/Users/mac/RecruiteAI`

---

## Current Situation

The active voice runtime is **`deepgram_openai`** (GPT-4o for LLM + Deepgram STT/TTS). This was chosen over `gemini_live_realtime` for cost/stability reasons.

**Critical open bug**: Every call produces **complete silence** — the AI assistant never speaks. The Twilio connection succeeds, Deepgram STT connects, the LLM generates the opener text — but the audio never reaches the caller.

---

## What Was Done This Session

### 1. Cost Optimization Audit (Phase 8 / 9 gaps)
- Reviewed `docs/cost_optimization_implementation_plan.md` against implementation.
- Identified and implemented missing gaps:
  - **`GET /api/dashboard/benchmark`** endpoint added to `backend/app/routers/dashboard.py` (side-by-side runtime performance/cost comparison).
  - **Twilio webhook signature validation** added to `backend/app/dependencies/twilio_signature.py` with new `TWILIO_VALIDATE_SIGNATURES` config flag in `backend/app/config.py`.
  - **Frontend latency metrics** fixed in `frontend/src/pages/CallDetail.tsx` — now shows human-readable ms deltas instead of raw ISO timestamps.
  - **WebSocket reconnect hardening** in `frontend/src/hooks/useCallWebSocket.ts` — exponential backoff with jitter + terminal state detection.
  - **DB commit bug** fixed in `backend/app/routers/calls.py` — `evaluate_call` was missing `commit()`.

### 2. Silence Bug Investigation
The runtime pipeline reaches TTS every time, but the HTTP call to Deepgram's TTS REST API never returns a response.

**Debug flow** (all logged via `backend/debug.log`):
```
Event START received → Generating opener → Opener generated → [TTS_ID] Requesting TTS from Deepgram REST... → [HANGS]
```

No `Response status:` line ever appears.

**Fixes attempted (all failed):**
| Attempt | What was tried | Result |
|---|---|---|
| 1 | Removed `http2=True` from shared `httpx.AsyncClient` | Still hangs |
| 2 | Moved to fresh `httpx.AsyncClient` per TTS call (inside async function) | Still hangs |
| 3 | Switched to `asyncio.to_thread` + sync `requests.post(timeout=15)` | Still hangs |

**Key observations:**
- `curl` to `https://api.deepgram.com/v1/speak` → works, 200 OK, ~1.4s.
- `requests.post()` from venv Python subprocess → works, 200 OK, ~1.0s.
- `httpx.AsyncClient` in standalone asyncio script → works.
- All three approaches hang when called inside the uvicorn WebSocket handler.
- Deepgram STT **WebSocket** connection works fine in the same process.
- The hang is consistent across ALL calls — never produces audio.

**Current state of `_speak_text`** (lines ~198–246 in `deepgram_runtime.py`):
```python
# asyncio.to_thread approach (latest, still hangs)
def _fetch_tts() -> tuple[int, bytes]:
    r = _requests.post(tts_url, headers=headers, json={"text": text_to_speak}, timeout=15)
    return r.status_code, r.content

status_code, audio_bytes = await asyncio.to_thread(_fetch_tts)
# ↑ This await never completes inside the WS handler
```

---

## Hypothesis for Next Session

The hang pattern is highly unusual. Both async httpx AND `asyncio.to_thread + requests` (which is immune to event-loop issues) hang. This points to something **outside Python's async model**:

### Most likely causes to investigate:

1. **OS-level socket or connection limit for the uvicorn process** — the process already holds open sockets to Twilio (WebSocket) and Deepgram STT (WebSocket). A per-process file descriptor limit could block new outbound TCP connections. Check with:
   ```bash
   lsof -p <uvicorn_worker_pid> | wc -l
   ulimit -n
   ```

2. **Network routing / firewall rule blocking HTTPS from this specific process** — the Deepgram SDK WebSocket uses `wss://` (port 443) which might bypass the same issue. Try connecting to port 443 from a raw socket:
   ```python
   import socket, ssl
   s = ssl.wrap_socket(socket.create_connection(("api.deepgram.com", 443), timeout=5))
   ```

3. **Thread pool deadlock** — `asyncio.to_thread` uses `loop.run_in_executor(None, ...)`. If the default executor is somehow exhausted or deadlocked (e.g., another `run_in_threadpool` from FastAPI held a thread lock), the new thread task queues but never starts. Check with:
   ```python
   import concurrent.futures, asyncio
   loop = asyncio.get_event_loop()
   print(loop._default_executor)  # check if full
   ```

4. **The TTS asyncio.create_task never actually runs** — the Twilio media stream delivers ~50 events/sec. If the media receive loop never yields long enough, the TTS task could be starved. Verify by adding a log at the very first line of `_fetch_tts` and checking if it appears.

5. **ngrok tunnel interfering** — the Deepgram STT WebSocket goes out directly. The TTS REST call also goes out directly. But maybe ngrok has a per-connection limit that blocks the third outbound connection from the uvicorn process.

---

## Immediate Next Steps (Priority Order)

1. **Add a log at the absolute first line of `_fetch_tts`** to confirm whether the thread is ever started:
   ```python
   def _fetch_tts() -> tuple[int, bytes]:
       log_debug(f"[{tts_run_id}] _fetch_tts THREAD STARTED")
       r = _requests.post(...)
   ```
   If this log never appears → `asyncio.to_thread` is not executing the function → thread pool deadlock.
   If it appears but `Response status:` doesn't → requests.post itself is hanging.

2. **Check open file descriptors** for the uvicorn worker PID during a live call:
   ```bash
   lsof -p <pid> | wc -l   # total
   lsof -p <pid> | grep "api.deepgram"
   ```

3. **Test outbound HTTPS from inside the running process** by adding a temporary debug route:
   ```python
   @app.get("/debug/tts-test")
   async def debug_tts():
       import requests
       r = requests.get("https://api.deepgram.com", timeout=5)
       return {"status": r.status_code}
   ```

4. **Consider switching TTS to Deepgram Python SDK** — `DeepgramClient.speak.asyncrest` might handle the connection differently than raw httpx/requests.

5. **Alternative: Use OpenAI TTS instead of Deepgram TTS** — since we're already authenticated to OpenAI for LLM, `openai.audio.speech.create()` could be a drop-in replacement that avoids the Deepgram TTS connection entirely.

6. **Nuclear option: run TTS in a subprocess** — `asyncio.create_subprocess_exec` with a minimal Python script that calls Deepgram and pipes back audio bytes. Totally isolated from the event loop.

---

## Active Runtime Config

```
VOICE_RUNTIME=deepgram_openai
TELEPHONY_PROVIDER=twilio
TWILIO_MOCK_MODE=false
TWILIO_VALIDATE_SIGNATURES=false
PUBLIC_URL=<active ngrok https URL>
DEEPGRAM_API_KEY=<set>
OPENAI_API_KEY=<set>
```

**Debug logging**: All runtime logs write to `/Users/mac/RecruiteAI/backend/debug.log` (via `backend/app/debug_log.py`). Tail this file, not `uvicorn.log`, to trace TTS/STT events.

---

## Files Changed This Session

| File | Change |
|---|---|
| `backend/app/services/deepgram_runtime.py` | Silence bug investigation: removed shared httpx client, tried fresh client, tried asyncio.to_thread. **Current: asyncio.to_thread approach (line ~208)** |
| `backend/app/routers/dashboard.py` | Added `GET /api/dashboard/benchmark` endpoint |
| `backend/app/routers/calls.py` | Fixed missing `commit()` in `evaluate_call` |
| `backend/app/config.py` | Added `TWILIO_VALIDATE_SIGNATURES` flag |
| `backend/app/dependencies/twilio_signature.py` | New: Twilio webhook signature validation |
| `backend/app/routers/twilio_webhooks.py` | Integrated signature validation dependency |
| `frontend/src/pages/CallDetail.tsx` | Latency metrics: raw timestamps → human-readable ms |
| `frontend/src/hooks/useCallWebSocket.ts` | Exponential backoff + terminal state detection |

---

## Test / Verification Notes

- `tests/test_calls.py` — 17 passed in last full run.
- `tests/test_cost_optimization.py` — blocked by schema race condition on test DB setup (pre-existing, unrelated to runtime).
- Backend server: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Frontend: `cd frontend && npm run dev`
- ngrok: must be running and `PUBLIC_URL` in `.env` must match the tunnel URL.

---

## Git / Working Tree

Working tree is **intentionally dirty**. Do not assume anything is committed.

---

## Fresh Chat Starter Prompt

> "Read `/Users/mac/RecruiteAI/docs/handoff.md` first. The active voice runtime is `deepgram_openai`. There is a critical silence bug: every call connects successfully but the AI never speaks. The TTS HTTP call to Deepgram REST API (`https://api.deepgram.com/v1/speak`) hangs indefinitely inside the uvicorn WebSocket handler — both `httpx.AsyncClient` and `asyncio.to_thread + requests.post()` approaches hang. The same call works fine from curl and standalone Python. Start by checking open file descriptors and thread pool state, then systematically narrow down whether the issue is OS-level (FD limits), thread pool exhaustion, or event-loop starvation of the TTS asyncio task."
