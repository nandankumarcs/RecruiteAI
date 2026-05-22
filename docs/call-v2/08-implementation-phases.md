# Call V2 Implementation Phases

## Purpose

This document turns the v2 architecture into an implementation sequence. The order is designed to prevent v1-style brittleness: no large untested call loop, no hidden async behavior, and no optimizations added before their boundaries are testable.

## Branch Goal

This branch focuses on the v2 call implementation as the primary future call runtime.

There is no v1/v2 runtime flag in the design. The branch itself is the isolation boundary.

Operational toggles may still exist for internal capabilities:

```text
SPECULATION_ENABLED
AUDIO_CACHE_ENABLED
STT_PROVIDER
TTS_PROVIDER
PRIMARY_TELEPHONY_PROVIDER
```

These are not v1 compatibility toggles.

## Phase 0: Planning Documents

Status: current phase.

Deliverables:

- `01-architecture-and-principles.md`
- `02-runtime-state-machine.md`
- `03-event-contracts.md`
- `04-agent-contract.md`
- `05-speculative-endpointing.md`
- `06-cache-policy.md`
- `07-testing-and-simulator-plan.md`
- `08-implementation-phases.md`

Exit criteria:

- Documents reviewed and adjusted.
- Open questions resolved.
- First implementation target confirmed.

## Phase 1: V2 Contracts And Trace Foundation

Goal:

Create the foundational types and trace logger without live telephony behavior.

Implementation scope:

- V2 package/module structure.
- Event models.
- State machine model.
- Generation id manager.
- Trace event envelope.
- Test helpers for event construction.

Suggested files:

```text
backend/app/call_v2/
  __init__.py
  events.py
  state.py
  trace.py
  ids.py
```

Tests:

- Event serialization.
- State transition validation.
- Generation id behavior.
- Trace event redaction hooks.

Manual gate:

- Read a sample trace and verify it is understandable.

Exit criteria:

- Contracts compile and tests pass.
- Trace foundation can be used by later modules.

## Phase 2: Simulator And Telephony Adapter Foundation

Goal:

Make simulator the first-class test harness.

Implementation scope:

- Browser/simulator adapter.
- Provider adapter interface.
- Normalized inbound telephony events.
- Normalized outbound telephony commands.
- Fixture-driven provider payload tests.

Suggested files:

```text
backend/app/call_v2/telephony/
  base.py
  simulator.py
  exotel.py
  twilio.py        # interface skeleton only if useful
```

Tests:

- Simulator start/media/stop.
- Missing stream id behavior.
- Outbound audio requires stream id.
- Provider stop cancels session.

Manual gate:

- Run simulator without STT/agent/TTS and inspect trace.

Exit criteria:

- Simulator can produce a fake call stream.
- Adapter boundary hides provider payloads.

## Phase 3: Audio Format And Codec Boundary

Goal:

Centralize audio format handling before STT/TTS integration.

Implementation scope:

- Audio format types.
- Mu-law and L16 conversion helpers.
- Frame sizing helpers.
- Provider compatibility validation.

Suggested files:

```text
backend/app/call_v2/audio/
  formats.py
  codecs.py
  pacing.py
```

Tests:

- Mu-law to L16 conversion.
- L16 to mu-law conversion.
- Unsupported format rejected.
- Chunk sizing stable.

Exit criteria:

- No provider/STT/TTS module needs hidden codec conversion.

## Phase 4: STT Engine And Transcript Assembler

Goal:

Convert audio frames into stable transcript events.

Implementation scope:

- STT engine interface.
- Deepgram implementation or fixture-backed fake first.
- Transcript assembler.
- STT fixture replay.

Suggested files:

```text
backend/app/call_v2/stt/
  base.py
  deepgram.py
  fake.py
  transcript_assembler.py
```

Tests:

- Interim ignored for persistence.
- Final segment assembly.
- Duplicate final deduplication.
- Empty transcript ignored.
- Delayed STT event keeps timing metadata.

