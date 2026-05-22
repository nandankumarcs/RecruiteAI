# Call V2 Architecture And Principles

## Purpose

Call v2 replaces the current call runtime with a cleaner general-purpose calling agent architecture. Recruitment screening is the first use case, but the runtime should not be tightly coupled to recruitment-specific concepts.

The goal is to make the call pipeline easy to reason about, test, trace, and evolve without accumulating patch-on-patch logic.

## Product Shape

The v2 runtime is a general voice calling system:

```text
telephony audio in
-> normalized provider events
-> STT
-> endpointing and speculative turn controller
-> LLM call agent
-> TTS and audio source resolver
-> normalized provider audio out
```

The call agent receives instructions, scope, tools, questions, additional context, and conversation history. It decides the next spoken response. The runtime owns transport, timing, audio, cancellation, persistence, and safety boundaries.

## Primary Design Decisions

- V2 is the primary call implementation on this branch.
- We will not build a v1/v2 runtime toggle.
- We may keep narrow operational toggles for risky internal capabilities such as speculation and audio cache.
- Simulator/browser testing is the first execution target.
- Exotel follows after simulator confidence.
- Twilio follows after the core runtime has proven stable.
- The LLM agent owns conversation policy.
- The runtime owns lifecycle mechanics and must never infer call control from fragile text heuristics.
- Speculative processing is first-class, but speculative work cannot mutate durable state until confirmed.
- Caching is an audio delivery optimization, not a conversation decision mechanism.

## Core Components

### CallSession

Owns a single live call lifecycle.

Responsibilities:

- Session state machine.
- Current stream identifiers.
- Current turn generation id.
- Cancellation of stale agent and TTS tasks.
- Wiring between telephony, STT, endpointing, agent, TTS, cache, and persistence.
- Emitting trace events.

Non-responsibilities:

- Provider-specific message formats.
- STT provider-specific event interpretation.
- Business-specific conversation decisions.
- TTS provider implementation details.

### TelephonyAdapter

Normalizes provider WebSocket events into v2 domain events.

Adapters:

- Browser/simulator adapter.
- Exotel adapter.
- Twilio adapter later.

Responsibilities:

- Parse provider start/media/stop/control events.
- Track provider stream id and provider call id.
- Normalize inbound audio frame metadata.
- Send outbound audio/control events in provider format.
- Hide provider-specific quirks from the rest of the runtime.

### AudioCodec

Handles format boundaries explicitly.

Responsibilities:

- Mu-law vs L16 conversion.
- Sample rate assumptions.
- Frame sizing.
- Provider output format validation.

Rule: codec conversion should not be hidden inside STT, TTS, or agent logic.

### STTEngine

Consumes normalized audio frames and emits transcript events.

Responsibilities:

- Connect to STT provider.
- Stream audio.
- Emit interim, tentative, final, VAD, and provider lifecycle events.
- Preserve provider timing metadata when available.

### EndpointingController

Owns turn detection and speculative processing decisions.

Responsibilities:

- Decide when a tentative turn begins.
- Start speculative agent processing after configured silence.
- Cancel stale speculation when candidate continues.
- Confirm a turn only after the confirmation policy passes.
- Emit confirmed turns to the agent/session.

Critical rule: only confirmed turns become durable transcript history.

### CallAgent

General-purpose LLM calling agent.

Inputs:

- Agent instructions.
- Call scope.
- Context bundle.
- Tool definitions.
- Past conversation.
- Latest confirmed user turn.

Output:

- Structured agent result with spoken text, action, optional tool calls, and metadata.

The agent can decide question order, follow-ups, clarification, redirection, and end-call behavior based on its instructions and context.

### AudioSourceResolver

Chooses how to produce assistant audio.

Priority:

1. Approved exact cached audio hit.
2. Optional approved filler or transition asset.
3. Live TTS.

Rule: the resolver never changes what the agent decided to say. It only decides how to speak that exact text.

### TTSEngine

Converts spoken text into provider-ready audio.

Responsibilities:

- Live synthesis.
- Streaming or non-streaming provider handling.
- Chunk pacing.
- Cancellation on barge-in or stale generation.
- Provider format compatibility.

### Persistence

Persists durable call data.

Responsibilities:

- Confirmed user turns.
- Assistant turns that were actually selected for speaking.
- Call lifecycle status.
- Recording metadata.
- Cost and latency metrics.
- Trace identifiers for debugging.

