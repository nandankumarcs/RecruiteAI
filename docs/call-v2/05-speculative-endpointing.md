# Call V2 Speculative Endpointing

## Purpose

Speculative endpointing is a latency optimization. It lets the backend start agent processing after a short silence, while still allowing the candidate to continue speaking without being interrupted or misrepresented.

This document defines how speculation works, what it is allowed to do, and how we avoid v1 failure modes.

## Core Idea

```text
candidate speaks
-> STT sees a tentative endpoint after short silence
-> backend starts speculative agent run
-> candidate continues: discard speculative work
-> candidate stops: confirm turn and reuse speculative result
```

The optimization is useful only if speculative work is quarantined until confirmation.

## Non-Negotiable Rule

Speculative work may read but cannot write.

Speculative runs cannot:

- Persist user transcript.
- Persist assistant transcript.
- Execute tools.
- Mark questions or objectives as covered.
- Start TTS.
- End the call.
- Update durable call state.

## Endpointing Controller Inputs

The controller consumes:

- STT speech started events.
- STT interim transcript events.
- STT final segment events.
- STT tentative endpoint events.
- STT utterance end events.
- Inbound audio frame arrival timestamps.
- Assistant speaking state.
- Post-TTS guard state.
- Echo suppression hints.

It should not depend on a single provider event type.

## Endpointing Controller Outputs

The controller emits:

- `TentativeTurnStarted`
- `TentativeTurnCancelled`
- `TurnConfirmed`
- `TurnDiscarded`

See `03-event-contracts.md` for schemas.

## Timing Model

V2 must track these clocks separately:

```text
provider media timestamp
backend audio receive timestamp
STT event receive timestamp
STT audio offset timestamp
agent run timestamp
TTS playback timestamp
```

Important rule:

```text
Do not compute candidate silence only from STT event arrival time.
```

Why:

STT events can arrive late. If Deepgram takes extra time to emit a final result, backend wall-clock time may falsely suggest the candidate has been silent longer than they actually have.

Endpoint confirmation should consider:

- Has new inbound audio arrived since tentative endpoint?
- Has STT emitted new final/interim content that extends the utterance?
- Is the latest transcript stable?
- Are we inside post-TTS guard?
- Is the candidate speech possibly suppressed or delayed by provider behavior?

## Recommended Initial Parameters

These are starting points for simulator testing, not final values.

```text
tentative_silence_ms = 500
confirmation_window_ms = 700 to 1000
post_tts_guard_ms = 500 to 1200
min_non_echo_words_for_barge_in = 2
min_non_echo_chars_for_barge_in = 8
max_candidate_turn_seconds = configurable, initially 60
```

The final values should be based on simulator and Exotel traces.

## Turn Lifecycle

### Listening

The transcript assembler accumulates final STT segments and tracks interim text.

When the STT provider indicates a tentative endpoint:

```text
text = assembled transcript + stable latest segment
generation_id += 1
emit TentativeTurnStarted
start speculative agent run
```

### Speculating

Speculative agent run starts with:

- Current committed conversation.
- Tentative latest user turn.
- `speculative=True`.
- Generation id.
- Input fingerprint.

The system continues listening.

### Candidate Continues

Candidate continuation can be detected through:

- New inbound audio after tentative endpoint.
- STT speech started.
- New interim transcript that extends or changes text.
- New final segment.

But cancellation should be careful:

- During normal listening, new audio can cancel speculation.
- During TTS playback, VAD-only events create pending barge-in, not immediate cancellation.
- During post-TTS guard, small speech should be accepted aggressively.

When continuation is confirmed:

```text
mark generation stale
cancel speculative task if possible
discard result if it later returns
return to listening
```

### Silence Holds

If confirmation window passes and no continuation invalidates the turn:

```text
emit TurnConfirmed(generation_id)
persist user turn
reuse speculative agent result if ready and fingerprint matches
otherwise await running result or start fresh run
```

### Agent Result Ready Before Confirmation

Hold result in memory.

Do not:

- Persist assistant message.
- Start TTS.
- Execute tools.

### Confirmation Before Agent Result

Persist confirmed user turn and await the in-flight speculative run if it is still valid.

This is the desired latency win: part of the LLM work is already underway.

## Stale Result Handling

Every speculative run has:

- `generation_id`
- `input_fingerprint`
- `speculative=True`

Before using the result:

```text
generation_id == latest_confirmed_generation_id
input_fingerprint == current_expected_fingerprint
session_state allows speaking
```

If any check fails, discard result.

## Transcript Assembly

STT providers can emit overlapping or duplicated segments.

The assembler should:

- Track final segment ids when available.
- Normalize whitespace.
- Deduplicate exact repeated segments.
- Avoid appending the same text from both `speech_final` and `utterance_end`.
- Preserve enough metadata for debugging.

Confirmed user turn text should be the assembler's output, not a raw provider event.