Manual gate:

- Replay recorded/synthetic candidate speech through simulator fixture.

Exit criteria:

- Endpointing receives clean transcript events.
- STT quirks do not leak into CallSession.

## Phase 5: Endpointing Controller And Speculation Harness

Goal:

Implement speculative turn processing in isolation before real agent/TTS integration.

Implementation scope:

- Endpointing controller.
- Confirmation timer.
- Cancellation logic.
- Generation id staleness.
- Post-TTS guard hooks.
- Fake agent runner for speculation tests.

Suggested files:

```text
backend/app/call_v2/turns/
  endpointing.py
  transcript_buffer.py
  speculation.py
```

Tests:

- Pause then continue.
- Silence confirmation.
- Delayed STT plus new audio.
- Short answer accepted.
- Duplicate final ignored.
- Stale speculative output discarded.

Manual gate:

- Simulator scripted cases for pause/continue and immediate post-TTS speech using fake downstream modules.

Exit criteria:

- No speculative output can persist or speak before confirmation.
- Trace explains all endpointing choices.

## Phase 6: Agent Runner

Goal:

Build the general-purpose call agent independent of telephony and audio.

Implementation scope:

- Agent input builder.
- Prompt builder.
- Structured output schema.
- Agent output validator.
- LLM runner.
- Optional LangChain integration if it helps agent/tool/prompt middleware.
- Fake agent for deterministic tests.

Suggested files:

```text
backend/app/call_v2/agent/
  config.py
  prompts.py
  runner.py
  output.py
  tools.py
  fake.py
```

Tests:

- Consent.
- Refusal.
- Repeat.
- Explain question.
- Short answer.
- Long answer.
- Off-scope handling.
- Terminal action.
- Invalid output repair.
- Speculative tool calls blocked.

Manual gate:

- Text-only conversation with the agent using recruitment config.

Exit criteria:

- Agent can lead recruitment screening through config.
- Runtime does not need deterministic question policy.

## Phase 7: TTS And Audio Source Resolver

Goal:

Speak agent output through exact cache or live TTS.

Implementation scope:

- TTS engine interface.
- Deepgram/Sarvam wrappers or adapters around existing provider code.
- Audio source resolver.
- Exact cache lookup.
- Cache eligibility classifier.
- TTS cancellation.

Suggested files:

```text
backend/app/call_v2/tts/
  base.py
  providers.py
  resolver.py
  cache.py
  eligibility.py
```

Tests:

- Known question cache hit.
- Cache miss live TTS.
- Wrong codec misses.
- Candidate-specific text not persistently cached.
- Question explanation live TTS.
- TTS cancellation.
- Fallback provider.

Manual gate:

- Listen to cached vs live TTS in simulator.
- Confirm cache never changes agent text.

Exit criteria:

- Audio resolver is safe and exact.
- TTS can be cancelled and traced.

## Phase 8: CallSession Integration With Fake Providers

Goal:

Integrate the full session with simulator and fake/mock modules.

Implementation scope:

- CallSession orchestration.
- Task lifecycle.
- State transitions.
- Trace event emission.
- Persistence interface with fake store first.

Suggested files:

```text
backend/app/call_v2/session.py
backend/app/call_v2/persistence.py
```

Tests:

- Normal call flow.
- Speculation cancel.
- Speculation reuse.
- Stale agent result.
- TTS cancel on barge-in.
- End-call action.
- Provider stop cleanup.

Manual gate:

- User acts as candidate in simulator.
- ChatGPT Voice acts as candidate.
- Scorecard recorded for each run.

Exit criteria:

- Full simulator trace is understandable.
- No hidden async task controls behavior outside state machine.

## Phase 9: Database Persistence Integration

Goal:

Persist confirmed runtime behavior to existing call/message models or a clean v2-compatible persistence boundary.

Implementation scope:

