# RecruiteAI — Cost Optimization Incremental Implementation Plan

## Purpose

This document defines the phase-wise implementation and verification plan for reducing per-call cost while preserving or improving product quality and latency.

This plan is written so it can be used in a fresh chat session without relying on prior conversational context.

---

## Goals

### Primary goals

1. Reduce per-interview call cost as quickly as possible.
2. Preserve or improve live call quality.
3. Preserve or improve end-to-end latency.
4. Keep the recruiter experience and backend conversation logic under our control.

### Non-goals

1. We are **not** migrating to Gemini Live at this stage.
2. We are **not** replacing OpenAI as the core reasoning layer.
3. We are **not** optimizing for migration safety or backward compatibility with a production rollout, because this project is still in development.

---

## Final Strategic Decisions

These decisions are assumed throughout the plan:

1. **OpenAI stays in the system** for reasoning and conversation intelligence.
2. **Plivo replaces or supplements Twilio** as the telephony provider, using an abstraction layer that supports both.
3. **Deepgram will be introduced into the voice pipeline** where it improves cost and/or quality.
4. The backend remains the **source of truth** for:
   - consent handling
   - off-topic handling
   - interview flow control
   - termination behavior
   - transcript persistence
   - evaluation
5. The implementation should be **incremental**, with clear verification gates at the end of each phase.

---

## Current Baseline Architecture

Current live architecture:

```text
Recruiter Dashboard
  -> Backend API
  -> TelephonyService (currently Twilio)
  -> Twilio voice webhook / media stream
  -> FastAPI realtime bridge
  -> OpenAI Realtime API
```

Additional non-realtime AI workloads:

1. Resume parsing
2. Interview question generation
3. Call evaluation

Current known baseline characteristics:

1. Realtime calls already work end to end.
2. Consent flow is now enforced more strictly than before.
3. User transcript capture works.
4. Recording capture works.
5. There are still some quality issues in live turn-taking and UI websocket behavior.

---

## Target Architecture

Target architecture after all phases in this plan:

```text
Recruiter Dashboard
  -> Backend API
  -> Telephony abstraction
      -> Twilio provider
      -> Plivo provider
  -> Voice runtime abstraction
      -> OpenAI Realtime bridge
      -> Deepgram-enhanced voice pipeline
  -> Backend conversation/state machine
  -> Transcript persistence
  -> Evaluation pipeline
```

Planned target voice stack direction:

```text
Plivo PSTN call
  -> Plivo bidirectional stream
  -> FastAPI backend voice orchestrator
  -> Deepgram STT
  -> OpenAI text reasoning
  -> Deepgram TTS
  -> Plivo stream back to caller
```

Important:

We should **not** rewrite the whole live stack at once. We should progressively introduce provider and pipeline changes behind stable interfaces.

---

## Architecture Principles

1. Keep telephony and voice runtime separate abstractions.
2. Never mix provider-specific logic into core conversation logic unless unavoidable.
3. The backend, not the provider, owns:
   - consent gating
   - interview progression
   - interruption policy
   - graceful hangup
   - transcript assembly
4. Verification must happen at three levels:
   - unit/integration tests
   - local browser/user-flow verification
   - real phone-call verification
5. No phase is complete until its verification checklist passes.

---

## Proposed New Abstractions

These abstractions should exist by the end of the work:

### 1. Telephony provider abstraction

Suggested interface:

- `start_outbound_call(...)`
- `end_call(...)`
- `play_and_hangup(...)`
- `validate_webhook_signature(...)` if provider-specific auth is added later
- provider-specific answer XML/TwiML generation helpers if needed

Providers:

- `TwilioTelephonyProvider`
- `PlivoTelephonyProvider`

### 2. Voice runtime abstraction

Suggested interface:

- `handle_stream(websocket, resume_id, provider_context)`
- `send_audio_chunk(...)`
- `receive_transcript_event(...)`
- `interrupt_response(...)`
- `close_session(...)`

