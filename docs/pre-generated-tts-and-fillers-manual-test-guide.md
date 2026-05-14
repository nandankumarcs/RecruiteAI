# Pre-Generated TTS and Fillers Manual Test Guide

## Purpose

This guide is for manually testing the hybrid prompt-audio system that:

- pre-generates audio for stable prompts
- uses cached prompt audio during calls when possible
- falls back to live TTS when cached audio is unavailable or stale
- optionally plays short filler audio to mask compute gaps
- logs routing decisions and tracks call-level audio-source metrics

This guide is intentionally detailed. The goal is not just to confirm that the feature works, but to expose:

- cache misses that should have been hits
- stale asset behavior
- fallback problems
- filler overuse or underuse
- barge-in regressions
- latency regressions
- call flow differences between cached and live turns

## Scope

This guide covers:

1. Asset generation
2. Database persistence and versioning
3. Job-question trigger behavior
4. Runtime selection behavior
5. Cached playback behavior in live calls
6. Filler behavior
7. Fallback behavior
8. Observability and metrics
9. Cleanup/version purge behavior

This guide does not assume Twilio. The current production path we care about is:

```text
Exotel -> backend websocket -> Deepgram STT -> OpenAI turn generation -> Sarvam TTS fallback
```

With this feature enabled, many assistant turns should instead become:

```text
Exotel -> backend websocket -> cached PCM playback
```

## Important Current Behavior

Before testing, keep these current implementation details in mind:

- Question audio is generated asynchronously after question create/update/generate.
- The trigger is coalesced, not fire-on-every-keystroke synchronous generation.
- Cached question playback only happens when the assistant text matches the stored question text.
- If cached question text is stale relative to the current question text, runtime falls back to live TTS.
- The opener cache only applies to the static opener template. Personalized openers still fall back to live TTS.
- Filler playback is gated by threshold, cooldown, and prompt readiness.

## Files and Components Under Test

- [prompt_audio_service.py](/Users/mac/RecruiteAI/backend/app/services/prompt_audio_service.py)
- [runtime_selection_layer.py](/Users/mac/RecruiteAI/backend/app/services/runtime_selection_layer.py)
- [filler_queue_manager.py](/Users/mac/RecruiteAI/backend/app/services/filler_queue_manager.py)
- [deepgram_runtime.py](/Users/mac/RecruiteAI/backend/app/services/deepgram_runtime.py)
- [audio_generation.py](/Users/mac/RecruiteAI/backend/app/tasks/audio_generation.py)
- [generate_prompt_audio.py](/Users/mac/RecruiteAI/backend/app/management/commands/generate_prompt_audio.py)
- [purge_old_audio_versions.py](/Users/mac/RecruiteAI/backend/app/management/commands/purge_old_audio_versions.py)
- [jobs.py](/Users/mac/RecruiteAI/backend/app/routers/jobs.py)
- [observability.py](/Users/mac/RecruiteAI/backend/app/services/observability.py)

## Test Environment Prerequisites

### Required services

- PostgreSQL running
- Backend running
- Frontend running if using UI flows
- Ngrok tunnel active and `PUBLIC_URL` set correctly for live Exotel testing
- Exotel credentials configured
- Deepgram API key configured
- Sarvam API key configured

### Recommended env settings

Check these in `backend/.env`:

```env
TELEPHONY_PROVIDER=exotel
VOICE_RUNTIME=deepgram_openai
TTS_PROVIDER=sarvam
SARVAM_TTS_SPEAKER=priya
SARVAM_TTS_PACE=1.2
PIPELINE_TTS_JITTER_BUFFER_MS=200
PIPELINE_STT_ENDPOINTING_MS=500
PIPELINE_STT_UTTERANCE_END_MS=1000
STORAGE_PROVIDER=local
```

### Useful commands

Run commands from `/Users/mac/RecruiteAI/backend`.

Generate all default prompt assets:

```bash
venv/bin/python -m app.management.commands.generate_prompt_audio
```

Generate only fillers:

```bash
venv/bin/python -m app.management.commands.generate_prompt_audio --category filler
```

Generate question audio for one job:

```bash
venv/bin/python -m app.management.commands.generate_prompt_audio --job-id <JOB_ID>
```

Force-regenerate one template:

```bash
venv/bin/python -m app.management.commands.generate_prompt_audio --template-key opener_consent --force-regenerate
```

Purge old versions:

```bash
venv/bin/python -m app.management.commands.purge_old_audio_versions --retention-days 0
```

