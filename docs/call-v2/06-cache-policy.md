# Call V2 Cache Policy

## Purpose

Caching can reduce latency and cost, especially when many calls use the same question set. It can also make the system brittle if it starts reusing conversational decisions.

This document defines safe caching boundaries for v2.

## Core Rule

The cache is an audio delivery optimization.

It must never decide what the agent should say.

```text
agent chooses spoken_text
-> audio resolver checks whether exact approved audio exists for that exact text
-> cache hit speaks cached audio
-> cache miss uses live TTS
```

Not allowed:

```text
candidate said something similar
-> retrieve old response
-> speak old response
```

## Cache Layers

### Prompt Prefix Cache

Stable agent prompt sections may benefit from provider-side prompt caching.

Stable sections:

- Agent identity.
- Instructions.
- Scope.
- Tool schemas.
- Question set.
- Static job/company context.
- Response format instructions.

Dynamic sections:

- Latest user turn.
- Recent conversation.
- Runtime state.
- Tool results.

Prompt prefix caching is provider-dependent. It should be treated as a model optimization, not a correctness mechanism.

### Curated Audio Cache

Prebuilt before calls.

Good for:

- Consent opener variants.
- Known question set.
- Standard goodbye.
- Standard technical recovery message.
- Common neutral fillers.
- Common transitions.

This is the safest and highest-value cache for repeated recruitment calls.

### Runtime Memory Cache

Short-lived in-process cache.

Good for:

- Exact same TTS text repeated during the same process.
- Development and simulator runs.
- Temporary TTS retry protection.

Recommended:

- TTL minutes to hours.
- Not relied on for persistent latency guarantees.

### Persistent Runtime Cache

Allowed only for approved reusable categories.

Good for:

- Generic repeated assets.
- Approved exact text that contains no candidate-specific details.

Not allowed by default:

- Freeform candidate-specific follow-ups.
- Question explanations generated from candidate context.
- Anything containing candidate name.
- Anything referencing resume-specific facts.
- Anything based on a previous candidate answer.

## Cache Eligibility

### Cacheable Categories

Initial approved categories:

```text
consent_opener
known_question
standard_goodbye
technical_recovery
neutral_filler
standard_transition
```

Potential future categories:

```text
company_intro
scheduling_prompt
compliance_notice
```

### Non-Cacheable Categories

```text
candidate_specific_followup
question_explanation
clarification_response
objection_handling
conversation_summary
answer_reflection
tool_result_response
anything_with_candidate_data
```

Question explanations are intentionally non-cacheable at first. If a candidate asks, "Can you explain the question?", the agent should generate a fresh explanation from context and live TTS should speak it unless an exact approved template was intentionally created.

## Cache Key

Audio cache keys must include all factors that affect playback correctness.

```python
class AudioCacheKey:
    normalized_text_hash: str
    category: str
    tts_provider: str
    tts_model: str
    voice: str
    language: str
    speaking_style: str | None
    codec: str
    sample_rate_hz: int
    channels: int
    telephony_provider: str
    variant_id: str | None
    cache_schema_version: str
```

Important:

- Twilio mu-law audio and Exotel L16 audio are different cache entries.
- Different voices are different cache entries.
- Different TTS providers are different cache entries.
- Text normalization must be stable and conservative.

## Text Normalization

Normalize only for exact-intent equivalence.

Allowed normalization:

- Trim leading/trailing whitespace.
- Collapse repeated whitespace.
- Normalize smart quotes.
- Remove accidental role prefix if this is already part of TTS text cleanup.

Avoid:

- Semantic similarity.
- Paraphrase matching.
- Removing candidate names.
- Aggressive punctuation stripping that changes prosody.

The spoken text used for cache lookup should be the same text that would be sent to TTS after final TTS-safe cleanup.

## Cache Decision Flow

```text
AgentOutput(spoken_text, action)
-> classify cache eligibility
-> if category approved and no candidate-specific data
-> build exact AudioCacheKey
-> lookup audio
-> hit: play cached audio
-> miss: live TTS
-> optional: store only if policy allows
```