Runtimes:

- `OpenAIRealtimeRuntime`
- `DeepgramOpenAIRuntime` or equivalent orchestrated pipeline runtime

### 3. Conversation orchestrator / state machine

Owns:

- consent state
- interview state
- off-topic handling
- end-intent handling
- question progression
- retry / reprompt behavior

This must stay provider-agnostic.

---

## Phase-Wise Plan

---

## Phase 0 — Instrumentation and Benchmark Baseline

### Objective

Establish hard baseline numbers before changing the stack.

### Scope

1. Add structured logging for:
   - outbound call create
   - voice webhook hit
   - stream connected
   - first assistant audio out
   - first user transcript in
   - call completed
2. Measure:
   - time from call start request to phone ringing
   - time from answer to first audible assistant utterance
   - time from user stop-speaking to assistant response start
3. Add lightweight metrics fields to logs or DB:
   - provider
   - runtime
   - call duration
   - transcript presence
   - evaluation presence
   - recording presence

### Deliverables

1. Baseline latency checklist
2. Baseline cost worksheet
3. One sample real-call benchmark for current Twilio + OpenAI Realtime flow

### Verification

1. Run at least 3 real calls.
2. Record baseline latency and transcript quality.
3. Store baseline numbers in a doc or handoff note.

### Exit criteria

We have objective baseline metrics before migration work begins.

---

## Phase 1 — Immediate Text-Agent Cost Reduction

### Objective

Reduce non-realtime AI cost quickly with minimal complexity.

### Scope

Switch these agents from `gpt-4o` to `gpt-4o-mini` unless a specific accuracy issue is proven:

1. Resume parser
2. Question generator
3. Evaluation agent

### Implementation tasks

1. Add a dedicated mini-model config if not already present.
2. Update the three agent classes to use the cheaper model.
3. Keep prompts unchanged initially.
4. Run regression tests against:
   - structured resume extraction
   - question schema stability
   - evaluation schema stability

### Verification

1. Full backend tests pass.
2. Parse a real resume and compare quality against existing output.
3. Generate questions for a real resume.
4. Evaluate a real call transcript and confirm output remains usable.

### Exit criteria

Per-candidate text-AI cost is reduced with no meaningful quality regression.

---

## Phase 2 — Prompt and Session-Update Cost Optimization

### Objective

Reduce waste in the current OpenAI Realtime implementation.

### Scope

1. Shorten the realtime system prompt.
2. Reduce unnecessary `session.update` calls.
3. Review any redundant question or resume context being resent.

### Implementation tasks

1. Split prompt content into:
   - static rules
   - dynamic state rules
2. Only call `session.update` when:
   - consent state changes
   - termination state changes
   - off-topic state changes in a way that affects policy
3. Ensure no repeated prompt churn on harmless user turns.

### Verification

1. Real call still handles:
   - consent
   - off-topic requests
   - decline flow
2. Transcript quality is unchanged or improved.
3. Logging shows fewer `session.update` events per call.

### Exit criteria

Realtime control token waste is reduced without changing behavior.

---

## Phase 3 — Telephony Abstraction Cleanup

### Objective

Prepare the codebase for multi-carrier support without changing the live provider yet.

### Scope

Refactor telephony code into explicit provider modules.

### Implementation tasks

1. Create telephony provider interface.
2. Move current Twilio implementation into a Twilio provider class.
3. Keep current behavior working exactly as it does now.
4. Move webhook-specific parsing into provider-aware utilities where appropriate.

### Verification

1. Existing Twilio tests pass.
2. Existing real browser-path call flow still works.

### Exit criteria

Twilio is still working, but the code is now ready for Plivo support.

---

## Phase 4 — Add Plivo Telephony Support in Parallel

### Objective

Introduce Plivo as a second telephony provider and enable side-by-side testing.

### Scope

Support Plivo outbound calling and Plivo bidirectional audio streaming while keeping Twilio available.

### Implementation tasks

