# Call V2 Testing And Simulator Plan

## Purpose

V2 must be developed through strict module and seam testing. The goal is to avoid building a full runtime that works conceptually but fails in practical timing or provider behavior.

The simulator is the primary proving ground before live Exotel or Twilio calls.

## Testing Philosophy

Each module must be testable without the layers above it.

Each seam must be tested before moving to the next phase.

```text
module works
+ downstream seam works
= phase can move forward
```

No module is considered complete until its important downstream seam passes automated tests and at least one manual/simulator test where audio timing matters.

## Test Types

### Unit Tests

Focused tests for individual classes/functions.

Examples:

- Cache key generation.
- Transcript deduplication.
- Agent output validation.
- State transition validation.
- Audio format compatibility.

### Fixture Tests

Replay deterministic fixtures without live providers.

Examples:

- Simulated Deepgram event stream.
- Simulated Exotel media start/media/stop payloads.
- Simulated delayed STT final event.
- Simulated duplicate transcript final.

### Seam Tests

Tests between adjacent modules.

Examples:

- Telephony adapter -> normalized audio frames.
- STT events -> endpointing decisions.
- Endpointing -> speculative agent run.
- Agent output -> TTS/cache resolver.
- TTS chunks -> telephony outbound audio.

### Simulator Tests

End-to-end local call behavior without live telephony budget.

Simulator should support:

- Scripted candidate behavior.
- Human candidate behavior.
- ChatGPT Voice as candidate.
- Event trace export.
- Audio timing manipulation.

### Live Provider Tests

Run only after simulator gates pass.

Order:

1. Browser/simulator.
2. Exotel controlled test calls.
3. Twilio after core behavior is stable.

## Required Trace Artifact

Every simulator and live test must produce a trace.

Trace should include:

```text
telephony.stream_started
telephony.audio_frame summaries
stt.connected
stt.speech_started
stt.final_segment
stt.tentative_endpoint
turn.tentative_started
agent.run_started
turn.tentative_cancelled
turn.confirmed
agent.run_completed
audio.source_selected
tts.started
tts.first_audio
tts.completed
telephony.clear_outbound_audio
telephony.stream_stopped
persistence.transcript_turn_committed
```

Trace requirements:

- Generation ids visible.
- Timings visible.
- Cache decisions visible.
- Cancellation reasons visible.
- Stale result discards visible.
- Redaction supported for production later.

## Manual Test Scorecard

After every manual simulator or live call, record:

```text
Did the agent interrupt the candidate?
Did it miss anything the candidate said?
Did it respond too slowly?
Did it speak over the candidate?
Did it handle clarification naturally?
Did it explain a question when asked?
Did it sound robotic?
Was cached audio noticeable?
Was transcript accurate?
Did the call end correctly?
Was the trace sufficient to explain issues?
```

Each item should be pass/fail with notes.

## Module Gates

### Gate 1: Contracts And State Machine

Scope:

- Event models.
- State machine transitions.
- Generation id handling.
- Trace envelope.

Automated tests:

- Valid state transitions accepted.
- Invalid transitions rejected or traced.
- Generation id increments.
- Stale generation cannot speak.
- Trace envelope serializes.

Manual review:

- Team can explain normal call path from state machine.
- Team can explain failure path from state machine.

Exit criteria:

- Event contracts and state machine docs are approved.
- Test scaffolding can construct domain events.

### Gate 2: Telephony Adapter And Simulator

Scope:

- Browser/simulator adapter.
- Exotel adapter shape if fixtures available.
- Normalized inbound events.
- Outbound audio command formatting.

Automated tests:

- Start event creates `TelephonyStreamStarted`.
- Media event creates `TelephonyAudioFrame`.
- Stop event creates `TelephonyStreamStopped`.
- Outbound audio command requires stream id.
- Clear audio command serializes if provider supports it.

Simulator tests:

- Scripted stream start/media/stop.
- Missing stream id.
- Duplicate stream start.
- Provider disconnect.

Exit criteria:

- Simulator can drive a fake call session without STT/agent/TTS.
- Adapter quirks do not leak outside adapter tests.