Rule: persistence should be idempotent and keyed by stable generation/message ids.

### TraceLogger

Produces a structured runtime trace for every simulator and live call.

Trace events must show:

- Provider events.
- STT events.
- Endpointing decisions.
- Speculation lifecycle.
- Agent run lifecycle.
- Cache decisions.
- TTS lifecycle.
- Barge-in/cancel behavior.
- Persistence commits.

The trace is a required debugging artifact, not optional logging.

## Runtime Boundary Rules

### Agent Boundary

The agent decides content and call intent.

The runtime enforces mechanical safety:

- Only latest confirmed generation can speak.
- Speculative outputs cannot speak until confirmed.
- Tool calls cannot execute from speculative runs.
- End call only via structured action or runtime failure policy.
- Invalid agent output triggers recovery behavior.

### Cache Boundary

The cache never decides the conversation.

Allowed:

- Exact approved audio asset for exact spoken text and compatible voice/audio config.

Not allowed:

- Semantic reuse of similar previous responses.
- Persistent caching of candidate-specific responses.
- Cache-based substitution of explanations, follow-ups, or context-sensitive text.

### Speculation Boundary

Speculative agent runs may read context but cannot:

- Persist transcript.
- Update call state.
- Execute tools.
- Start TTS.
- End the call.
- Mark questions as covered.

Speculative result becomes eligible only when the endpointing controller confirms the same generation.

### Provider Boundary

Provider quirks must remain inside adapters and codec modules.

Examples:

- Exotel stream id shape.
- Exotel post-TTS speech suppression behavior.
- Twilio media payload format.
- Browser simulator message format.

## Development Philosophy

V2 will be built through gated slices, not one large call loop.

Implementation should be collaborative, but not blindly reactive. Any requested change should be evaluated against the v2 architecture, current phase, testing gates, and long-term maintainability before implementation. If a request would cause drift, add brittle layering, skip a required gate, or belongs in a later phase, the implementer should push back, explain the tradeoff, and propose the safer path.

Refactoring is allowed and expected when it improves the overall system. If feature B requires feature A to be significantly refactored so the final architecture is cleaner, faster, or less brittle, we should refactor A rather than layering awkward compatibility code on top of it.

The condition is strict regression discipline:

- Existing behavior owned by A must have tests or simulator coverage before the refactor lands.
- The refactor must preserve or intentionally improve A's public contract.
- Regressions must be caught at module and seam gates, not discovered later in a full live call.

Stale code should not be left behind. When code changes make an old block, branch, helper, flag, or workaround obsolete, remove it in the same phase unless there is a documented migration reason to keep it temporarily.

Each module needs:

- Unit tests.
- Fixture or simulator tests.
- Seam tests with its downstream neighbor.
- Manual test checklist when audio/timing behavior is involved.

A module is not done until its important downstream seam has passed.

## First Execution Path

Initial v2 target:

```text
browser/simulator
-> normalized audio events
-> STT fixture or Deepgram test mode
-> endpointing with speculation
-> general CallAgent
-> mocked or live TTS
-> normalized outbound audio
```

Then:

```text
Exotel
-> Deepgram STT
-> CallAgent
-> Sarvam or Deepgram TTS
```

Twilio comes after the runtime behavior is stable with simulator and Exotel.

## Non-Goals For The First Implementation

- Full backward compatibility with v1 internals.
- A second v1/v2 runtime toggle.
- Keeping stale v1 code paths alive as informal fallbacks.
- Semantic caching of LLM responses.
- Large tool ecosystem on day one.
- Reusing v1 giant runtime loops.
- Optimizing cost before correctness and debuggability are proven.

## Success Criteria

V2 is successful when:

- The call pipeline can be explained from trace events.
- Speculative processing reduces latency without interrupting candidates.
- Candidate speech immediately after TTS is captured reliably in simulator and live provider tests.
- Stale agent or TTS outputs cannot leak into the call.
- Exact audio cache hits reduce latency without changing agent behavior.
- The agent can handle clarification, refusal, follow-up, and question explanation naturally.
- New telephony providers can be added through adapters without changing agent or STT logic.
- Necessary refactors are made deliberately with regression coverage.
- Obsolete code paths are removed or explicitly documented as temporary migration code.