If classification is uncertain:

```text
do not persistently cache
```

## Candidate Data Detection

Persistent cache should reject text containing:

- Candidate name.
- Phone number.
- Email.
- Resume-specific project/company names unless explicitly approved.
- Previous answer content.
- Scheduling details specific to the candidate.

The first implementation can use conservative metadata rather than perfect NLP:

- Agent or resolver marks category.
- Known question assets are cacheable.
- Freeform agent outputs are not persistently cacheable.

## Variants

To avoid robotic repetition across many calls, curated audio may have variants.

Example:

```text
known_question:q3:variant_a
known_question:q3:variant_b
known_question:q3:variant_c
```

Variant rules:

- Variants must preserve meaning exactly.
- Variants should be curated or generated offline.
- Runtime may choose a variant deterministically or randomly.
- Variant selection should be traceable.

For exact question text, the safest v2 option is multiple TTS performances of the same text, not paraphrases.

## Cache Growth Policy

Use a hybrid model:

```text
fixed curated cache
+ controlled runtime cache
```

### Fixed Curated Cache

Stable assets generated before calls.

Regeneration requires an explicit cache build step.

### Controlled Runtime Cache

May grow slowly under strict rules.

Persistent storage requires:

- Approved category.
- No candidate-specific data.
- Exact text.
- Known voice/audio config.
- TTL or versioned invalidation.

Do not store every TTS output forever.

## TTL And Invalidation

Curated assets:

- Versioned by question set, voice, TTS model, and audio format.
- No short TTL required.
- Regenerated when source text, voice, model, codec, or speaking style changes.

Runtime persistent assets:

- Recommended TTL: 30 to 90 days.
- Invalidate on provider/model/voice changes.
- Invalidate on cache schema version changes.

Memory cache:

- Recommended TTL: process lifetime or a few hours.

## Relationship To LangChain

LangChain can help with prompt/model middleware and provider prompt caching. It should not be the main voice audio cache.

Recommended split:

- Use LangChain or provider features for stable prompt prefix caching where supported.
- Build application-level audio cache for exact approved spoken text.
- Do not use semantic LLM response cache for live conversation turns.

## Cache And Speculation

Speculative agent output can perform a cache lookup only after turn confirmation.

Allowed:

- Precompute possible cache key in memory.

Not allowed:

- Start audio playback.
- Persist runtime cache entry.
- Mark cache hit as used in durable metrics.

When generation confirms:

- Validate generation id and input fingerprint.
- Then resolve audio source.

## Cache And Manual Testing

The simulator should show cache decisions in trace:

```text
audio.source_selected generation_id=7 source=cache category=known_question key=...
audio.source_selected generation_id=8 source=live_tts reason=non_cacheable_category
```

Manual testers should be able to tell:

- Whether a response was cached.
- Whether cached audio felt natural.
- Whether live TTS fallback worked.

## Automated Test Cases

Required:

1. Known question exact text hits curated cache.
2. Same text with different codec misses.
3. Same text with different voice misses.
4. Candidate-specific text is not persistently cached.
5. Question explanation is live TTS by default.
6. Clarification response is live TTS by default.
7. Standard goodbye can hit cache.
8. Cache miss falls back to live TTS.
9. Live TTS failure can use fallback provider.
10. Speculative output cannot trigger playback before confirmation.

## Manual Test Cases

Required:

- Same question set across multiple simulator calls.
- Candidate asks for explanation of a cached question.
- Candidate asks to repeat a question.
- Candidate gives unusual answer causing fresh follow-up.
- Compare cached question audio vs live TTS naturalness.

## Success Criteria

The cache policy is successful when:

- Repeated known questions can be spoken with near-zero TTS latency.
- The agent still handles clarification and explanation naturally.
- Cache decisions are deterministic and traceable.
- Persistent cache does not accumulate candidate-specific data.
- Cache miss path is always safe and natural.
