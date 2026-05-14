# RecruiteAI — Pre-Generated TTS and Filler Audio Implementation Plan

## Purpose

This document defines a practical implementation plan for reducing live-call latency by pre-generating audio for stable recruiter prompts and optionally using short prebuilt filler utterances while dynamic work is still running.

The plan is designed for the current architecture in this repository:

```text
Exotel
 -> backend websocket/media runtime
 -> Deepgram STT
 -> OpenAI turn generation
 -> Sarvam TTS
 -> Exotel audio playback
```

The goal is not to remove all dynamic behavior. The goal is to move the most repeated, latency-sensitive prompts off the live TTS path while keeping dynamic fallback available.

---

## Problem Statement

The current live call system has two recurring issues:

1. The caller hears noticeable gaps before agent speech.
2. Longer prompts can take too long to synthesize and play, especially at the start of the call or after a user answer.

We have already improved the system by:

- switching TTS to Sarvam
- adding streaming playback
- adding a jitter buffer
- shortening many generated prompts

Those improvements helped, but they do not fully eliminate latency because the system still generates TTS live for nearly every turn.

There is a simpler opportunity:

- many spoken recruiter turns are stable
- the interview questions are pre-selected
- some acknowledgements are reusable
- many reprompts can be standardized without harming the product

That makes a hybrid architecture viable.

---

## Goals

### Primary goals

1. Reduce time from decision to audible agent speech.
2. Preserve Indian-accent English output quality.
3. Make the first few call turns feel fast and reliable.
4. Reduce dependence on live Sarvam generation for repeated prompts.
5. Keep the backend in control of call flow and question sequencing.

### Secondary goals

1. Improve consistency of recruiter wording.
2. Reduce repeated live TTS cost for common prompts.
3. Create a reusable prompt audio library for future voice-agent work.

### Non-goals

1. We are not removing Deepgram STT in this workstream.
2. We are not removing OpenAI reasoning in this workstream.
3. We are not making the call completely scripted with zero dynamic turns.
4. We are not redesigning the entire recruiter conversation model in one pass.

---

## Recommendation

Implement a hybrid audio strategy:

1. Pre-generate audio for all stable prompts.
2. Use optional short filler clips to hide compute gaps.
3. Keep live Sarvam TTS as a fallback for dynamic turns.
4. Route runtime behavior through a prompt classification layer instead of sending every response directly to live TTS.

This should cover most high-frequency call turns without losing flexibility.

---

## Scope Of Pre-Generated Audio

### Phase 1 candidates

These are the highest-value prompts to pre-generate first:

1. Consent opener
2. Interview questions tied to a job
3. Standard reprompts
4. Standard clarification prompts
5. Standard closers

### Phase 2 candidates

These are optional but useful:

1. Follow-up prompts such as:
   - "Can you tell me more?"
   - "Can you elaborate on that?"
   - "Can you give me an example?"
2. Off-topic redirects
3. Retry prompts for noisy input
4. Common acknowledgement fillers

### Keep dynamic for now

These should remain live-generated initially:

1. Highly customized follow-up questions
2. Freeform clarification responses
3. Anything that directly incorporates novel transcript content
4. Rare fallback/recovery lines not worth maintaining as assets

---

## Prompt Taxonomy

Introduce a stable prompt taxonomy so the runtime can choose from a finite set of known spoken intents.

Suggested categories:

```text
opener
ack_filler
question
reprompt
clarification
off_topic_redirect
closing
fallback_dynamic
```

Suggested properties on a prompt template:

- `template_key`
- `category`
- `text`
- `speaker`
- `provider`
- `language_code`
- `pace`
- `sample_rate`
- `codec`
- `version`
- `job_scoped`
- `active`

For job-specific questions, include:

- `job_id`
- `question_id`
- `order_index`

---

## Architecture Changes

## 1. Add A Prompt Audio Library

Create a new storage-backed library of generated audio assets.

Possible implementation paths:

1. Database-backed metadata + file storage on disk/S3
2. Pure filesystem index plus DB reference

Recommended direction:

- DB metadata
- audio files stored using the existing storage abstraction

Suggested DB table:

```text
audio_prompt_assets
```

Suggested fields:

- `id`
- `template_key`
- `category`
- `text`
- `job_id` nullable
- `question_id` nullable
- `provider` default `sarvam`
- `speaker` default `priya`
- `language_code` default `en-IN`
- `sample_rate`
- `codec`
- `pace`
- `file_path`
- `file_hash`
- `duration_ms`
- `version`
- `status` such as `pending`, `ready`, `failed`
- `last_generated_at`
- `created_at`
- `updated_at`

The `file_hash` should be derived from the normalized input text plus synthesis configuration so regeneration can be made deterministic.

---

## 2. Add Audio Asset Generation Service

Create a dedicated backend service to synthesize and persist prompt audio.

Suggested file:

- `backend/app/services/prompt_audio_service.py`

Responsibilities:

1. Normalize prompt text.
2. Compute cache key or hash.
3. Look up existing ready asset.
4. Generate audio through Sarvam if missing or stale.
5. Persist audio file and metadata.
6. Return an object the runtime can stream immediately.