### Gate 3: STT Engine And Transcript Assembler

Scope:

- STT event normalization.
- Transcript assembly.
- Deduplication.
- Audio format handling.

Automated tests:

- Interim transcript not persisted.
- Final segments assemble into one user turn.
- Duplicate final events deduplicated.
- Empty transcripts ignored.
- Delayed STT event keeps timing metadata.

Simulator tests:

- Fixture-driven STT without live Deepgram.
- Optional live Deepgram smoke test with recorded audio.

Exit criteria:

- STT produces stable events for endpointing.
- Transcript assembler handles duplicate and delayed provider events.

### Gate 4: Endpointing And Speculation

Scope:

- Tentative turn.
- Confirmation window.
- Cancellation.
- Stale result handling.
- Post-TTS guard hooks.

Automated tests:

- 500ms pause then continuation cancels speculation.
- Silence confirmation reuses speculative result.
- Confirmation waits for still-running agent result.
- Delayed STT final plus new audio prevents false confirmation.
- Short `yes` is accepted.
- Duplicate final does not create duplicate turn.

Simulator/manual tests:

- Human pauses mid-sentence then continues.
- ChatGPT Voice rambles and pauses.
- Candidate answers immediately after TTS in simulated post-TTS guard.

Exit criteria:

- No speculative result can persist or speak before confirmation.
- Trace explains every speculative decision.

### Gate 5: Agent Contract

Scope:

- Agent input builder.
- Prompt shape.
- Structured output validation.
- Tool schema handling.
- Speculative run behavior.

Automated tests:

- Consent granted/refused.
- Clarification request.
- Explain question request.
- Short answer.
- Long answer.
- Off-scope question.
- Terminal action.
- Invalid output repair.
- Tool call validation.
- Speculative tool calls do not execute.

Manual tests:

- Chat through agent without audio.
- Review naturalness and scope adherence.

Exit criteria:

- Agent can drive recruitment conversation through config.
- Runtime does not need deterministic question policy.
- Runtime does not parse assistant prose for call control.

### Gate 6: TTS And Audio Cache

Scope:

- Audio source resolver.
- Exact cache lookup.
- Live TTS.
- TTS fallback.
- Chunk pacing.
- Cancellation.

Automated tests:

- Known question cache hit.
- Cache miss live TTS.
- Wrong codec misses cache.
- Candidate-specific text not persistently cached.
- TTS cancellation stops chunks.
- Fallback provider used on primary failure.

Manual tests:

- Compare cached question audio vs live TTS.
- Confirm cached audio does not sound robotic.
- Ask for question explanation and verify live TTS path.

Exit criteria:

- Cache is exact and safe.
- TTS can be cancelled.
- Audio output matches provider adapter requirements.

### Gate 7: First Full Simulator Slice

Scope:

```text
simulator/browser
-> telephony adapter
-> STT fixture or mocked STT
-> endpointing/speculation
-> real agent
-> mocked or live TTS
-> outbound audio events
```

Automated tests:

- Normal full turn.
- Speculative cancellation.
- Stale agent result discarded.
- Cached known question.
- Live TTS follow-up.
- End-call action.

Manual tests:

- User acts as candidate in simulator.
- ChatGPT Voice acts as candidate.
- Candidate asks explanation.
- Candidate interrupts.
- Candidate pauses mid-answer.

Exit criteria:

- Full trace is explainable.
- No untraced async task controls call behavior.
- Manual scorecard passes core interaction cases.

### Gate 8: Exotel Controlled Test

Before this gate, run the real-audio simulator slice:

```text
simulator/browser or recorded audio
-> telephony adapter
-> provider-backed buffered STT
-> endpointing/speculation
-> agent
-> provider-backed TTS
-> outbound audio events
```

Required checks:

- Real STT can transcribe a buffered candidate turn.
- Real TTS returns audio converted to the telephony output format.
- The simulator exposes `real_audio=1` explicitly; fake deterministic mode remains the default harness.
- `stt.transcribe_buffer` is used as a test control before live streaming STT is introduced.
- Provider API keys are never committed to docs, tests, fixtures, or shell scripts.

