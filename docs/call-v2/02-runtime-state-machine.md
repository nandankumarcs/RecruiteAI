# Call V2 Runtime State Machine

## Purpose

The v2 call runtime must make call state explicit. V1 became brittle partly because timing behavior lived across nested loops, provider callbacks, STT events, speculative tasks, and TTS tasks.

This document defines the session states, allowed transitions, and rules for speculation, barge-in, post-TTS listening, and shutdown.

## State Overview

```text
initializing
-> waiting_for_stream
-> listening
-> speculating
-> agent_running
-> speaking
-> post_tts_guard
-> listening
-> ending
-> ended
```

Error paths can move most active states to `recovering` or `ending`.

## States

### initializing

The CallSession has been created but provider stream context may not exist yet.

Allowed work:

- Load call context.
- Build agent configuration.
- Create runtime trace.
- Prepare STT/TTS/cache clients if needed.

Exit conditions:

- Move to `waiting_for_stream` when session dependencies are ready.
- Move to `ending` on unrecoverable setup failure.

### waiting_for_stream

The telephony WebSocket is connected but no valid provider stream id exists yet.

Allowed work:

- Receive provider lifecycle events.
- Accept WebSocket if adapter requires it.
- Start STT only if provider/audio path supports pre-stream audio.

Not allowed:

- Send assistant audio.
- Start TTS.
- Persist stream-connected lifecycle markers.

Exit conditions:

- Move to `listening` when adapter emits `stream_started`.
- Move to `ending` on provider stop/disconnect.

### listening

The runtime is receiving candidate audio and waiting for a possible turn boundary.

Allowed work:

- Stream inbound audio to STT.
- Collect interim/final transcript segments.
- Track speech activity.
- Detect echo.
- Detect tentative endpoint.

Exit conditions:

- Move to `speculating` when endpointing controller emits `tentative_turn`.
- Move to `speaking` only for a runtime-originated opener that does not depend on user input.
- Move to `ending` on provider stop or terminal failure.

### speculating

A tentative candidate turn exists and the runtime has started a speculative agent run.

Allowed work:

- Continue receiving audio.
- Continue receiving STT events.
- Start or continue speculative agent processing.
- Store speculative transcript/result only in memory.

Not allowed:

- Persist candidate turn as confirmed transcript.
- Execute tools.
- Send assistant audio.
- End the call based on speculative output.

Exit conditions:

- Move back to `listening` if new speech invalidates the tentative turn.
- Move to `agent_running` if turn is confirmed but agent result is not ready.
- Move to `speaking` if turn is confirmed and agent result is ready.
- Move to `ending` on provider stop or terminal failure.

### agent_running

The user turn is confirmed and an agent run is active or waiting to finish.

Allowed work:

- Persist confirmed user turn.
- Await existing speculative agent result if it matches the confirmed generation.
- Start a non-speculative agent run if no valid speculative run exists.
- Validate structured agent output.

Not allowed:

- Speak stale generation output.
- Execute tools from invalid agent output.

Exit conditions:

- Move to `speaking` when valid agent output is ready.
- Move to `recovering` on invalid output or timeout if recovery is possible.
- Move to `ending` on terminal agent action or unrecoverable failure.

### speaking

The runtime is sending assistant audio to telephony.

Allowed work:

- Persist assistant turn once selected for speaking.
- Resolve exact cached audio or live TTS.
- Send audio frames.
- Monitor inbound audio for barge-in.
- Mark first assistant audio.

Not allowed:

- Start another assistant response for an older generation.
- Fully trust VAD-only barge-in events.

Exit conditions:

- Move to `post_tts_guard` when assistant audio completes.
- Move to `listening` if confirmed barge-in cancels TTS.
- Move to `ending` if assistant action is `end_call_after_speaking`.
- Move to `recovering` on TTS failure if fallback is available.

### post_tts_guard

A short guard state immediately after assistant audio completes. This exists because real telephony providers may suppress or delay candidate speech immediately after TTS.

Allowed work:

- Keep STT open.
- Accept candidate speech aggressively.
- Suppress likely assistant echo.
- Avoid requiring a perfect `SpeechStarted` signal.
- Track inbound audio frames and transcript content.

Exit conditions:

- Move to `listening` after guard window expires.
- Move to `speculating` if a tentative user turn is detected.
- Move to `ending` if terminal action has already completed.

Recommended initial guard window:

```text
500ms to 1200ms, configurable after simulator and Exotel testing
```

### recovering

The runtime encountered a recoverable subsystem failure.

Examples:

- Agent invalid JSON.
- TTS provider failure with fallback available.
- STT transient disconnect with reconnect policy.

Allowed work:

- Emit trace event.
- Use recovery phrase if safe.
- Retry within bounded policy.
- Fall back to secondary TTS provider.

Exit conditions:

- Move to `speaking` if recovery response should be spoken.
- Move to `listening` if recovery does not require speaking.
- Move to `ending` if recovery fails or failure is terminal.

### ending

The runtime is shutting down the call.

Allowed work:

- Cancel active agent/TTS/STT tasks.
- Send final audio if action requires it and still possible.
- Close provider stream.
- Mark call finished.
- Flush trace.
- Persist cost/latency summary.