1. Add Plivo config values:
   - auth ID
   - auth token
   - phone number
   - provider selector
2. Add Plivo outbound call creation.
3. Add Plivo answer XML generation using `<Stream bidirectional="true">`.
4. Add Plivo webhook routes if payload shape differs from Twilio.
5. Add Plivo stream status callback route.
6. Make the provider selectable by env var or feature flag.

### Verification

#### Automated

1. Unit tests for provider selection.
2. Tests for Plivo answer XML generation.
3. Tests for Plivo callback parsing.

#### Manual

1. Start a call through the UI using Plivo mode.
2. Confirm:
   - outbound call is placed
   - media stream connects
   - transcript starts
   - call completion updates correctly

### Exit criteria

Plivo can successfully place and stream a real interview call through the existing backend architecture.

---

## Phase 5 — Deepgram STT Introduction

### Objective

Use Deepgram for speech-to-text while preserving OpenAI for reasoning.

### Scope

Replace or supplement Realtime-native transcription with Deepgram streaming STT.

### Why this phase first

This is the safest Deepgram entry point:

1. It can reduce dependence on OpenAI Realtime transcription behavior.
2. It gives us more control over transcript quality.
3. It is less invasive than replacing TTS and reasoning simultaneously.

### Implementation tasks

1. Add Deepgram streaming client integration.
2. Feed inbound caller audio to Deepgram in real time.
3. Use:
   - interim results
   - VAD events
   - endpointing tuning
4. Normalize Deepgram transcript events into the existing transcript persistence path.
5. Decide whether to:
   - keep OpenAI user transcript as fallback
   - or fully trust Deepgram STT

### Verification

1. Compare transcript quality against current OpenAI transcript capture.
2. Measure:
   - speech-to-text latency
   - transcript completeness
   - interruption handling quality
3. Run at least 3 real calls with:
   - short answers
   - interruptions
   - pauses
   - off-topic turns

### Exit criteria

Deepgram STT is at least as good as the current transcript path and does not create unacceptable latency.

---

## Phase 6 — Deepgram TTS Introduction

### Objective

Replace OpenAI audio output generation with Deepgram TTS while keeping OpenAI for reasoning.

### Scope

The backend will:

1. get user transcript from Deepgram STT
2. send text context to OpenAI for reasoning
3. send model text output to Deepgram TTS
4. stream resulting audio back to the carrier

### Implementation tasks

1. Introduce TTS runtime adapter for Deepgram.
2. Request `mulaw` or a compatible output format suitable for the carrier stream.
3. Add barge-in support:
   - when caller speaks, clear pending outgoing TTS audio
4. Keep the backend state machine authoritative.
5. Ensure final assistant text is still persisted even if TTS is interrupted.

### Verification

1. Compare first-response latency against the OpenAI Realtime baseline.
2. Confirm audio quality and naturalness are acceptable.
3. Confirm interruption behavior is better or no worse.
4. Confirm consent prompt is still respected.

### Exit criteria

The Deepgram TTS pipeline produces acceptable latency and audio quality in real calls.

---

## Phase 7 — Full Orchestrated Voice Runtime

### Objective

Run the full live call pipeline as:

```text
Plivo <-> backend <-> Deepgram STT <-> OpenAI text reasoning <-> Deepgram TTS <-> backend <-> Plivo
```

### Scope

This is the first phase where the system is fully off the current OpenAI Realtime-first voice path.

### Implementation tasks

1. Introduce a runtime selector:
   - `openai_realtime`
   - `deepgram_openai_pipeline`
2. Move turn-taking and interruption logic fully into backend orchestration.
3. Ensure assistant response generation is explicitly triggered after end-of-turn detection.
4. Add buffering and timeout rules to avoid:
   - double questions
   - clipped openers
   - overlapping turns

### Verification

1. Run at least 5 real calls.
2. Validate:
   - consent flow
   - recruiter identity opener
   - question pacing
   - interruption handling
   - graceful decline handling
   - clean hangup