Suggested entrypoints:

- `ensure_prompt_audio(...)`
- `ensure_question_audio_for_job(...)`
- `ensure_default_fillers(...)`
- `get_ready_audio_asset(...)`

---

## 3. Add Job-Level Generation Trigger

When interview questions are created or updated for a job, generate the associated question audio.

Possible trigger points:

1. During question generation workflow
2. During manual question editing
3. During explicit "publish job questions" action

Recommended first implementation:

- trigger generation when job questions are finalized or saved
- do generation asynchronously in the backend after DB commit

This avoids blocking the UI request too long.

If job setup time becomes too slow, move to a background worker pattern later.

---

## 4. Add Default Filler Library

Create a small curated filler inventory rather than generating fillers ad hoc.

Recommended starter set:

```text
understood
got_it
okay
thanks
sure
one_moment
```

Guidelines:

1. Each filler should be one short phrase only.
2. Avoid overusing them.
3. Avoid chatty or unnatural fillers.
4. Keep them reusable across jobs.

These should be generated once and reused globally rather than per job.

---

## 5. Add Runtime Prompt Selection Layer

The current runtime sends assistant text almost directly into TTS.

We should insert a selection layer before live synthesis:

```text
assistant text / conversation state
 -> classify turn
 -> if matching pre-generated template exists, play cached audio
 -> else if filler appropriate, play filler then continue
 -> else use live Sarvam TTS fallback
```

Suggested new runtime helper methods:

- `classify_assistant_turn(...)`
- `resolve_prebuilt_prompt(...)`
- `should_play_filler(...)`
- `play_audio_asset(...)`
- `play_or_synthesize(...)`

This logic can live in:

- [backend/app/services/deepgram_runtime.py](/Users/mac/RecruiteAI/backend/app/services/deepgram_runtime.py)

but the selection logic itself should be factored into a helper/service so the runtime file does not become even more overloaded.

---

## 6. Add Queueing Rules For Fillers

Fillers are useful only if they do not create awkward double speech.

Required runtime rules:

1. Skip filler if main prompt is already ready quickly.
2. Only play filler if there is likely to be a real gap.
3. Never overlap filler and main prompt.
4. If main prompt becomes ready while filler is still playing, wait until filler ends, then continue.
5. If user barges in, filler playback must be interruptible the same way as normal TTS playback.

Suggested first rule:

- only play a filler if predicted response latency exceeds `250ms` to `400ms`

This can start as a simple fixed threshold and become smarter later.

---

## 7. Preserve Live TTS Fallback

Do not remove live Sarvam TTS.

Fallback is still required for:

1. unusual dynamic turns
2. missing assets
3. generation failures
4. future product experiments

The runtime should log whether a turn used:

- `prebuilt_asset`
- `filler_asset`
- `live_tts`
- `live_tts_fallback`

This is essential for debugging and performance measurement.

---

## Data Model Plan

## Tables

### `audio_prompt_assets`

Stores all reusable synthesized prompt assets.

### Optional `job_prompt_generation_runs`

Useful if we want explicit progress reporting during bulk generation.

Suggested fields:

- `id`
- `job_id`
- `status`
- `started_at`
- `completed_at`
- `success_count`
- `failure_count`
- `error_summary`

This is optional for phase 1. It becomes more useful if generation is moved into a queue/worker system.

---

## Storage Plan

Use the repo’s existing storage abstraction if possible.

Relevant code to inspect during implementation:

- [backend/app/services/storage.py](/Users/mac/RecruiteAI/backend/app/services/storage.py)

Suggested path pattern:

```text
prompt-audio/{category}/{version}/{hash}.wav
```

Or:

```text
prompt-audio/jobs/{job_id}/{question_id}/{version}.wav
```

Prefer a hash-backed path if we want strong deduplication across identical prompts.

---

## Generation Strategy

## Questions

When job questions are finalized:

1. iterate all questions
2. generate prompt text
3. synthesize audio with Sarvam
4. persist asset metadata
5. mark ready

## Fillers

Generate once during:

1. migration/setup task
2. management command
3. startup check with explicit guard

Recommended:

- use a one-off management command or seed script
- avoid doing this implicitly on every app startup

## Opener

Generate a standard opener template, but keep the first name dynamic if needed.

Two viable approaches:

1. Stable non-personalized opener:
   - fastest and easiest to cache
2. Partially personalized opener:
   - more natural
   - requires either dynamic insertion or per-name live TTS

Recommendation:

- phase 1 uses a stable opener template without job title expansion
- keep first-name personalization only if it still fits latency and call-length constraints

---

## Runtime Behavior Plan

## High-value runtime flow

### Opener

1. Resolve prebuilt opener asset.
2. Play cached opener audio.
3. Avoid live TTS unless opener asset missing.

### Question turn

1. Determine next interview question from backend flow.
2. Resolve cached question audio by `question_id`.
3. Play question audio immediately.

### Clarification/reprompt turn