## Post-TTS Guard

This is required because the user reported v1 could miss candidate speech immediately after TTS, likely due to Exotel/media gateway echo cancellation or timing behavior.

After TTS completes:

```text
state = post_tts_guard
keep STT open
accept inbound speech aggressively
do not require SpeechStarted
compare transcript against assistant echo
if candidate content appears, process normally
```

During guard:

- Do not discard short answers just because they are short.
- Do not wait for perfect provider VAD.
- Do not close/reopen STT stream.
- Do trace all inbound audio and STT events.

## Barge-In During TTS

Candidate interruption while assistant is speaking is separate from ordinary endpointing.

Recommended flow:

```text
VAD/audio during TTS
-> pending_barge_in
-> wait for transcript or strong non-echo audio evidence
-> confirmed barge-in
-> clear provider audio
-> cancel TTS
-> return to listening
```

Avoid:

- Cancelling on VAD-only events.
- Treating assistant echo as candidate speech.
- Suppressing real short user responses.

## Echo Suppression

During `speaking` and `post_tts_guard`, transcript may include assistant audio.

Suppress likely echo if:

- It is highly similar to recent assistant spoken text.
- It occurs during or immediately after assistant playback.
- It does not include clear candidate additions.

Do not suppress:

- `yes`
- `no`
- `okay`
- `sure`
- `repeat that`
- `I did not understand`
- Candidate-specific answers that share a few words with the question.

## Long Turn Handling

Some candidates will speak for a long time.

V2 needs explicit limits:

- Soft max answer duration: trace and optionally prepare a gentle interruption.
- Hard max answer duration: agent may politely pause the candidate if configured.

This is not part of initial speculation, but the controller should expose enough timing to add it cleanly.

## Failure Modes And Mitigations

### Delayed STT Event Causes False Silence

Mitigation:

- Use inbound audio arrival as a freshness signal.
- Prefer STT audio offsets when available.
- Confirmation requires no new audio since tentative endpoint, not just delayed event timing.

### Candidate Continues After 500ms Pause

Mitigation:

- Cancel or stale speculative generation.
- Do not persist tentative transcript.
- Do not speak speculative result.

### Candidate Speaks Immediately After TTS

Mitigation:

- Post-TTS guard.
- Keep STT stream open.
- Accept short speech.
- Trace inbound audio even if STT VAD is weird.

### STT Emits Duplicate Finals

Mitigation:

- Transcript assembler deduplication.
- Segment ids when available.
- Text overlap detection.

### Agent Result A Returns After Result B

Mitigation:

- Generation id check before every TTS start.
- Stale result discard.

### Barge-In False Positive

Mitigation:

- VAD-only is pending, not confirmed.
- Confirm with transcript or strong audio evidence.

### Barge-In False Negative

Mitigation:

- Track inbound audio energy during TTS if practical.
- Confirm candidate speech as soon as transcript arrives.
- Keep TTS cancellable.

## Trace Requirements

Every speculative lifecycle should produce trace events:

```text
turn.tentative_started generation_id text_hash source
agent.run_started generation_id speculative=true
turn.tentative_cancelled generation_id reason
agent.run_cancelled generation_id reason
turn.confirmed generation_id text_hash
agent.run_completed generation_id stale=false
agent.run_completed generation_id stale=true discarded
```

For timing issues, trace should include:

- Last inbound audio frame timestamp before tentative endpoint.
- STT event backend receive timestamp.
- STT audio offset timestamp if present.
- Confirmation deadline.
- Whether new audio arrived during confirmation window.

## Automated Test Cases

Required:

1. 500ms pause then candidate continues.
2. 500ms pause then silence holds and speculative result is reused.
3. Confirmation happens before speculative result completes.
4. Speculative result returns after cancellation and is discarded.
5. STT final event delayed beyond confirmation window but new audio arrived, so turn is not confirmed early.
6. Duplicate final segments do not duplicate transcript text.
7. Candidate says short `yes` and it is confirmed.
8. Candidate speaks immediately after TTS and is not ignored.
9. VAD-only during TTS does not cancel audio.
10. Confirmed non-echo barge-in cancels TTS.

## Manual Simulator Cases

Required:

- Speak, pause for half a second, continue the sentence.
- Speak a complete answer and stop naturally.
- Answer immediately after the assistant finishes.
- Interrupt the assistant mid-question.
- Ask the assistant to explain the question.
- Give one-word answers.
- Speak with background noise.
- Let ChatGPT Voice act as a fast or rambling candidate.

## Success Criteria

Speculative endpointing is successful when:

- Latency improves on normal turns.
- Candidate continuations are not interrupted.
- No speculative transcript reaches durable conversation history.
- No speculative response reaches TTS before confirmation.
- Post-TTS speech is captured in simulator and Exotel tests.
- Trace makes every endpointing decision explainable.