3. Compare with baseline on:
   - cost
   - first-response latency
   - perceived responsiveness
   - transcript quality

### Exit criteria

The orchestrated pipeline is good enough to become the default development path.

---

## Phase 8 — Frontend and Observability Hardening

### Objective

Make the recruiter-facing UI and internal observability match the new architecture.

### Scope

1. Fix noisy websocket reconnect behavior on call progress UI.
2. Expose provider and runtime labels in call detail.
3. Add latency/debug metadata for internal use.
4. Add clear status presentation for:
   - queued
   - ringing
   - in progress
   - completed
   - failed

### Verification

1. Browser verification for:
   - call start
   - live progress
   - call detail
   - transcript visibility
   - recording playback
2. No runaway websocket reconnect loops.
3. No console errors during normal use.

### Exit criteria

The recruiter UI behaves cleanly with the new backend pipeline.

---

## Phase 9 — Final Cost and Product Benchmark

### Objective

Measure whether the optimization effort actually delivered the intended business outcome.

### Required benchmark outputs

1. Cost per 10-minute interview:
   - old stack
   - new stack
2. Average first-response latency
3. Average turn latency
4. Transcript quality assessment
5. Subjective call quality assessment

### Final decision

Choose one default development path:

1. `Twilio + OpenAI Realtime`
2. `Plivo + OpenAI Realtime`
3. `Plivo + Deepgram STT/TTS + OpenAI reasoning`

### Exit criteria

We have a measured final recommendation, not just a theoretical one.

---

## Recommended Execution Order

If the goal is **fastest savings and best product**, do phases in this order:

1. Phase 0 — Baseline
2. Phase 1 — Text-agent model downgrade
3. Phase 2 — Prompt/session optimization
4. Phase 3 — Telephony abstraction cleanup
5. Phase 4 — Plivo support
6. Phase 5 — Deepgram STT
7. Phase 6 — Deepgram TTS
8. Phase 7 — Full orchestrated runtime
9. Phase 8 — Frontend/observability hardening
10. Phase 9 — Final benchmark

---

## Acceptance Rules for Each Phase

Every phase must end with:

1. Code implemented
2. Tests added or updated
3. Browser-path verification if UI is affected
4. Real-call verification if the live voice path is affected
5. Findings fixed before moving on
6. A clean git commit before starting the next phase

---

## Known Risks

### 1. Latency stacking

Deepgram STT + OpenAI text reasoning + Deepgram TTS may be slower than OpenAI Realtime if orchestration is sloppy.

Mitigation:

1. benchmark each phase
2. tune endpointing
3. stream aggressively where possible
4. keep assistant responses short

### 2. Provider protocol differences

Plivo is not a drop-in Twilio clone.

Mitigation:

1. keep provider adapters isolated
2. write provider-specific tests
3. verify real calls early

### 3. Conversation-quality regressions

Changing the audio path may break turn-taking even if transcripts still work.

Mitigation:

1. preserve backend state machine ownership
2. test consent and interruption on every runtime/provider combination

### 4. False savings from theory-only calculations

Token and minute costs on paper do not equal real system cost.

Mitigation:

1. benchmark actual traffic
2. measure end-to-end latency
3. compare real recordings and transcripts

---

## Fresh-Session Handoff Prompt

If starting from a fresh chat, use this context:

> We are implementing the plan in `docs/cost_optimization_implementation_plan.md`.  
> Keep OpenAI in the stack.  
> Add Plivo support in parallel with Twilio behind a telephony abstraction.  
> Introduce Deepgram incrementally, starting with STT, then TTS, then a full orchestrated voice pipeline.  
> Optimize for fastest per-call savings, ultra low latency, and best product quality.  
> The backend state machine must remain authoritative for consent, off-topic handling, interview progression, interruption handling, and hangup behavior.  
> Do not do a big-bang rewrite. Complete one phase at a time, verify it, fix issues, and commit before moving on.

