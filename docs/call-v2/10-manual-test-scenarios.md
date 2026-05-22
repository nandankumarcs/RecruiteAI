# Call V2 — Manual Test Scenarios

Use the browser simulator at `http://127.0.0.1:5173/sim/v2-call/manual-v2?real_audio=1`
with ChatGPT Voice acting as the candidate. Deepgram handles STT; Sarvam handles TTS.

Start the backend with `LOG_LEVEL=DEBUG` (or `--log-level debug`) so all
`runtime.*`, `agent.*`, `tts.*`, `stt.*` logger lines appear in the terminal.

---

## ChatGPT Voice setup prompt

Open ChatGPT Voice and paste this as the system/opening instruction before each scenario:

```
You are a job candidate named Priya being screened by an AI recruiter over the phone.
The recruiter will speak first. Listen carefully to what they say, then respond naturally
as Priya would. Stay in character throughout — respond only as the candidate, never break
the fourth wall or comment on the AI system. Keep your answers concise (1–3 sentences)
unless asked to elaborate. Pause naturally before answering, as a real caller would.
```

Adjust the specific scenario instruction below per test (append it to the above).

---

## Scenario 1 — Normal short call (happy path)

**Purpose:** Confirm the full happy path end-to-end: consent → questions → polite close.

**ChatGPT instruction to append:**
```
Priya is cooperative and enthusiastic. She immediately grants consent, answers every
question clearly in 1–2 sentences, and says goodbye when the recruiter closes the call.
```

**What to verify:**
- [ ] Opener heard and sounds natural (Sarvam voice)
- [ ] Consent phrase captured as user `CallMessage`
- [ ] Assistant next question persisted and spoken
- [ ] Each answer captured and responded to
- [ ] Call closes cleanly; status → `completed`
- [ ] `latency_metrics.call_v2.trace_summary` present in DB after hangup
- [ ] Logs show `agent.run_completed latency_ms=` and `tts.complete latency_ms=`
- [ ] No `turn.tentative_cancelled` with reason `audio_after_tentative`

---

## Scenario 2 — Pause mid-sentence then continue

**Purpose:** Verify speculative run cancels correctly; no premature assistant response.

**ChatGPT instruction to append:**
```
Priya starts answering, then pauses for about 2 seconds mid-sentence ("I worked on...
[pause] ...a distributed system that..."), then finishes. She does this on the first
question. After the pause she continues naturally without repeating herself.
```

**What to verify:**
- [ ] After the pause: `turn.tentative_cancelled reason=speech_started_after_tentative` in trace
- [ ] Assistant does NOT speak during the pause
- [ ] Full combined answer (before + after pause) is committed as one user turn
- [ ] Logs show two speculative runs; second one confirmed
- [ ] No double-response from assistant

---

## Scenario 3 — One-word / very short answer

**Purpose:** Confirm short answers are not discarded as noise.

**ChatGPT instruction to append:**
```
Priya grants consent with just "Yes." — a single word. Then answers the first technical
question with only "FastAPI." and waits for the recruiter to follow up.
```

**What to verify:**
- [ ] "Yes." persisted as user message (not discarded)
- [ ] "FastAPI." persisted as user message
- [ ] Assistant generates a follow-up, not a repeat of the same question
- [ ] `turn.discarded reason=empty_tentative_endpoint` does NOT appear

---

## Scenario 4 — Barge-in (candidate interrupts assistant)

**Purpose:** Confirm clear-audio fires, stale generation is cancelled, barge-in text captured.

**ChatGPT instruction to append:**
```
While the recruiter is still speaking (partway through their sentence), Priya interrupts
with "Sorry, can I ask something first?" — she doesn't wait for the recruiter to finish.
After the interruption, continue normally when the recruiter responds.
```

**What to verify:**
- [ ] `telephony.clear_outbound_audio reason=candidate_barge_in` in trace
- [ ] Stale TTS generation id appears in `tts.cancelled_generation_ids`
- [ ] Barge-in text "Sorry, can I ask something first?" persisted as user turn
- [ ] Assistant responds to the barge-in naturally (not to previous question)
- [ ] State returns to `LISTENING` then back to `SPEAKING`

---

## Scenario 5 — Clarification request

**Purpose:** Confirm agent explains naturally without cache brittleness.

**ChatGPT instruction to append:**
```
Priya doesn't understand the first technical question. She asks "Sorry, can you explain
what you mean by that?" after hearing it. Once the recruiter explains, she answers
the question.
```

**What to verify:**
- [ ] Explanation goes through live TTS (not cache) — log shows `tts.cache_hit` should NOT appear for the explanation
- [ ] Explanation sounds natural and is contextual to the question
- [ ] After explanation, Priya's answer captured as user turn
- [ ] No echo or repeated explanation

---

## Scenario 6 — Immediate speech after TTS (post-TTS guard)

**Purpose:** Confirm speech right after assistant finishes is captured.