Exit criteria:

- Recorded audio or manual audio can drive a full turn without Exotel.
- Provider-backed TTS audio plays through the same v2 outbound media contract.
- Trace explains STT flush, turn confirmation, and audio source selection.

Scope:

- Exotel adapter with real stream.
- Real Deepgram STT.
- Real or controlled TTS.
- Post-TTS guard validation.

Live tests:

- Normal screening call.
- Candidate speaks immediately after assistant.
- Candidate interrupts assistant.
- Candidate pauses mid-answer.
- Candidate asks clarification.

Exit criteria:

- No missed immediate post-TTS candidate response.
- No premature speculative interruption.
- Trace explains any provider weirdness.

### Gate 9: Twilio Adapter

Scope:

- Twilio adapter.
- Mu-law audio format.
- Clear audio command behavior.
- Twilio-specific status callbacks if needed.

Exit criteria:

- Twilio works through same core runtime contracts.
- No Twilio-specific logic leaks into agent or endpointing.

## Scripted Simulator Scenarios

Required scenario library:

### normal_short_call

- Candidate grants consent.
- Candidate answers two questions.
- Agent ends politely.

### pause_then_continue

- Candidate says half an answer.
- Pauses 500ms.
- Continues.
- Expected: speculative run cancelled, no assistant interruption.

### delayed_stt_final

- STT final arrives late.
- New audio arrives during apparent silence.
- Expected: no false confirmation.

### immediate_after_tts

- Candidate starts speaking 100ms after assistant audio completes.
- Expected: response captured.

### barge_in

- Candidate interrupts assistant mid-TTS.
- Expected: pending barge-in, confirmed transcript, TTS cancelled.

### echo_false_positive

- Inbound transcript resembles assistant question.
- Expected: echo suppressed if no candidate content.

### explain_question

- Candidate asks for more detail.
- Expected: agent explains naturally, live TTS path by default.

### one_word_answer

- Candidate says `yes`.
- Expected: not discarded as noise.

### stale_agent_result

- Agent result A returns after generation B.
- Expected: A discarded.

### tts_failure

- Primary TTS fails.
- Expected: fallback or graceful recovery.

## Manual Candidate Modes

### Human Candidate

The user speaks as the candidate.

Good for:

- Natural timing.
- Awkwardness detection.
- Immediate post-TTS speech.
- Interruption behavior.

### ChatGPT Voice Candidate

ChatGPT Voice can act as:

- Fast candidate.
- Rambling candidate.
- Confused candidate.
- Candidate asking clarifications.
- Candidate with interruptions.

Good for repeatable-ish conversational stress without telephony budget.

## Test Data And Fixtures

Maintain fixtures for:

- Provider start/media/stop payloads.
- STT event streams.
- Audio frame timestamp patterns.
- Agent input/output examples.
- TTS chunk sequences.
- Cache hit/miss examples.

Fixtures should live near v2 tests and be versioned with the contracts they exercise.

## Regression Policy

Every bug discovered in manual or live testing must become either:

- Automated test fixture.
- Scripted simulator scenario.
- Manual checklist item.

No practical call bug should remain only as memory or chat notes.

Refactors are welcome when they simplify the architecture or unlock a better implementation. Before refactoring an existing module, define the behavior that must not regress and cover it with one or more of:

- Unit tests.
- Fixture tests.
- Seam tests.
- Simulator scenarios.
- Manual scorecard cases.

After the refactor, stale code must be removed. Avoid leaving old branches, unused helpers, commented-out code, or shadow implementations that future work could accidentally revive.

## Success Criteria

The test strategy is successful when:

- We can test most call behavior without paid telephony.
- Simulator traces explain timing bugs.
- Each module has a clear completion gate.
- Each seam has explicit pass/fail tests.
- Live Exotel testing starts only after simulator confidence.
- V2 does not need late patch layers to handle predictable edge cases.
- Refactors can happen safely because regression expectations are explicit.
- Cleanup is part of each change, not a postponed final chore.