## Test Data Setup

Create at least:

1. One recruiter user
2. One job with 4-6 questions
3. One parsed resume with a valid Indian phone number
4. At least one question set with:
   - one technical question
   - one behavioral question
   - one short reprompt-eligible question
   - one question with phrasing you may later edit to create staleness

Recommended sample questions:

1. `Tell me about yourself and why this role interests you.`
2. `Can you walk me through a recent backend project you worked on?`
3. `What was the toughest production issue you debugged recently?`
4. `How do you usually approach API performance optimization?`

## Observability: What to Watch

### Backend logs

Watch for:

- `audio_source_selection`
- `audio_source=prebuilt_asset`
- `audio_source=live_tts_fallback`
- `audio_source=live_tts`
- `audio_source=filler_asset`
- cached playback errors
- stale text fallback signals
- Sarvam fallback use

### Database tables

Inspect:

- `audio_prompt_assets`
- `job_prompt_generation_runs`
- `calls`

Useful query patterns:

```sql
select template_key, category, version, status, file_path, duration_ms, created_at
from audio_prompt_assets
order by template_key, version desc;
```

```sql
select job_id, status, success_count, failure_count, started_at, completed_at
from job_prompt_generation_runs
order by created_at desc;
```

```sql
select id, provider, status, latency_metrics, cost_breakdown
from calls
order by created_at desc
limit 10;
```

## Test Matrix

Run all of these, not just the happy path.

| Area | Goal |
|---|---|
| Default template generation | Ensure opener/reprompt/clarification/closing/filler assets generate |
| Question generation | Ensure per-job question assets generate |
| Versioning | Ensure changed text/config creates new versions |
| Reuse by hash | Ensure identical content/config can be reused |
| Triggering | Ensure question create/update/generate schedules background generation |
| Runtime selection | Ensure cached vs fallback routing is correct |
| Cached playback | Ensure PCM playback works end to end |
| Filler behavior | Ensure fillers only play when appropriate |
| Fallback behavior | Ensure live TTS covers missing/stale/broken assets |
| Barge-in | Ensure candidate interruption still stops assistant audio |
| Metrics | Ensure logging and call counters update |
| Cleanup | Ensure old versions can be purged safely |

## Detailed Test Cases

### Section A: Asset Generation

#### A1. Generate all default templates

Steps:

1. Run:
   ```bash
   venv/bin/python -m app.management.commands.generate_prompt_audio
   ```
2. Check command output.
3. Query `audio_prompt_assets`.

Expected:

- command exits successfully
- assets exist for:
  - `opener_consent`
  - all `reprompt_*`
  - all `clarification_*`
  - all `closing_*`
  - all `filler_*`
- `status=ready`
- `codec=linear16`
- `sample_rate=8000`
- `pace=1.2`
- `file_path` ends in `.pcm`
- `duration_ms > 0`

Gap signals:

- `status=failed`
- missing `file_path`
- zero-length duration
- wrong speaker/language/pace

#### A2. Generate only fillers

Steps:

1. Delete or inspect existing filler assets.
2. Run:
   ```bash
   venv/bin/python -m app.management.commands.generate_prompt_audio --category filler
   ```

Expected:

- only filler assets are generated or versioned
- no unintended opener/question asset churn

#### A3. Generate question audio for a job

Steps:

1. Get one `job_id`.
2. Run:
   ```bash
   venv/bin/python -m app.management.commands.generate_prompt_audio --job-id <JOB_ID>
   ```
3. Query `audio_prompt_assets` filtered by `job_id`.

Expected:

- one `question_<QUESTION_ID>` asset per question
- `question_id` and `job_id` populated
- `category=question`

### Section B: Versioning and Reuse

#### B1. Re-run generation without changes

Steps:

1. Generate question audio for a job.
2. Run the same generation command again without changing question text.

Expected:

- no unnecessary version bump for unchanged template
- if implementation reuses by hash through a new template-version record, verify behavior is intentional and stable
- no duplicate failed assets

What to verify:

- version counts
- whether `file_hash` is reused
- whether `file_path` points to existing PCM

#### B2. Change one question text and regenerate

Steps:

1. Update exactly one question text via API or UI.
2. Wait for async generation to complete.
3. Query `audio_prompt_assets` for that `template_key`.

Expected:

- version increments by 1 for that question template
- latest version matches new text
- old version remains retained
- unchanged questions do not get new versions

#### B3. Force-regenerate a template

Steps:

1. Run:
   ```bash
   venv/bin/python -m app.management.commands.generate_prompt_audio --template-key opener_consent --force-regenerate
   ```

Expected:

- new version exists even if text matches
- latest version becomes the selected version

### Section C: Async Trigger Behavior

#### C1. Add a question through API/UI

Steps:

1. Create a question using:
   - UI, or
   - `POST /api/jobs/{job_id}/questions`
2. Watch backend logs.
3. Query `job_prompt_generation_runs`.

Expected:

- HTTP response does not wait for audio generation
- background generation run appears shortly after commit
- created question gets an audio asset

#### C2. Update a question twice quickly

Steps:

1. Update the same question text.
2. Within 1 second, update it again.
3. Watch logs and `job_prompt_generation_runs`.

Expected:

- coalesced scheduling should reduce redundant runs
- final generated audio should match the latest text
- no large pile of useless intermediate versions

This is a very important gap-finding test.

#### C3. Bulk generate questions for a job

Steps:

1. Call `POST /api/jobs/{job_id}/questions/generate`
2. Watch for async generation follow-up.
3. Query prompt assets afterward.

Expected:

- generated questions persist
- question-audio generation follows
- each generated question gets a corresponding asset

### Section D: Runtime Selection Without Live Calls

These are semi-manual verification tests using logs and DB state.

#### D1. Cached opener eligibility

Current expectation:

- static opener template can use cached audio
- personalized opener should fall back to live TTS

Steps:

1. Start a call and watch first-turn logs.
2. Observe `audio_source_selection`.

Expected:

- if assistant opener exactly matches static template: `prebuilt_asset`
- if assistant opener includes candidate name or any other personalization: `live_tts_fallback`

This is an expected current limitation, not a bug.

#### D2. Cached question routing

Steps:

1. Ensure question assets exist and match current question text exactly.
2. Start a call and let the candidate grant consent.
3. Listen for the first interview question and inspect logs.

Expected:

- question turn logs `audio_source=prebuilt_asset`
- `template_key=question_<id>`

#### D3. Stale question fallback

Steps:

1. Generate question audio.
2. Change question text.
3. Start a call before regenerated asset catches up, or intentionally break the sync.

Expected:

- runtime detects text mismatch
- `audio_source=live_tts_fallback`
- no incorrect old question audio is played

### Section E: Live Call Behavior

Use a real Exotel call to your own number.

#### E1. Happy path call

Steps:

1. Confirm `PUBLIC_URL` works through ngrok.
2. Start a call from app/API:
   - `POST /api/resumes/{resume_id}/calls/start`
3. Answer the call.
4. Say yes to proceed.
5. Answer two questions normally.

Expected:

- no disconnect on pickup
- consent turn sounds natural
- first question plays clearly
- second question also plays
- no long silent gaps where cached audio should exist

Collect:

- call ID
- Exotel provider call ID
- backend logs
- recording URL/path
- `calls.latency_metrics`

#### E2. Candidate pauses briefly mid-answer

Steps:

1. During a question, answer naturally but insert a short pause.

Expected:

- agent should not cut in too aggressively
- endpointing should still feel natural

This specifically validates that cached question playback did not regress turn-taking behavior downstream.

#### E3. Barge-in against cached audio

Steps:

1. As the cached question is playing, interrupt with speech after 1-2 seconds.

Expected:

- assistant audio stops
- candidate speech is captured
- conversation continues from candidate turn

Gap signals:

- cached audio ignores barge-in
- assistant keeps talking over candidate
- websocket gets stuck after interruption

#### E4. Long pause after a candidate answer

Steps:

1. Give an answer that may require LLM reasoning.
2. Note whether filler audio plays.

Expected:

- filler may play only when there is a real compute gap
- filler should not repeat too often
- filler should not stack awkwardly before a ready cached question

### Section F: Filler-Specific Tests

#### F1. Filler threshold below 300ms

Goal:

Confirm filler does not play for quick turns.

Steps:

1. Use a situation where the next response is cached and ready.
2. Watch logs.

Expected:

- `filler_played=false`
- no audible filler clip

#### F2. Filler cooldown

Steps:

1. Create two slow-response situations within 5 seconds.
2. Watch logs.

Expected:

- first filler may play
- second filler should usually be suppressed by cooldown

#### F3. Filler rotation

Steps:

1. Trigger filler several times across multiple calls.

Expected:

- filler keys rotate
- not always `filler_understood`

#### F4. Filler fallback safety

Steps:

1. Remove one filler PCM file from local storage after DB asset exists.
2. Trigger that filler.

Expected:

- error is logged
- main response still proceeds
- call does not break

### Section G: Failure Injection

These are critical.

#### G1. Missing cached question file

Steps:

1. Find a `question_*` asset with `status=ready`.
2. Delete its PCM file from storage.
3. Start a call that reaches that question.

Expected:

- cached playback attempt fails
- runtime logs the error
- runtime falls back to live TTS
- call continues

#### G2. Missing Sarvam key during fallback

Only do this in a safe local environment.

Steps:

1. Temporarily unset `SARVAM_API_KEY`.
2. Trigger a turn that requires live fallback.

Expected:

- clear error logs
- observe whether any secondary fallback exists
- confirm failure mode is understandable

This exposes how graceful the fallback chain really is.

#### G3. Storage path corruption

Steps:

1. Manually alter one `file_path` in DB to an invalid path.
2. Trigger playback of that asset.

Expected:

- playback error logged
- fallback to live TTS
- no call crash

### Section H: Observability and Metrics

#### H1. Verify audio-source logs

For at least one call, confirm logs show:

- opener routing
- one cached question
- one fallback turn
- optional filler turn

Each event should include:

- `audio_source`
- `template_key`
- `asset_id`
- `asset_lookup_ms`
- `filler_played`
- `filler_key`
- `main_prompt_ready_after_ms`

#### H2. Verify call-level metrics

After a mixed call, inspect `calls.latency_metrics`.

Expected counters:

- `prebuilt_turn_count`
- `filler_turn_count`
- `live_tts_turn_count`
- `live_tts_fallback_count`

Also inspect:

- `first_assistant_audio_at`
- `first_user_transcript_at`
- `stream_connected_at`

Gap signals:

- counters never move
- all turns show as live even when cache should hit
- cached calls missing first-audio markers

### Section I: Cleanup and Retention

#### I1. Purge old versions

Steps:

1. Create multiple versions for one template.
2. Run:
   ```bash
   venv/bin/python -m app.management.commands.purge_old_audio_versions --retention-days 0
   ```
3. Query DB and inspect storage.

Expected:

- latest version remains
- older versions are removed
- corresponding files are deleted

#### I2. Verify no active version is purged

Expected:

- maximum version per `template_key` remains intact
- runtime still finds a ready asset for active templates

## Recommended End-to-End Scenarios

Run these as named scenarios and record results.

### Scenario 1: Fully cached question flow

- default templates generated
- question assets generated
- candidate grants consent
- first two questions route from cache

Success criteria:

- no noticeable TTS wait for cached questions
- logs show `prebuilt_asset`

### Scenario 2: Mixed cached and fallback flow

- one question stale or missing
- others healthy

Success criteria:

- healthy questions use cache
- broken question falls back cleanly
- call remains stable

### Scenario 3: Filler stress test

- create repeated slower turns
- verify cooldown and rotation

Success criteria:

- fillers help, but do not become noisy

### Scenario 4: Interruption stress test

- interrupt opener
- interrupt cached question
- interrupt live fallback question

Success criteria:

- all three respect barge-in

## What to Record for Every Live Test

For each call, record:

- date/time
- call ID
- provider call ID
- candidate number used
- whether opener was cached or fallback
- whether question 1 was cached or fallback
- whether fillers played
- observed latency
- interruptions/barge-in outcome
- recording URL/path
- notable log lines
- pass/fail

## Known Gaps to Watch Closely

These are the most likely areas to expose issues:

1. Static opener vs personalized opener behavior
2. Exact-text matching for question cache hits
3. Asset staleness timing after fast edits
4. Filler feeling unnatural if thresholds are off
5. Barge-in while cached PCM is streaming
6. Recovery when cached files exist in DB but not on disk
7. Whether coalesced generation is aggressive enough under frequent editing

## Suggested Pass Criteria

Treat the feature as ready for broader use only if all of these hold:

1. Default templates generate reliably
2. Question assets generate reliably after question changes
3. Cached question turns clearly reduce perceived latency
4. Missing or stale assets fall back without breaking the call
5. Barge-in works on cached and live audio
6. Filler usage is sparse and helpful
7. Logs and metrics clearly explain every routing decision

## Suggested Follow-Up if Gaps Appear

If you find failures, group them into one of these buckets:

- generation bug
- cache selection bug
- playback bug
- fallback bug
- filler-tuning issue
- turn-taking/STT issue
- observability gap

That classification will make the next debugging pass much faster.