- Call status updates.
- Transcript writes.
- Idempotency keys.
- Latency metrics.
- Cost metrics.
- Recording metadata if applicable.

Tests:

- Confirmed user turn committed once.
- Assistant turn committed once.
- Speculative turns never committed.
- Stale assistant result never committed.
- Call completion persisted.

Exit criteria:

- Existing UI/API can read v2 call data.
- Persistence failures are recoverable or terminal by policy.

## Phase 10: Real STT And Real TTS In Simulator

Goal:

Run simulator with real Deepgram STT and real TTS without live telephony.

Scope:

- Feed real or recorded audio into STT.
- Use live TTS/cached audio.
- Validate timing.

Tests:

- Recorded audio fixture.
- Live microphone/browser path if simulator supports it.
- TTS first-byte and playback timing.

Manual gate:

- Human and ChatGPT Voice candidate tests.

Exit criteria:

- Latency and transcript quality are acceptable before Exotel.

## Phase 11: Exotel Adapter Live Test

Goal:

Connect Exotel to the v2 runtime.

Scope:

- Real Exotel stream adapter.
- Real Deepgram STT.
- Real Sarvam/Deepgram TTS.
- Post-TTS guard validation.
- Provider stop/status handling.

Live test checklist:

- Normal screening.
- Pause then continue.
- Immediate post-TTS speech.
- Barge-in.
- Explain question.
- Short answer.
- End call.

Exit criteria:

- No missed immediate post-TTS candidate response.
- No premature speculative interruption.
- Trace explains provider behavior.

## Phase 12: Twilio Adapter

Goal:

Add Twilio after the core runtime is stable.

Scope:

- Twilio adapter.
- Mu-law format.
- Twilio clear audio behavior.
- Status/recording callbacks if needed.

Exit criteria:

- Twilio uses the same core events and session.
- No Twilio logic leaks into agent, endpointing, or TTS resolver.

## Phase 13: Cleanup And Migration

Goal:

Remove or isolate obsolete v1 call runtime code once v2 is accepted.

Scope:

- Delete unused v1 runtime paths or mark as legacy.
- Remove dead flags/config.
- Remove stale codeblocks, commented-out alternatives, unused helper functions, and old workaround branches.
- Update developer docs.
- Update manual test guides.
- Update deployment notes.

Exit criteria:

- Codebase has one primary call runtime.
- V1 complexity is not preserved as accidental fallback.
- No obsolete code path remains without a documented owner, reason, and removal condition.

## Continuous Refactor And Cleanup Rule

Do not wait until Phase 13 to clean up code made obsolete by earlier phases.

During any phase:

- Refactor upstream modules when a downstream feature would otherwise require brittle layering.
- Add or update regression tests before changing behavior that existing code depends on.
- Remove replaced code in the same phase when safe.
- If temporary compatibility code is unavoidable, document why it exists and when it should be removed.
- Do not leave commented-out codeblocks or parallel shadow implementations.

## Review Checkpoints

Review after:

- Phase 0 docs.
- Phase 5 speculation harness.
- Phase 8 full simulator integration.
- Phase 11 Exotel live test.
- Phase 13 cleanup.

Each checkpoint should answer:

```text
What worked?
What failed?
What trace evidence do we have?
What contract needs changing?
What stale code or workaround can now be removed?
Does any requested change conflict with the architecture, phase boundary, or test gates?
Should we continue, pause, or redesign?
```

## Definition Of Done For V2

V2 is done when:

- Simulator and Exotel flows pass manual scorecards.
- Speculative endpointing improves latency without candidate interruption.
- Immediate post-TTS candidate speech is captured.
- Agent handles clarification and explanation naturally.
- Cache hits are exact and safe.
- Stale generations cannot speak.
- Trace artifacts explain call behavior.
- The old v1 runtime complexity is no longer the active implementation path.
- Refactors introduced during v2 are covered by regression tests.
- No stale codeblocks or undocumented fallback paths are left behind.
