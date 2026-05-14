# Call Quality and Recording Fix Plan

Date: 2026-05-14
Branch: `feat/exotel-implementation`

## Why this plan exists

Recent live calls showed three distinct issues:

1. Turn-taking is still too aggressive and cuts the candidate off on short pauses.
2. Cached prompt audio is working, but only a small portion of assistant turns are using it.
3. Exotel recordings are not being persisted to the `calls` table even when `Record=true`.

This plan focuses on fixing those issues without destabilizing the current Exotel + Deepgram + OpenAI + Sarvam flow.

## Current evidence

### Live call evidence

- Call `4157db0d-c250-4853-aa40-a25db007d647`
  - `prebuilt_turn_count=1`
  - `live_tts_turn_count=6`
  - `recording_url=null`
- Transcript evidence from the same call:
  - user: `... encapsulations, inheritance,`
  - assistant interrupted with: `Could you please elaborate on those five concepts in OOP?`

### Recording persistence evidence

Current Exotel outbound call setup:

- [telephony.py](/Users/mac/RecruiteAI/backend/app/services/telephony.py)
  - sends `Record=true`
  - sends `StatusCallback`
  - does **not** pass any Exotel-specific recording callback parameter
- [exotel_webhooks.py](/Users/mac/RecruiteAI/backend/app/routers/exotel_webhooks.py)
  - `exotel_status_webhook` updates `status`
  - but does **not** persist `RecordingUrl`
  - `exotel_recording_webhook` expects a separate recording callback that Exotel is not using in this call flow

### Exotel documentation evidence

Exotel’s current developer docs state that:

- when `Record=true`, `RecordingUrl` is sent to the `StatusCallback` once the call completes
- callback delivery can be delayed or fail, and customers should use the call details API as a fallback

References:

- [Exotel Make Call API](https://developer.exotel.com/api/make-a-call-api)
- [Exotel Contact Center Make Call API](https://developer.exotel.com/docs/contact-center/api-reference/make-call)

## Root causes

### 1. Recording not saved

Primary root cause:

- our Exotel integration is listening for recording data in the wrong place

Specifically:

- we expect a separate `/webhooks/exotel/recording`
- Exotel sends `RecordingUrl` to the `StatusCallback`
- our status webhook currently ignores `RecordingUrl`

Secondary risk:

- if Exotel callback delivery is delayed or dropped, we currently have no reconciliation job against Exotel call details

### 2. Candidate interruption on slight pauses

Primary root causes:

- STT end-of-turn detection is still too eager for natural phone speech pacing
- assistant follow-up generation reacts to partial content too aggressively

Likely contributing factors:

- a partial answer is treated as complete if Deepgram emits a final segment too early
- the LLM has no explicit guardrail for “do not ask a follow-up if the last user utterance looks truncated”
- very short clarification/follow-up turns are cheap to generate, so the system escalates too quickly

### 3. Cached audio underused

Primary root causes:

- only some prompts map cleanly to stable cached templates today
- clarification and follow-up responses are still mostly dynamic
- selection coverage is narrower than the actual dialogue space observed in live calls

## Fix plan

## Phase 1: Fix recording persistence

### 1.1 Persist `RecordingUrl` from Exotel status callback

Update [exotel_webhooks.py](/Users/mac/RecruiteAI/backend/app/routers/exotel_webhooks.py):

- parse `RecordingUrl` from the status callback payload
- set:
  - `call.recording_url = RecordingUrl`
  - `call.recording_path = RecordingUrl`
- if Exotel also returns duration fields in terminal payload, map them when present

Why:

- this is the documented location for recording metadata in the current Exotel call flow

### 1.2 Keep `/webhooks/exotel/recording`, but treat it as optional

Do not remove the existing endpoint yet.

Instead:

- keep it as a compatibility path
- make status callback the primary persistence path
- log whether recording metadata came from `status_callback` or `recording_webhook`

### 1.3 Add fallback reconciliation using Exotel call details

Implement a recovery path for calls that finish without `recording_url`:

- trigger a short delayed background fetch for completed Exotel calls missing recording metadata
- call Exotel call details API using `provider_call_id`
- if `RecordingUrl` is present there, backfill:
  - `recording_url`
  - `recording_path`
  - duration if available

Why:

- Exotel docs explicitly warn that callback delivery can fail or be delayed

### 1.4 Add tests

Add or update tests for:

- status callback with `RecordingUrl`
- status callback without `RecordingUrl`
- separate recording webhook compatibility
- reconciliation backfill when callback misses recording data

## Phase 2: Reduce interruption and improve turn-taking

### 2.1 Retune STT end-of-turn behavior

Adjust and test:

- `PIPELINE_STT_ENDPOINTING_MS`
- `PIPELINE_STT_UTTERANCE_END_MS`

Recommended starting point:

- endpointing: `650-800ms`
- utterance_end: `1200-1500ms`

Approach:

- test in small increments
- prioritize natural candidate pacing over absolute fastest response

### 2.2 Add “possibly incomplete utterance” guard

Before generating the next assistant turn, detect whether the user utterance looks incomplete.

Candidate heuristics:

- ends with conjunction or comma-like continuation
- very short fragment after a long pause
- semantic fragment such as:
  - `and polymorphism`
  - `okay so in python for`
  - `there are five concepts`

Behavior:

- if likely incomplete, wait briefly for continuation instead of prompting immediately

### 2.3 Add interruption-safe follow-up policy

Strengthen the LLM instructions so it does not overreact to partial answers.

New policy rules:

- do not ask a follow-up if the candidate likely has not finished speaking
- prefer acknowledgment plus wait over immediate probing
- do not ask layered follow-ups on top of a partially answered question
- only advance to the next question after a reasonably complete response or explicit user intent

### 2.4 Add transcript-level regression tests

Add tests for cases like:

- user pauses mid-list
- user restarts sentence
- user says `one second`, `wait`, `let me think`
- user says `next question`
- user says `bye`

## Phase 3: Increase prebuilt prompt coverage

### 3.1 Expand cached template set

Add stable cached assets for common recruiter turns observed in live calls:

- `Could you please elaborate on that?`
- `Can you explain that in more detail?`
- `Could you give an example?`
- `Let’s move to the next question.`
- `Thanks, let’s continue.`

### 3.2 Normalize dynamic outputs into known cached variants

When the LLM produces semantically equivalent text, map it to a canonical cached template.

Examples:

- `Can you elaborate on that?`
- `Could you explain that more?`
- `Tell me a bit more about that.`

All can route to one cached reprompt asset.

### 3.3 Prefer cached questions and cached reprompts before live TTS

Tighten `RuntimeSelectionLayer` so it:

- aggressively matches known question text
- aggressively matches known clarification / reprompt intents
- falls back to live TTS only when the response is genuinely dynamic

### 3.4 Add coverage metrics

Track per-call ratios:

- `prebuilt_turn_count`
- `live_tts_turn_count`
- `filler_turn_count`
- derived cached coverage percentage

Goal:

- raise prebuilt coverage from current low single-digit turns to a majority of scripted recruiter turns

## Phase 4: Validate filler behavior deliberately

### 4.1 Force a controlled compute gap

Create a controlled test where:

- main response intentionally takes longer
- filler is expected to play

Validate:

- filler plays only once
- no overlap with main prompt
- main prompt follows naturally

### 4.2 Tune filler threshold

Current filler triggering should be validated against real call feel.

Tune:

- minimum estimated latency threshold
- cooldown interval
- skip behavior when main prompt becomes ready early

### 4.3 Add per-turn observability

Structured logs should clearly capture:

- selected audio source
- selected template key
- whether filler was played
- whether cached playback failed and fell back to live TTS

## Implementation order

Recommended order:

1. Fix Exotel recording persistence in status callback
2. Add recording reconciliation fallback
3. Retune STT endpointing and utterance end
4. Add incomplete-utterance guard
5. Tighten follow-up policy
6. Expand cached reprompt / clarification templates
7. Run controlled filler validation

## Definition of done

This fix pass is complete when:

- completed Exotel calls reliably persist `recording_url`
- recording playback endpoint works for new Exotel calls
- candidate answers are no longer cut off on short pauses in repeated live tests
- cached prompt coverage is measurably higher than current baseline
- filler playback is proven in at least one controlled live or semi-live test

## Manual validation checklist

- Place a live Exotel call and confirm `recording_url` is populated after completion
- Open the call recording endpoint and confirm audio playback succeeds
- Speak with short pauses mid-answer and confirm the agent does not interrupt
- Ask for `next question` and confirm the next scripted question is fast and stable
- Use `bye` and confirm the cached closer or expected closer behavior is correct
- Run one forced-gap test and confirm filler usage is observable and natural
