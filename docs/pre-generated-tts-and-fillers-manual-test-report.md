# Pre-Generated TTS and Fillers Manual Test Report

Date: 2026-05-14  
Tester: Codex  
Environment:

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- Public URL: `https://consistent-contessa-uncondemnable.ngrok-free.dev`
- Telephony: Exotel
- STT: Deepgram
- TTS fallback: Sarvam
- Test number used: `+917903229509`

## Overall Result

Result: `PARTIAL PASS / REMAINING GAPS`

The original manual run failed because the cached-audio generation path was broken. I fixed that blocker during the test session and reran the core generation and live-call checks. Cached prompt generation now works, and at least one real Exotel call turn was served from a pre-generated asset. The feature is no longer fully blocked, but the browser login issue remains, and filler behavior is still not conclusively validated in a controlled way.

## Major Findings

### 1. P0: Frontend login in the headed in-app browser hangs after submit

Severity: `P0 for browser-driven manual testing`, `P1 for product usability if reproducible outside the in-app browser`

Observed behavior:

- I filled the login form in the headed browser.
- The button changed to `Authenticating...`.
- The page stayed stuck on the login screen.
- Backend logs showed only `OPTIONS /api/auth/login` from the browser path, not the actual `POST /api/auth/login`.

Evidence:

- Browser snapshot after submit showed:
  - email and password populated
  - button disabled with text `Authenticating...`
- Backend log showed:
  - `OPTIONS /api/auth/login HTTP/1.1 200 OK`
  - no corresponding browser-origin `POST /api/auth/login`
- Direct curl to the same endpoint worked immediately and returned tokens.

Interpretation:

- Credentials are valid.
- Backend auth endpoint is healthy.
- The request is getting stuck on the browser/frontend path before the actual POST reaches the backend.

Impact:

- Prevented full browser-led authenticated testing through the UI.
- Forced the rest of the manual test flow to continue through API/backend methods.

### 2. Fixed During Test: Prompt audio generation was broken for all templates and questions

Severity: `P0`

Original observed behavior:

- Running the generation command for default templates produced `0 success / 14 failure`.
- Updating a job question triggered a generation run, but it completed with `0 success / 11 failure`.
- All generated `audio_prompt_assets` rows ended in `status=failed`.

Root cause found:

- In [prompt_audio_service.py](/Users/mac/RecruiteAI/backend/app/services/prompt_audio_service.py:598), `_synthesize_and_persist` is indented under `get_prompt_audio_service()` instead of being a class method on `PromptAudioService`.
- `ensure_prompt_audio()` calls `self._synthesize_and_persist(...)`, but that method does not exist on the instance.

Observed error:

```text
Audio generation failed for opener_consent: 'PromptAudioService' object has no attribute '_synthesize_and_persist'
```

Fix applied during testing:

- moved `_synthesize_and_persist` back onto `PromptAudioService` as a real instance method

Outcome after fix:

- default template generation succeeded
- question generation for the live job produced `ready` assets
- cached audio was exercised in a real call

Original impact before fix:

- No opener cache
- No reprompt cache
- No clarification cache
- No closing cache
- No filler cache
- No question cache

This means the new feature is effectively non-functional in the current build.

## What I Tested

## A. Environment / Setup

Status: `PASS`

Verified:

- backend starts and `/health` responds
- frontend dev server is running
- ngrok tunnel is live
- Exotel is able to reach backend webhooks

## B. Default template generation

Status: `PASS after fix`

Command:

```bash
venv/bin/python -m app.management.commands.generate_prompt_audio --category opener,reprompt,clarification,closing,filler
```

Observed before fix:

- command ran
- all 14 assets inserted
- all 14 assets ended in `failed`
- all durations stayed `0`

Observed after fix:

- command completed with `generated=14`
- `success_count=14`
- `failure_count=0`
- default template assets became `ready`

Database evidence after fix:

- `opener_consent|ready|2|10706`
- `reprompt_elaborate|ready|2|2020`
- `clarification_repeat|ready|2|1626`
- `closing_thank_you|ready|2|1094`
- filler assets became ready, including:
  - `filler_understood|ready|2|725`
  - `filler_got_it|ready|2|1303`
  - `filler_okay|ready|2|474`
  - `filler_thanks|ready|2|574`
  - `filler_sure|ready|2|443`

## C. Question audio generation by trigger

Status: `PASS after fix`

Test:

- updated question `6ce44f8f-7504-4d57-a4e0-6dfd2cbfed5f`

Observed before fix:

- trigger wiring works
- a `job_prompt_generation_runs` row was created
- run completed quickly
- result was `success_count=0`, `failure_count=11`

Observed after fix:

- question generation for job `64258aff-8efe-4f66-80d4-ca5ef25638fb` produced `ready` question assets
- examples:
  - `question_6ce44f8f-7504-4d57-a4e0-6dfd2cbfed5f|ready|2|4136`
  - `question_bb854eca-420f-49b8-935d-acc045de5b43|ready|2|5455`
  - `question_f5d03d7d-5a18-4c82-96b4-643f8dc1c26e|ready|2|6447`

Interpretation:

- scheduling/orchestration path works
- synthesis path now works for question assets

## D. Versioning / retention

Status: `BLOCKED`

Reason:

- since generation never produces `ready` assets, versioning and cleanup behavior cannot be meaningfully validated

## E. Runtime selection / cache hits

Status: `PARTIAL PASS`

Observed after fix in live call:

- call ID: `c0e65210-35c3-431e-99b0-9883b6ddfe3d`
- `prebuilt_turn_count=1`
- `live_tts_turn_count=6`

Interpretation:

- runtime did use cached audio for at least one assistant turn
- runtime still used live TTS for several dynamic turns in the same call
- this is expected for the current hybrid design, but we still need tighter instrumentation to attribute each exact turn source without relying only on counters

## F. Live call in degraded fallback-only mode

Status: `PASS`

Call placed:

- Call ID: `ba482b83-aeea-4e73-bb5e-ef541834fecc`
- Exotel provider call ID: `ad99f2ad2e32097b8a61c4cb30681a5e`

Observed:

- Exotel reached backend
- websocket connected
- call answered
- opener was spoken
- user said `Yes.`
- assistant followed with:
  - `Tell me about yourself and why this role interests you.`

Database evidence:

- messages captured:
  1. assistant opener
  2. user consent
  3. assistant first question

Latency metrics:

```json
{
  "call_requested_at": "2026-05-14T06:16:41.818339+00:00",
  "call_answered_at": "2026-05-14T06:16:57.825159+00:00",
  "stream_connected_at": "2026-05-14T06:16:57.827685+00:00",
  "live_tts_turn_count": 2,
  "last_main_prompt_ready_after_ms": 800,
  "first_assistant_audio_at": "2026-05-14T06:16:58.398288+00:00",
  "first_user_transcript_at": "2026-05-14T06:17:07.423140+00:00"
}
```

Key interpretation:

- `live_tts_turn_count=2`
- there were no cached turns
- no filler turns were recorded

So the call path itself functions both:

- in fallback live-TTS mode
- and now, after the fix, with at least one confirmed cached turn in the real Exotel path

## G. Filler playback

Status: `PARTIAL / NOT YET CONCLUSIVE`

Observed:

- filler assets now generate successfully and are `ready`
- live call metrics reviewed so far do not yet show a conclusive filler turn for this session

Remaining gap:

- we still need one intentionally controlled call where we create a compute gap and verify:
  - `filler_turn_count > 0`
  - filler audio is audibly played
  - main prompt follows correctly without awkward overlap

## H. Cached playback / stale asset fallback

Status: `PARTIAL`

Observed:

- ready cached assets now exist
- cached routing is confirmed at least once in production flow

Still not fully exercised:

- stale asset handling
- forced fallback when a cached asset is missing/corrupt
- cleanup and retention behavior after multiple successful versions

## I. Observability

Status: `PARTIAL PASS`

Verified:

- call-level latency metrics updated
- live TTS counters updated
- generation failure errors were logged clearly

Verified:

- call-level counters now include `prebuilt_turn_count=1` on the live call

Not yet conclusively verified:

- exact per-turn `prebuilt_asset` structured log extraction from noisy raw media logs
- `filler_asset` logging in a working filler turn

## Rerun Summary After Fix

Core recovery steps completed during this session:

1. Fixed [prompt_audio_service.py](/Users/mac/RecruiteAI/backend/app/services/prompt_audio_service.py) so `_synthesize_and_persist` is a real `PromptAudioService` method.
2. Regenerated default template assets successfully.
3. Regenerated question assets for the live test job successfully.
4. Restarted the backend.
5. Placed a fresh Exotel call to `+917903229509`.
6. Confirmed a hybrid real-call result:
   - `prebuilt_turn_count=1`
   - `live_tts_turn_count=6`

Live call messages captured:

1. assistant: `Hi Shreyansh, this is RecruiteAI calling about your application. Is now a good time for a short screening?`
2. user: `Sure.`
3. assistant: `Tell me about yourself and why this role interests you.`
4. user: `What do you want to know?`
5. assistant: `Tell me about yourself and why this role interests you.`
6. user: `Can you explain a bit more?`
7. assistant: `Can you share your background and what excites you about this role?`
8. user: `Next question.`
9. assistant: `Can you explain the basic concepts of Object-Oriented Programming (OOP) and how they apply to Python?`
10. user: `Next question.`
11. assistant: `Describe a project where you had to learn a new technology or framework.`

Interpretation:

- at least one of the stable scripted turns was served from cache
- dynamic clarification and follow-up paths are still using live TTS, which matches the intended hybrid architecture
- filler behavior remains the main unproven runtime slice

## Important Database Evidence

### Failed default template assets

All tested default assets existed with:

- `status=failed`
- `duration_ms=0`

Examples:

- `opener_consent`
- `reprompt_elaborate`
- `reprompt_example`
- `reprompt_clarify`
- `clarification_repeat`
- `clarification_more`
- `closing_thank_you`
- `closing_next_steps`
- `filler_understood`
- `filler_got_it`
- `filler_okay`
- `filler_thanks`
- `filler_sure`
- `filler_one_moment`

### Job generation run

For job `64258aff-8efe-4f66-80d4-ca5ef25638fb`:

- `status=completed`
- `success_count=0`
- `failure_count=11`

## Final Assessment

### What works

- backend boots
- frontend renders
- Exotel call path works
- Deepgram STT works
- OpenAI turn generation works
- Sarvam live TTS fallback works
- question update trigger fires background generation runs

### What is broken

- headed browser login path hangs after submit
- all prompt audio generation fails
- all cached prompt categories are unusable
- filler system is unusable
- cache-hit runtime behavior cannot be validated because there are no ready assets

## Recommended Next Action

Fix this first:

- move `_synthesize_and_persist` back onto the `PromptAudioService` class in [prompt_audio_service.py](/Users/mac/RecruiteAI/backend/app/services/prompt_audio_service.py:598)

Then rerun this same manual guide in this order:

1. default template generation
2. question generation trigger
3. ready-asset DB verification
4. live call verifying `prebuilt_asset`
5. filler tests
6. stale asset fallback tests

Secondary follow-up:

- debug why the headed in-app browser login path stalls after preflight even though direct API login succeeds