**ChatGPT instruction to append:**
```
Priya starts speaking almost immediately (within 1 second) after the recruiter
finishes speaking — no pause. She's eager and jumps in quickly every time.
```

**What to verify:**
- [ ] `state.transition POST_TTS_GUARD → LISTENING` visible in trace before user turn
- [ ] User speech immediately after TTS captured correctly
- [ ] No missed turns
- [ ] `stt.speech_started` arrives while in `post_tts_guard` state

---

## Scenario 7 — Refusal / consent declined

**Purpose:** Confirm agent handles refusal gracefully and ends call politely.

**ChatGPT instruction to append:**
```
Priya says "No, I'd rather not continue with this interview" when asked for consent.
She's polite but firm.
```

**What to verify:**
- [ ] Agent acknowledges refusal without arguing
- [ ] Call ends with polite close (action=`end_call_after_speaking`)
- [ ] Refusal text persisted as user turn
- [ ] Call status → `completed` cleanly

---

## Scenario 8 — Off-topic question from candidate

**Purpose:** Confirm agent stays in scope and redirects.

**ChatGPT instruction to append:**
```
After granting consent, Priya asks "What's the weather like where you are?" — a totally
off-topic question. Then she cooperates normally after the recruiter redirects.
```

**What to verify:**
- [ ] Agent does not answer the off-topic question
- [ ] Agent redirects to the screening naturally
- [ ] Off-topic text persisted as user turn
- [ ] No hallucinated answer about weather

---

## Scenario 9 — Long rambling answer

**Purpose:** Stress-test endpointing with a long, wandering answer.

**ChatGPT instruction to append:**
```
Priya gives a very long answer (30–45 seconds) to the first question — she talks about
multiple projects, pauses briefly a few times mid-story, then trails off. The recruiter
should wait patiently until she finishes.
```

**What to verify:**
- [ ] Speculative runs may fire during brief pauses — all cancelled via STT
- [ ] Only one user `CallMessage` committed for the full long answer
- [ ] No premature assistant response during the story
- [ ] Final committed text contains the full answer (not truncated)
- [ ] Deepgram `utterance_end_ms` config visible in STT URL log

---

## Scenario 10 — Candidate hangs up mid-call

**Purpose:** Confirm clean session teardown on unexpected hangup.

**ChatGPT instruction to append:**
```
Priya grants consent and answers one question, then abruptly stops the call (hang up)
without warning in the middle of the recruiter's next question.
```

**What to verify:**
- [ ] `telephony.stream_stopped reason=caller_hangup` in trace
- [ ] Deepgram WebSocket closed cleanly
- [ ] Call status → `completed` (not stuck in `in_progress`)
- [ ] `trace_summary` present in `latency_metrics` even on abrupt hangup
- [ ] No unhandled exception in logs

---

## Latency targets to check across all scenarios

Read from the structured logs after each scenario:

| Metric | Good | Acceptable | Investigate |
|---|---|---|---|
| Agent `latency_ms` (speculative) | < 1 500 ms | < 3 000 ms | > 3 000 ms |
| Agent `latency_ms` (confirmed, reused) | < 50 ms | < 200 ms | > 200 ms |
| Sarvam TTS `latency_ms` | < 800 ms | < 1 500 ms | > 1 500 ms |
| STT endpoint → first audio frame sent | < 2 500 ms | < 4 000 ms | > 4 000 ms |
| Opener latency (connect → first frame) | < 3 000 ms | < 5 000 ms | > 5 000 ms |

---

## Post-scenario DB check

After each scenario, run:

```bash
cd backend && source venv/bin/activate && python3 - <<'EOF'
import asyncio, json
from app.database import async_session_factory
from sqlalchemy import select
from app.models import Call, CallMessage

CALL_ID = "PASTE-CALL-ID-HERE"

async def check():
    async with async_session_factory() as db:
        call = await db.get(Call, CALL_ID)
        print(f"status: {call.status}")
        trace = (call.latency_metrics or {}).get("call_v2", {}).get("trace_summary", {})
        print(f"trace events: {trace.get('recent_control_events', [])[-5:]}")
        msgs = (await db.execute(
            select(CallMessage).where(CallMessage.call_id == call.id).order_by(CallMessage.created_at)
        )).scalars().all()
        for m in msgs:
            print(f"  [{m.role}] {(m.content or '')[:80]}")

asyncio.run(check())
EOF
```

---

## Scorecard template

Fill in after each scenario:

```
Scenario: ___________________
Date/time: __________________
TTS provider: Sarvam / OpenAI
STT provider: Deepgram

[ ] Opener heard and natural
[ ] Consent captured
[ ] All turns committed correctly
[ ] No premature assistant responses
[ ] No missed candidate turns
[ ] Call ended cleanly
[ ] Trace summary present in DB

Agent latency (avg): ___ ms
TTS latency (avg):   ___ ms
E2E turn latency:    ___ ms

Issues found:
-
```