1. Map candidate intent to a standard reprompt template when possible.
2. Use cached reprompt audio.
3. Fall back to live Sarvam only if response is genuinely dynamic.

### Filler

1. Candidate finishes speaking.
2. If next turn is not ready yet and expected latency exceeds threshold, play cached filler.
3. Then play question or follow-up.

---

## Classification Strategy

We do not need perfect semantic classification at first.

Start with deterministic routing based on state and template matching:

1. If consent not yet granted:
   - use opener/consent template
2. If next turn is exactly a known question:
   - use question asset
3. If assistant text matches one of a small set of standard reprompts:
   - use reprompt asset
4. If assistant text contains mapped clarification pattern:
   - use clarification asset
5. Else:
   - live TTS fallback

This keeps phase 1 implementable and low-risk.

---

## UX And Product Rules

1. Fillers should never become verbal spam.
2. The first recruiter impression should still feel human and polite.
3. Question wording should stay stable once audio is generated.
4. If recruiter text changes, associated audio asset version must change too.
5. The call should feel faster without sounding robotic or over-optimized.

---

## Implementation Phases

## Phase 1 — Static Question Audio

### Scope

1. Add `audio_prompt_assets` table.
2. Add prompt audio generation service.
3. Generate and store audio for interview questions.
4. Add runtime path to play question assets instead of live TTS when available.

### Expected outcome

The most common interview turns become near-instant from a TTS perspective.

### Verification

1. Create/update a job with questions.
2. Confirm assets exist for all questions.
3. Place a live call.
4. Verify question turns use cached audio, not live Sarvam synthesis.

---

## Phase 2 — Opener, Reprompts, Closers

### Scope

1. Add standard opener asset.
2. Add standard reprompt asset set.
3. Add closing asset set.
4. Route matching runtime turns to cached audio.

### Expected outcome

The first impression and common recovery turns become significantly faster and more consistent.

### Verification

1. Verify opener playback path in live call.
2. Verify at least two reprompt scenarios.
3. Verify closing playback path.

---

## Phase 3 — Filler Audio

### Scope

1. Add filler library and generation command.
2. Add runtime threshold logic for filler usage.
3. Add barge-in compatibility for fillers.

### Expected outcome

Noticeable silence is masked without making the call feel scripted.

### Verification

1. Simulate a slow dynamic response.
2. Confirm filler plays only when threshold exceeded.
3. Confirm filler is skipped when main response is already ready.
4. Confirm filler can be interrupted.

---

## Phase 4 — Dynamic Prompt Mapping

### Scope

1. Expand routing from exact template match to controlled intent mapping.
2. Reduce the number of live-TTS turns further.
3. Add observability for routing reasons.

### Expected outcome

More turns use cached audio without overcomplicating the dialogue system.

---

## Observability Plan

Add structured logs and metrics for:

- `audio_source=prebuilt`
- `audio_source=filler`
- `audio_source=live_tts`
- `template_key`
- `asset_id`
- `asset_lookup_ms`
- `filler_played=true/false`
- `filler_key`
- `main_prompt_ready_after_ms`

Also capture call-level counts:

- number of prebuilt turns
- number of filler turns
- number of live TTS turns
- average time to first agent audio
- average user-stop to next-agent-audio

This is necessary to prove the architecture is helping.

---

## Testing Plan

## Unit tests

1. prompt text normalization
2. asset hash generation
3. asset lookup behavior
4. template routing
5. filler threshold logic

## Integration tests

1. question save triggers audio generation
2. missing asset falls back to live TTS
3. cached asset is streamed correctly through Exotel path

## Manual tests

1. create a job
2. generate questions
3. confirm assets ready
4. place a call
5. verify opener
6. verify first question
7. verify reprompt behavior
8. verify dynamic fallback still works

## Real call checks

Measure:

1. answer to first audio
2. candidate answer end to next question start
3. number of silence gaps longer than `500ms`
4. agent interruption behavior

---

## Risks

1. Cached prompts may feel repetitive if there are too few variants.
2. Fillers can become annoying if used too often.
3. Asset generation can drift from actual prompt text if versioning is weak.
4. Dynamic fallback behavior may become inconsistent if routing rules are not explicit.
5. Personalized openers can reintroduce latency if not handled carefully.

---

## Suggested First Build Order

1. Add asset table and metadata model.
2. Add prompt audio generation service.
3. Add command to generate default fillers and global templates.
4. Add question-audio generation on question save/finalization.
5. Add runtime asset playback helper.
6. Route question turns to cached audio.
7. Route opener/reprompts/closers.
8. Add optional filler logic.

This order gives the biggest latency benefit early without forcing a full runtime rewrite first.

---

## Final Recommendation

This idea is highly viable and probably one of the best practical latency improvements available for the current system.

The strongest implementation is not:

- “pre-generate all possible speech”

The strongest implementation is:

- pre-generate the stable majority of recruiter turns
- keep a small reusable filler library
- preserve live Sarvam TTS only for truly dynamic turns

That gives us lower latency, more consistent voice behavior, and fewer failure points, while still keeping the call flow intelligent enough to handle real conversations.