Exit conditions:

- Move to `ended`.

### ended

Terminal state. No runtime tasks should remain active.

Allowed work:

- None except final logging after cleanup.

## Generation IDs

Every candidate turn attempt receives a monotonically increasing generation id.

Generation id is attached to:

- Tentative transcript.
- Speculative agent run.
- Confirmed user turn.
- Agent result.
- Assistant TTS task.
- Trace events.

Rule:

```text
Only the latest confirmed generation is allowed to speak.
```

If generation 4 starts, generation 5 later confirms, and generation 4 returns after generation 5, generation 4 is discarded.

## Transition Rules

### Stream Start

```text
waiting_for_stream
-> stream_started
-> listening
```

Actions:

- Store stream id.
- Mark stream connected.
- Start continuous STT if not already active.
- Optionally speak opener.

### Tentative Endpoint

```text
listening
-> tentative_turn(generation_id, text)
-> speculating
```

Actions:

- Start speculative agent run.
- Do not persist transcript.
- Continue listening for new speech.

### Candidate Continues

```text
speculating
-> new_speech_for_same_turn
-> listening
```

Actions:

- Cancel speculative run if possible.
- Mark generation stale.
- Discard speculative result if it later returns.
- Continue transcript assembly.

### Turn Confirmed

```text
speculating
-> turn_confirmed(generation_id)
-> agent_running or speaking
```

Actions:

- Persist confirmed user turn.
- Reuse matching speculative result if ready.
- Await matching speculative result if running.
- Start fresh agent run if no valid speculative run exists.

### Assistant Response Ready

```text
agent_running
-> valid_agent_result(generation_id)
-> speaking
```

Actions:

- Validate structured output.
- Persist selected assistant text.
- Resolve audio source.
- Start TTS or cached playback.

### TTS Complete

```text
speaking
-> tts_complete
-> post_tts_guard
-> listening
```

Actions:

- Mark audio complete.
- Keep STT active.
- Watch for immediate candidate speech.

### Confirmed Barge-In

```text
speaking
-> confirmed_candidate_speech
-> listening
```

Actions:

- Cancel current TTS task.
- Send provider clear-audio event if supported.
- Mark assistant turn as interrupted in trace/metrics.
- Continue assembling candidate turn.

### End Call After Speaking

```text
speaking
-> tts_complete with action=end_call_after_speaking
-> ending
```

Actions:

- End provider call if supported.
- Mark call completed.
- Flush trace.

## Timing Model

The runtime must track separate clocks:

- Provider audio frame timestamps if available.
- Backend receive timestamps.
- STT event timestamps/audio offsets if available.
- Agent run start/end timestamps.
- TTS first byte and playback completion timestamps.

Rule:

```text
Do not infer real candidate silence solely from delayed STT event arrival time.
```

Endpoint confirmation should consider whether new inbound audio has arrived since the tentative endpoint, not just whether STT events were delayed.

## Barge-In Rules

VAD-only signal while speaking is not enough to cancel TTS.

Recommended flow:

```text
SpeechStarted while speaking
-> pending_barge_in
-> wait for transcript or strong audio evidence
-> if non-echo candidate content confirmed
-> cancel TTS
```

Cancellation is allowed earlier if inbound audio energy is strong and sustained, but that path must be traceable and tested.

## Echo Suppression Rules

During `speaking` and `post_tts_guard`, inbound transcript may contain assistant echo.

Runtime should compare inbound text against recent assistant spoken text.

Suppress only when:

- Similarity is high.
- Timing overlaps assistant playback or guard window.
- Transcript does not contain clear additional candidate content.

Never suppress short candidate confirmations such as:

```text
yes
okay
sure
no
repeat that
```

solely because they are short.

## Failure State Rules

### STT Failure

If STT fails before the call has useful interaction:

- Speak recovery message if TTS is available.
- End call gracefully.

If STT fails mid-call and reconnect is possible:

- Reconnect once or within bounded retry policy.
- Trace the gap.
- Continue only if transcript integrity is acceptable.

### Agent Failure

If agent output is invalid:

- Retry once with a repair instruction or structured-output retry.
- If still invalid, speak technical recovery and end gracefully.

### TTS Failure

If primary TTS fails:

- Use fallback provider if compatible.
- If fallback fails, end gracefully if possible.

### Provider Disconnect

Provider disconnect is terminal unless simulator explicitly supports reconnect.

## State Machine Test Requirements

Automated tests must cover:

- Normal call start to first assistant audio.
- Tentative endpoint cancelled by continued speech.
- Confirmed speculative result reused.
- Confirmed turn awaiting still-running speculative result.
- Stale generation result discarded.
- TTS complete into post-TTS guard.
- Candidate speech during post-TTS guard.
- VAD false positive during TTS does not cancel.
- Confirmed barge-in cancels TTS.
- Agent terminal action ends call after speaking.
- Provider stop cancels active tasks.

Manual simulator tests must cover:

- Candidate pauses mid-answer and continues.
- Candidate starts speaking immediately after assistant finishes.
- Candidate interrupts assistant.
- Candidate asks for question explanation.
- Candidate gives very short answer.
- Candidate rambles for a long time.
