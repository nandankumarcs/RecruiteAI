# Browser Telephony Simulator — Manual Verification Checklist

Use this file to test the simulator end-to-end. Tick off each item as you go.
Mark each test: ✅ Pass · ❌ Fail · ⚠️ Partial · ⏭️ Skip

---

## Setup

**Start servers (if not already running):**
```bash
# Backend
cd backend && venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8030 --reload

# Frontend
cd frontend && VITE_API_URL=http://localhost:8030/api npm run dev -- --port 5180
```

**Verify both are up:**
```
http://localhost:8030/health    → {"status":"ok"}
http://localhost:5180           → RecruiteAI login page
```

**Login credentials:**
- Email: `dinesh.tomar@yopmail.com`
- Password: `Password@123`

**DB quick-check helper (run after any test that writes to DB):**
```sql
-- Replace <CALL_ID> with actual UUID shown in the URL
SELECT id, status, provider, duration_seconds,
       recording_url IS NOT NULL AS has_rec,
       ai_evaluation IS NOT NULL AS evaluated,
       (cost_breakdown->'costs'->>'telephony_usd')::float AS tel_cost,
       LEFT(transcript, 120) AS transcript_start
FROM calls WHERE id = '<CALL_ID>';
```
```bash
# Quick recording check
ls -lh backend/uploads/recordings/<CALL_ID>.wav
file backend/uploads/recordings/<CALL_ID>.wav
```

---

## Section 1 — Pre-flight (automated checks, run once)

| # | Check | Command / Expected | Result |
|---|---|---|---|
| P1.1 | Backend health | `curl http://localhost:8030/health` → `{"status":"ok"}` | |
| P1.2 | Worklet reachable | `curl -I http://localhost:5180/sim-audio-worklet.js` → HTTP 200 | |
| P1.3 | Browser provider registered | `grep "browser" backend/app/services/telephony.py` → line 331 | |
| P1.4 | pricing.py browser=$0 | `grep "browser" backend/app/services/pricing.py` → line 96 | |

---

## Section 2 — Happy Path (requires real mic + speakers 🎙️)

### T2.1 — Cold start, full happy path

**Steps:**
1. Log into the dashboard → open any job → find a parsed resume with questions
2. Click **START CALL** to open the resume detail modal
3. Click **START INTERVIEW CALL** → a new popup window should open automatically
4. The popup shows the iPhone-style "Incoming call" screen with Agent Smith avatar
5. Click **Accept** → grant microphone when prompted
6. **Listen**: AI should greet within ~2 s
7. Speak 2–3 natural turns (introduce yourself, answer a question)
8. Try **interrupting the AI mid-sentence** (barge-in)
9. Click **Hang up**

**Expected at each step:**
- [ ] Popup opens automatically (480×960, no toolbar) — no manual link needed
- [ ] Ringing tone plays (Marimba-style, loops every 3 s)
- [ ] Vibration on mobile / haptic trackpad
- [ ] Accept click: ringtone stops → connect tone plays (two ascending beeps)
- [ ] iPhone frame visible: Dynamic Island, titanium frame, side buttons, home indicator
- [ ] Agent Smith avatar shown (not "AI" initials)
- [ ] AI greeting heard within ~2 s (voice clear, no distortion)
- [ ] Timer ticks in real time (MM:SS)
- [ ] Indigo glow ring pulses on avatar while AI is speaking
- [ ] Your speech captured by STT (check dashboard tab: live transcript updates)
- [ ] Barge-in cuts AI audio cleanly
- [ ] Hang up: disconnect tone plays (three descending beeps)
- [ ] Screen shows "Call ended. You can close this tab."
- [ ] Tab title changes: `📲 Incoming call…` → `📞 MM:SS` → `Call ended`
- [ ] Dashboard tab: status badge → **CALL COMPLETED**

**DB check (10 s after hangup):**
- [ ] `status = 'completed'`
- [ ] `provider = 'browser'` (NOT 'exotel' — critical!)
- [ ] `duration_seconds > 0`
- [ ] `tel_cost = 0`
- [ ] `has_rec = true`
- [ ] `evaluated = true`
- [ ] `transcript_start` contains candidate's actual words

**Recording check:**
- [ ] WAV file exists in `backend/uploads/recordings/<call_id>.wav`
- [ ] `file` command: `RIFF, 16 bit, stereo 8000 Hz`
- [ ] Open recording from Call Detail page (View recording button or `/api/calls/<id>/recording`)
- [ ] Audio plays in browser — left channel = your voice, right channel = AI

**Score:**
```
T2.1: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T2.2 — Barge-in

> Run during T2.1 or a separate call

- [ ] While AI is speaking: start talking
- [ ] AI audio cuts within ~300 ms of your voice being detected
- [ ] No "tail" audio from AI after your voice starts
- [ ] AI waits for you to finish, then responds
- [ ] Backend log shows: `User started speaking (call=...), cancelling assistant output.`

```
T2.2: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T2.3 — Mute button

