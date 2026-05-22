# Call V2 Agent Contract

## Purpose

The call agent is the conversational brain of v2. It is general-purpose: recruitment screening is a configuration, not the runtime itself.

The agent receives instructions, scope, tools, context, past conversation, and the latest confirmed user turn. It returns a structured response that the runtime can validate and execute safely.

## Design Goals

- Let the agent decide the next natural spoken response.
- Support recruitment and future calling workflows.
- Avoid deterministic question sequencing in runtime code.
- Avoid fragile runtime heuristics based on assistant text.
- Make call control explicit through structured output.
- Support speculative execution without side effects.
- Keep low-level telephony, STT, TTS, and caching out of the agent.

## Agent Inputs

### AgentInput

```python
class AgentInput:
    call_id: str
    generation_id: int
    speculative: bool
    agent_config: AgentConfig
    call_state: AgentVisibleCallState
    conversation: list[ConversationMessage]
    latest_user_turn: ConversationMessage
    available_tools: list[ToolSpec]
```

### AgentConfig

```python
class AgentConfig:
    agent_name: str
    instructions: str
    scope: CallScope
    context: dict
    objectives: list[str]
    constraints: list[str]
    response_style: ResponseStyle
```

For recruitment, `context` may include:

```json
{
  "candidate": {
    "name": "Candidate name",
    "resume_summary": "...",
    "skills": []
  },
  "job": {
    "title": "...",
    "description": "...",
    "requirements": "..."
  },
  "questions": [
    {"id": "q1", "text": "...", "priority": 1}
  ],
  "company": {},
  "screening_rubric": {}
}
```

### CallScope

```python
class CallScope:
    purpose: str
    allowed_topics: list[str]
    disallowed_topics: list[str]
    compliance_notes: list[str]
    success_criteria: list[str]
```

Example:

```json
{
  "purpose": "Screen a candidate for a backend engineer role.",
  "allowed_topics": [
    "role fit",
    "technical experience",
    "project experience",
    "availability",
    "candidate questions about the screening"
  ],
  "disallowed_topics": [
    "medical advice",
    "legal advice",
    "salary negotiation beyond configured scope"
  ],
  "compliance_notes": [
    "Ask for consent before the screening conversation.",
    "End politely if the candidate refuses to continue."
  ],
  "success_criteria": [
    "Collect enough answers to evaluate the candidate against the role.",
    "Keep the call polite, concise, and natural."
  ]
}
```

### AgentVisibleCallState

```python
class AgentVisibleCallState:
    phase: str
    consent_status: str           # "unknown", "granted", "refused"
    previous_agent_action: str | None
    covered_items: list[str]
    open_items: list[str]
    last_assistant_message: str | None
    candidate_interrupted_last_turn: bool
    elapsed_call_seconds: int
```

The agent can see high-level state, but not raw provider details.

### ConversationMessage

```python
class ConversationMessage:
    role: str                     # "assistant", "user", "tool"
    content: str
    message_id: str
    generation_id: int | None
    committed: bool
    interrupted: bool
    created_at_ms: int
    metadata: dict
```

Only committed user turns should appear in normal agent history. Speculative runs receive the tentative latest user turn as input, but it must be marked by `speculative=True` at the `AgentInput` level.

## Agent Output

### AgentOutput

```python
class AgentOutput:
    spoken_text: str
    action: AgentAction
    tool_calls: list[ToolCall]
    state_updates: dict
    confidence: float | None
    internal_notes: str | None
```

Only `spoken_text`, `action`, `tool_calls`, and `state_updates` are machine-actionable. `internal_notes` are for trace/debug and should not be spoken.

### AgentAction

Initial actions:

```text
continue
pause_for_user
end_call_after_speaking
technical_recovery
```

Meanings:

- `continue`: speak `spoken_text`, then return to listening.
- `pause_for_user`: speak `spoken_text` if present, then listen without advancing any internal objective.
- `end_call_after_speaking`: speak `spoken_text`, then end the provider call.
- `technical_recovery`: runtime-selected or agent-selected recovery message for a non-business failure.

Do not add new actions casually. New actions require tests and runtime handling.

### ToolCall

```python
class ToolCall:
    tool_name: str
    arguments: dict
    call_id: str
```

Tool calls from speculative agent runs cannot execute. They may be stored in memory and executed only if the same generation is confirmed and output is still current.

## Structured Output Rules

The agent must return valid structured output.

Rules:

- `spoken_text` must be plain text intended for TTS.
- `spoken_text` must not include role labels like `Assistant:` or `Candidate:`.
- `spoken_text` must not include JSON, Markdown, or implementation notes.
- `action` must be one of the allowed actions.
- `tool_calls` must match declared tool schemas.
- If ending the call, `spoken_text` should contain the final message to speak before hangup.