- [ ] During an active call, click **Mute**
  - [ ] Button turns white/inverted, label → "muted"
  - [ ] Mic icon changes to strikethrough-mic
  - [ ] Soft click sound plays
- [ ] Speak — AI should hear silence (your voice not transmitted)
- [ ] Click **Mute** again to unmute
  - [ ] Button reverts to normal
  - [ ] Your voice is transmitted again

```
T2.3: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T2.4 — Sequential calls (3 in a row, no restart)

> Start 3 separate calls one after the other with different resumes. Brief conversation each, then hang up.

- [ ] Call 1: completes correctly (`status=completed`, `provider=browser`)
- [ ] Call 2: no hang-over from Call 1 (fresh greeting, fresh transcript)
- [ ] Call 3: same
- [ ] Each has its own WAV recording
- [ ] Each `tel_cost = 0`

```
T2.4: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T2.5 — "Open Simulator ↗" from Call Detail page

1. Start a call and immediately hang up (or use any completed browser call)
2. Go to **Call History** → click the call
3. Look for the **"Browser Simulator active"** indigo banner (only shows for `queued`/`ringing`/`in_progress` calls — start a new call if needed)
4. Click **Open Simulator ↗**

- [ ] Opens a new popup window (same size, same iPhone frame)
- [ ] Shows the ringing screen for that specific call

```
T2.5: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

## Section 3 — Audio Fidelity (subjective, rate 1–5 🎙️)

| # | Test | What to listen for | Rating | Notes |
|---|---|---|---|---|
| T4.1 | AI greeting clarity | Clear, natural, no distortion or robotic artifacts | /5 | |
| T4.2 | First response latency | After you stop speaking, how long before AI starts? | fast/slow | |
| T4.3 | Sustained quality | After 3+ turns, any degradation, dropout, or drift? | /5 | |
| T4.4 | Echo / feedback | Any echo of your voice? Any AI feeding back? | /5 | |
| T4.5 | Barge-in feel | Does the cut feel natural, or is there a pop/click/tail? | /5 | |

```
Section 4 average: ___/5
Notes:
```

---

## Section 4 — Negative Paths

### T3.1 — Decline before accepting

1. Open a sim URL → see the "Incoming call" screen
2. Click **Decline**

- [ ] Screen shows "Call declined. You can close this tab."
- [ ] Decline tone plays
- [ ] No recording file created (`ls backend/uploads/recordings/<id>.wav` → file not found)
- [ ] DB: call stays in `queued` or moves to a terminal state (not `in_progress`)

```
T3.1: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T3.2 — Microphone denied

1. Open a sim URL → click **Accept**
2. In the browser microphone permission prompt → click **Block/Deny**

- [ ] Error message appears: *"Microphone permission was denied. Please allow microphone access and click Retry."*
- [ ] **Retry** button visible
- [ ] No WebSocket connection opened (call stays in `queued`)

**T3.3 — Retry after allowing mic:**
3. Go to browser URL bar → click lock icon → change mic permission to **Allow**
4. Click **Retry**

- [ ] Call proceeds normally (connect tone, AI greets, etc.)

```
T3.2: [ ] ✅ Pass  [ ] ❌ Fail
T3.3: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T3.4 — Closing the tab mid-call

1. Start a call, accept, let AI greet
2. **Close the sim tab** (Cmd-W / Ctrl-W) while call is active

- [ ] Within 5 s: DB `status = 'completed'`, `ended_at` set
- [ ] Recording saved (partial — shorter than a full call but valid WAV)
- [ ] Evaluation may or may not run (depends on transcript length)

```
T3.4: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T3.5 — Refresh during call

1. Accept a call, let AI greet
2. Hit **Refresh** (F5 / Cmd-R) on the sim tab

- [ ] Page reloads cleanly to "Call ended" or login (depending on session)
- [ ] DB: call marked `completed` (bridge finalizer ran on WS disconnect)
- [ ] No zombie process or stuck state

```
T3.5: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

## Section 5 — Security (quick API checks)

Run these from Terminal:

```bash
# P = your backend port (8030)
# T5.1 — Unauthenticated token mint → 401
curl -s http://localhost:8030/api/sim/token/<any-call-id> | jq .detail

# T5.2 — Garbage WS token → 403
# (use wscat: npm i -g wscat)
wscat -c "ws://localhost:8030/ws/browser-media/<resume-id>?token=garbage"
# Expected: connection refused / 403

# T5.3 — Token for completed call → 400
TOKEN=$(curl -s -X POST http://localhost:8030/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"dinesh.tomar@yopmail.com","password":"Password@123"}' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8030/api/sim/token/<completed-call-id>" | jq .detail
# Expected: "Call has already ended (status=completed)"
```

| # | Check | Expected | Result |
|---|---|---|---|
| T5.1 | No auth → token mint | 401 | |
| T5.2 | Garbage WS token | WS 403 | |
| T5.3 | Token for completed call | 400 "already ended" | |

---

## Section 6 — Edge Cases

### T6.1 — "Open Simulator" when popup is blocked

1. In your browser, block popups for `localhost:5180`
2. Start a call from the dashboard

- [ ] Amber warning strip appears in the modal: *"Popup was blocked by your browser."*
- [ ] **Open Simulator ↗** button appears in the warning
- [ ] Clicking it tries to open the popup again (or falls back to new tab)

```
T6.1: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T6.2 — Call page reopened after hangup

1. Complete a call (hang up)
2. Copy the sim URL and reopen it in a new tab

- [ ] Page shows error: *"Call has already ended"* (not a ringing screen)

```
T6.2: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T6.3 — Invalid call ID in URL

Open: `http://localhost:5180/sim/call/00000000-0000-0000-0000-000000000000`

- [ ] Page shows: *"Could not load simulator session."* (or 404/error message)
- [ ] No crash

```
T6.3: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

### T6.4 — Draft restore banner

1. Open a sim URL, click Accept, then immediately close the tab (don't hang up)
2. Reopen the same sim URL

- [ ] Amber banner appears: *"You have unsaved changes from a previous session."*
- [ ] **Restore** and **Discard** buttons visible

```
T6.4: [ ] ✅ Pass  [ ] ❌ Fail  (note: this is the resume editor draft, not sim — skip if not testing editor)
Notes:
```

---

## Section 7 — Recording Playback

After completing any T2.1 call:

1. Go to **Call History** → click the completed call
2. Scroll to the recording section

- [ ] Recording player appears
- [ ] Press play → audio plays in browser (no error)
- [ ] Duration looks right (≈ actual call length ± 5 s)
- [ ] Left channel (headphone): your voice audible
- [ ] Right channel (headphone): AI voice audible

```bash
# Verify stereo channels (needs ffmpeg)
WAV=backend/uploads/recordings/<call-id>.wav
ffprobe -v error -show_entries format=duration -of csv=p=0 $WAV  # should ≈ call duration
ffmpeg -y -i $WAV -filter_complex "[0:a]channelsplit=channel_layout=stereo:channels=FL[FL]" -map "[FL]" /tmp/L.wav 2>/dev/null
ffmpeg -i /tmp/L.wav -af "volumedetect" -f null - 2>&1 | grep mean_volume  # should be ~ -20 to -30 dB
```

```
T7 Recording: [ ] ✅ Pass  [ ] ❌ Fail
Notes:
```

---

## Final Score

| Section | Tests | ✅ | ❌ | ⚠️ |
|---|---|---|---|---|
| S1 Pre-flight | 4 | | | |
| S2 Happy path | 5 | | | |
| S3 Negative | 5 | | | |
| S4 Audio fidelity | 5 (subjective) | | | |
| S5 Security | 3 | | | |
| S6 Edge cases | 4 | | | |
| S7 Recording | 1 | | | |
| **Total** | **27** | | | |

**Overall rating:** `___/27 automated checks passed · Audio avg ___/5`

---

## Known Gaps / Won't Test Now

| Test | Reason | When |
|---|---|---|
| T2.6 — 5-min sustained call | Time-consuming; low value for daily dev | Before prod launch |
| T3.6 — 3G throttle | Needs DevTools network throttling | Before prod launch |
| T7.1 — Parity vs real Exotel | Requires restored credits | When credits available |
| T8.1 — 20 sequential call soak | Needs ~15 min unattended script | Weekly CI |
| S9 — Removal verification | Destructive; only run before removing sim | On removal PR |

---

## Quick DB Snippets

```sql
-- All recent browser calls (last 24 h)
SELECT id, status, provider, duration_seconds,
       recording_url IS NOT NULL AS has_rec,
       ai_evaluation IS NOT NULL AS evaluated,
       created_at
FROM calls
WHERE provider = 'browser'
  AND created_at > NOW() - INTERVAL '24 hours'
ORDER BY created_at DESC;

-- Free up stuck queued calls (if dev session crashed mid-test)
UPDATE calls SET status = 'failed'
WHERE provider = 'browser'
  AND status IN ('pending', 'queued', 'ringing', 'in_progress')
  AND created_at < NOW() - INTERVAL '2 hours';

-- Check recording files on disk
SELECT id, recording_path FROM calls WHERE provider = 'browser' AND recording_url IS NOT NULL;
```

---

## Useful URLs (with current config)

| Purpose | URL |
|---|---|
| Dashboard | http://localhost:5180/dashboard |
| Job detail (Junior AI Engineer) | http://localhost:5180/jobs/5512bba4-9ade-4891-bb84-9bd292cd2a33 |
| Backend health | http://localhost:8030/health |
| Backend API docs | http://localhost:8030/docs |
| Sim page template | `http://localhost:5180/sim/call/<call-id>` |
| Recording API | `http://localhost:8030/api/calls/<call-id>/recording` |