If output is invalid:

1. Runtime retries once with a structured-output repair instruction.
2. If still invalid, runtime uses a technical recovery response and ends gracefully.

## Prompt Shape

The agent prompt should have stable and dynamic sections.

### Stable Prefix

Good candidate for provider prompt caching:

```text
agent identity
call purpose
scope
instructions
tool descriptions
response format
question set
static job/company context
```

### Dynamic Suffix

Changes every turn:

```text
call state
past conversation summary or recent turns
latest confirmed user turn
speculative flag
```

## System Prompt Requirements

The system/developer prompt should instruct the agent to:

- Behave like a professional calling agent.
- Follow the configured scope and instructions.
- Use the provided context and questions.
- Ask one thing at a time unless instructions say otherwise.
- Handle clarification naturally.
- Explain questions when asked.
- Respect refusal and end politely.
- Return structured output only.
- Avoid mentioning internal tools, cache, STT, TTS, or implementation details.
- Avoid inventing candidate or job facts.
- Keep spoken turns concise enough for a phone call.

## Recruitment Configuration

Recruitment should be expressed through `AgentConfig`, not runtime branches.

Example objectives:

```text
- Confirm consent to continue.
- Ask screening questions naturally.
- Ask follow-up questions when useful.
- Clarify or explain questions when the candidate asks.
- Collect enough signal for post-call evaluation.
- End politely if the candidate refuses or the call is complete.
```

Example constraints:

```text
- Do not ask interview questions before consent.
- Do not ask multiple unrelated questions in one turn.
- Do not provide hiring decisions.
- Do not discuss confidential company information.
- If the candidate asks to repeat, repeat or rephrase the current point.
```

## Tools

### Day-One Tool Policy

Keep executable tools minimal.

Recommended day-one tools:

```text
none, or internal-only state recording tools
```

The first implementation can support tool schemas in the contract without executing many real tools.

Allowed early internal tools:

- `record_screening_signal`
- `mark_candidate_concern`
- `mark_topic_covered`

These should be non-critical annotations. The call should still work if tool execution fails.

### Tool Execution Rules

- Never execute tools from speculative runs.
- Never execute unknown tool names.
- Validate arguments against schema.
- Tool failures should not crash the call.
- Tool results can be appended to conversation history only after confirmation.

## Speculative Agent Runs

For speculative runs:

- `AgentInput.speculative` is true.
- The agent receives tentative latest user text.
- The agent may produce a full output.
- Runtime stores output in memory only.
- Tool calls do not execute.
- Output does not reach TTS until turn confirmation.

If candidate continues:

- Runtime cancels the run if possible.
- If the model call cannot be cancelled, result is discarded by generation id.

If silence confirms:

- Runtime may reuse the speculative result if generation id and input fingerprint match.

## Input Fingerprint

Each agent run should include an `input_fingerprint`.

Fingerprint should include:

- Stable agent config version.
- Conversation message ids included.
- Latest user turn text hash.
- Generation id.
- Tool schema version.

Purpose:

- Prevent stale speculative result reuse.
- Make trace debugging easier.

## Agent Safety Boundaries

The agent cannot:

- Directly end the provider call.
- Send audio.
- Modify transcript history.
- Execute tools directly.
- Access raw audio.
- Decide cache hits.
- Override generation id rules.

It can request:

- `end_call_after_speaking`
- tool calls
- state updates

Runtime validates and applies those requests.

## Testing Requirements

Agent tests should run without telephony, STT, or TTS.

Golden cases:

- Consent opener.
- Candidate grants consent.
- Candidate refuses.
- Candidate asks who is calling.
- Candidate asks to repeat.
- Candidate asks to explain a question.
- Candidate gives short answer.
- Candidate gives long answer.
- Candidate asks off-scope question.
- Candidate interrupts or says they could not hear.
- Candidate completes all required scope.
- Agent returns terminal action with final spoken text.

Structured output tests:

- Valid JSON/output model accepted.
- Missing `spoken_text` rejected.
- Unknown action rejected.
- Tool call with invalid args rejected.
- Role-prefixed spoken text cleaned or rejected.

Speculation tests:

- Speculative output is not persisted.
- Speculative tool calls are not executed.
- Matching confirmed generation can reuse speculative output.
- Stale speculative output cannot speak.

## Success Criteria

The agent layer is successful when:

- The runtime can call it with no provider-specific context.
- It handles recruitment naturally through configuration.
- It produces structured output consistently.
- It can explain, repeat, redirect, and end without runtime text heuristics.
- It can run speculatively without side effects.
