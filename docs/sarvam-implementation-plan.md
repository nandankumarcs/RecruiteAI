# Sarvam Implementation Plan

## Goal

Replace the current American-sounding TTS voice in the `deepgram_openai` runtime with English spoken in an Indian accent, while keeping:

- Exotel as the telephony provider
- OpenAI as the turn/reasoning engine
- the current call orchestration and transcript flow intact

The first rollout target is:

- Deepgram STT
- Sarvam TTS
- Exotel telephony

This is scoped to the live Exotel call path already verified on `feat/exotel-implementation`.

## Executive Summary

Sarvam is now the preferred first implementation path over DesiVocal for this repo.

Why:

- we verified that Sarvam can produce `en-IN` speech
- we verified live TTS responses at `8000 Hz`, mono, telephony-friendly PCM
- we verified live HTTP streaming output with `Content-Type: audio/pcm`
- we observed a promising first-byte time of about `0.443s` on the HTTP streaming endpoint when requesting `linear16`

DesiVocal still remains a plausible accent-first option, but it is now clearly the second choice for the current call architecture because:

- it returns `s3_path` indirection instead of immediate audio
- it needs a generate-then-download flow
- its voice outputs varied by format and sample rate across voices

## Current State In This Repo

The current speech pipeline is split across three responsibilities:

- Telephony transport:
  - Exotel for outbound call setup and media streaming
  - Relevant files:
    - [backend/app/services/telephony.py](/Users/mac/RecruiteAI/backend/app/services/telephony.py)
    - [backend/app/main.py](/Users/mac/RecruiteAI/backend/app/main.py)
- Voice runtime orchestration:
  - `VOICE_RUNTIME=deepgram_openai`
  - Dispatcher lives in [backend/app/services/voice_runtime.py](/Users/mac/RecruiteAI/backend/app/services/voice_runtime.py)
- STT + TTS + LLM turn handling:
  - Deepgram STT websocket
  - OpenAI text turn generation
  - Deepgram TTS inside `_speak_text`
  - Main runtime file: [backend/app/services/deepgram_runtime.py](/Users/mac/RecruiteAI/backend/app/services/deepgram_runtime.py)

The current TTS behavior is tightly coupled to Deepgram:

- it reads `DEEPGRAM_API_KEY` and `DEEPGRAM_TTS_MODEL`
- it calls Deepgram’s speak API
- it expects audio bytes back quickly
- it chunks returned audio into:
  - `1600` byte chunks for Exotel `linear16`
  - `400` byte chunks for Twilio `mulaw`

Key code points:

- TTS generation entrypoint:
  - [backend/app/services/deepgram_runtime.py](/Users/mac/RecruiteAI/backend/app/services/deepgram_runtime.py)
- Pricing helpers:
  - [backend/app/services/pricing.py](/Users/mac/RecruiteAI/backend/app/services/pricing.py)
- Runtime selection:
  - [backend/app/services/voice_runtime.py](/Users/mac/RecruiteAI/backend/app/services/voice_runtime.py)
- Config:
  - [backend/app/config.py](/Users/mac/RecruiteAI/backend/app/config.py)

## Sarvam Docs We Could Verify

### Official docs pages

- Docs home:
  - <https://docs.sarvam.ai/api-reference-docs/getting-started/welcome>
- REST TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert>
- HTTP streaming TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert-stream>
- WebSocket TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/stream>
- Pricing:
  - <https://docs.sarvam.ai/api-reference-docs/pricing>
- Product pricing page:
  - <https://www.sarvam.ai/api-pricing>

### Published API contracts

- OpenAPI JSON:
  - <https://docs.sarvam.ai/openapi.json>
- AsyncAPI JSON:
  - <https://docs.sarvam.ai/asyncapi.json>

From those docs and specs, we could verify:

- REST TTS endpoint exists at `/text-to-speech`
- HTTP streamed TTS endpoint exists at `/text-to-speech/stream`
- WebSocket TTS endpoint exists at `/text-to-speech/ws`
- auth header is `api-subscription-key` / `Api-Subscription-Key`
- `en-IN` is supported
- `bulbul:v3` is the preferred modern TTS model
- REST TTS supports:
  - `speech_sample_rate`
  - `output_audio_codec`
  - `speaker`
  - `pace`
  - `temperature`
  - pronunciation dictionaries via `dict_id`

## Validated Live API Findings

I tested Sarvam live with a real API key from this workspace session.

### Finding 1: REST TTS can produce Exotel-friendly audio directly

Verified request shape:

- `target_language_code=en-IN`
- `model=bulbul:v3`
- `speaker=shubh`
- `speech_sample_rate=8000`
- `output_audio_codec=linear16`

Observed result:

- request succeeded with `HTTP 200`
- response was JSON with base64 audio
- decoded output was raw PCM bytes compatible with a `linear16` flow

This matters because it means Sarvam can target telephony output directly instead of forcing us through a separate normalization pipeline.

### Finding 2: HTTP streaming is the strongest first integration target

I tested `POST /text-to-speech/stream` with:

- `target_language_code=en-IN`
- `model=bulbul:v3`
- `speaker=shubh`
- `speech_sample_rate=8000`
- `output_audio_codec=linear16`

Observed result:

- `HTTP 200`
- `Content-Type: audio/pcm`
- first byte arrived in about `0.443s`

This is the most important live finding in the whole comparison, because it makes Sarvam materially more suitable than DesiVocal for a conversational phone agent.

### Finding 3: WAV output also works cleanly

I also tested the HTTP stream endpoint with:

- `output_audio_codec=wav`
- `speech_sample_rate=8000`

Observed result:

- `Content-Type: audio/wav`
- file decoded as:
  - `pcm_s16le`
  - `8000 Hz`
  - mono

This gives us a simple fallback debug format for local validation.

### Finding 4: WebSocket docs are promising, but the live shape still needs care

Sarvam publishes an AsyncAPI schema and a WebSocket TTS endpoint, and the docs position it for conversational agents.

However, my first live direct WebSocket probes returned:

- `422`
- message:
  - `Input parameters has to be a valid dictionary`

Even after following the published message envelope closely, the live WS path did not become plug-and-play immediately.

This does **not** block a Sarvam rollout, because the HTTP streaming endpoint is already viable. It does mean we should avoid designing the first implementation around Sarvam WebSocket until we have a clean, repeatable local probe or switch to Sarvam’s SDK for that path.

## Cost Comparison

### Sarvam

Current published pricing:

- `Bulbul v2`: `₹15 / 10K chars`
- `Bulbul v3`: `₹30 / 10K chars`
- STT: `₹30 / hour`

### Deepgram

Current published pricing:

- `Aura-1`: `$0.015 / 1K chars`
- `Aura-2`: `$0.030 / 1K chars`
- streaming STT `Nova-3`: `$0.0048 / min`
- streaming STT `Flux`: `$0.0065 / min`

### Interpretation

For TTS:

- Sarvam is cheaper than Deepgram TTS
- Sarvam is also a better accent fit for the India-focused recruiter use case

For STT:

- Sarvam STT is plausible, but the strongest low-risk move is still to keep Deepgram STT first and replace only TTS

## Recommended Architecture

### Recommendation

Do **not** replace the whole speech stack at once.

Instead:

1. keep Deepgram STT
2. add a TTS provider abstraction
3. implement Sarvam as the first alternative provider
4. use Sarvam HTTP streaming first
5. keep Deepgram TTS as fallback

### Why this is the right shape

- the surrounding runtime already works on live Exotel calls
- the main change needed is TTS byte production, not conversation orchestration
- Sarvam’s verified `linear16` and streaming behavior let us avoid the heavy normalization path that DesiVocal would require
- fallback is easy if the first production calls reveal latency or quality issues

## Implementation Plan

### Phase 1: Add config for TTS provider selection

Update [backend/app/config.py](/Users/mac/RecruiteAI/backend/app/config.py) with:

- `TTS_PROVIDER: str = "deepgram"`
- `SARVAM_API_KEY: str = ""`
- `SARVAM_TTS_MODEL: str = "bulbul:v3"`
- `SARVAM_TTS_SPEAKER: str = "shubh"`
- `SARVAM_TTS_LANGUAGE: str = "en-IN"`
- `SARVAM_TTS_SAMPLE_RATE: int = 8000`
- `SARVAM_TTS_CODEC: str = "linear16"`
- `SARVAM_TTS_USE_HTTP_STREAM: bool = True`
- `SARVAM_ESTIMATED_COST_INR_PER_10K_CHARS: float = 30.0`

Update [backend/.env.example](/Users/mac/RecruiteAI/backend/.env.example) with matching keys and comments.

Recommended default:

- keep `TTS_PROVIDER=deepgram` by default in committed config
- enable Sarvam only in local/staging env first

### Phase 2: Introduce a small TTS provider abstraction

Add a new module, for example:

- `backend/app/services/tts_providers.py`

Suggested interface:

```python
class BaseTTSProvider(Protocol):
    provider_name: str

    async def synthesize(
        self,
        *,
        text: str,
        telephony_provider: str,
    ) -> bytes:
        ...
```

Implement:

- `DeepgramTTSProvider`
- `SarvamTTSProvider`

Keep target audio expectations explicit:

- Exotel:
  - `linear16`
  - mono
  - `8000 Hz`
- Twilio:
  - either `mulaw`, `8000 Hz`
  - or keep Twilio on Deepgram initially and scope Sarvam rollout to Exotel first

### Phase 3: Move current Deepgram logic behind the provider

Refactor [backend/app/services/deepgram_runtime.py](/Users/mac/RecruiteAI/backend/app/services/deepgram_runtime.py):

- extract the current Deepgram TTS logic from `_speak_text`
- route all synthesis through the provider abstraction
- preserve:
  - chunking logic
  - websocket pacing
  - `first_assistant_audio_at`
  - interruption cancellation
  - existing transcript and latency instrumentation

This phase should be a structural refactor with no behavior change while `TTS_PROVIDER=deepgram`.

### Phase 4: Implement `SarvamTTSProvider`

First implementation target:

- `POST https://api.sarvam.ai/text-to-speech/stream`

Headers:

- `api-subscription-key`
- `Content-Type: application/json`

Initial request body:

```json
{
  "text": "Hello Rahul, this is a quick test from our recruitment team.",
  "target_language_code": "en-IN",
  "speaker": "shubh",
  "model": "bulbul:v3",
  "speech_sample_rate": 8000,
  "output_audio_codec": "linear16",
  "pace": 1.0
}
```

Implementation notes:

- consume the streamed HTTP body incrementally
- return raw PCM bytes to the existing Exotel chunking path
- avoid unnecessary transcoding if Sarvam already returns the desired format
- preserve a small adapter boundary so we can swap in WebSocket later if it proves cleaner

### Phase 5: Keep a normalization fallback, but not on the hot path

Sarvam likely lets us avoid normalization for the Exotel path, but the provider should still be able to normalize when needed.

Recommended use:

- primary path:
  - direct `linear16`, `8000 Hz` from Sarvam
- fallback/debug path:
  - accept `wav` or other supported codecs
  - normalize with `ffmpeg` only if the runtime receives an unexpected format

Suggested fallback conversion shape:

```bash
ffmpeg -i input_anything -ac 1 -ar 8000 -f s16le output.raw
```

This is a safeguard, not the intended steady-state path.

### Phase 6: Fallback behavior

Add guarded fallback behavior:

- if `TTS_PROVIDER=sarvam` and synthesis fails:
  - log provider-specific failure detail
  - fall back to Deepgram TTS for the current turn

Recommended first rollout:

- fallback enabled
- provider tagged in logs
- explicit metrics for:
  - Sarvam success
  - fallback count
  - time to first audio

### Phase 7: Pricing and observability

Update [backend/app/services/pricing.py](/Users/mac/RecruiteAI/backend/app/services/pricing.py):

- add Sarvam TTS cost estimation
- add provider-tagged cost output

Track at minimum:

- `telephony_provider=exotel`
- `voice_runtime=deepgram_openai`
- `tts_provider=sarvam`
- chars synthesized
- estimated TTS cost
- time-to-first-audio
- total TTS generation time
- fallback activation

### Phase 8: Tests

Add unit tests for:

- provider selection from config
- Sarvam request payload generation
- fallback to Deepgram when Sarvam fails
- correct handling of streamed PCM responses

Likely files:

- `backend/tests/test_tts_providers.py`
- extend `backend/tests/test_telephony_provider.py` only if needed for config interplay

Also add a focused runtime smoke test that verifies:

- Exotel path still emits the expected websocket payload shape
- Sarvam provider output is chunked correctly into the current Exotel media send loop

## Rollout Plan

### Step 1: Build behind a feature flag

Set:

- `TTS_PROVIDER=sarvam`

only in local or staging first.

### Step 2: Use one first-rollout voice

Recommended initial voice:

- `shubh`

Why:

- verified live against `bulbul:v3`
- works with `en-IN`
- already usable in the documented request shape

After first verification, compare with one or two additional speakers if needed.

### Step 3: Live Exotel test

Repeat the same end-to-end validation pattern we used for the Exotel fix:

1. start backend
2. start frontend
3. confirm public tunnel URL
4. place a real Exotel call
5. verify:
   - greeting reaches candidate
   - Indian-accent English is intelligible
   - pronunciation of names sounds acceptable
   - barge-in still works
   - transcript persistence still works
   - no premature disconnect

### Step 4: Keep Deepgram as fallback until stable

Do not remove Deepgram TTS immediately.

We should keep a rollback path until we are satisfied with:

- voice quality
- latency under repeated turns
- reliability across multiple calls

## Risks

### Risk 1: WebSocket docs and live behavior do not line up perfectly yet

The published WebSocket schema looks mature, but the direct probe still returned a `422`.

Mitigation:

- use HTTP streaming first
- treat WebSocket as a later optimization
- optionally test Sarvam’s official SDK before attempting a direct WS integration

### Risk 2: Live latency may vary by prompt length

The promising `0.443s` first-byte result came from a short prompt. Longer recruiter utterances may still behave differently.

Mitigation:

- benchmark greeting-length, question-length, and follow-up-length prompts
- log time-to-first-audio and total synthesis time separately

### Risk 3: Voice quality is still partly subjective

Even if the API behavior is strong, we still need to validate recruiter-style English, Indian names, and mild Hinglish on real calls.

Mitigation:

- run real call tests with representative scripts
- keep speaker configurable
- compare at least two speakers before locking the default

### Risk 4: Twilio support may need separate handling

Sarvam is a clear fit for Exotel with `linear16`. Twilio may need either `mulaw` output or a conversion shim, depending on how we want to scope the first rollout.

Mitigation:

- scope the first Sarvam rollout to Exotel
- leave Twilio on Deepgram initially if we want the smallest safe change

## Recommended First Build Scope

The smallest safe first implementation is:

1. add `TTS_PROVIDER` and Sarvam config
2. extract current Deepgram TTS into a provider class
3. add `SarvamTTSProvider`
4. support Exotel first
5. use Sarvam HTTP streaming endpoint
6. request `linear16`, `8000 Hz`, mono-compatible output
7. keep Deepgram fallback enabled

I would avoid replacing STT in the first pass. The live data now supports a narrower, safer rollout that should materially improve accent fit without destabilizing the rest of the call stack.

## References

- Sarvam docs home:
  - <https://docs.sarvam.ai/api-reference-docs/getting-started/welcome>
- Sarvam REST TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert>
- Sarvam HTTP stream TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert-stream>
- Sarvam WebSocket TTS:
  - <https://docs.sarvam.ai/api-reference-docs/text-to-speech/stream>
- Sarvam pricing docs:
  - <https://docs.sarvam.ai/api-reference-docs/pricing>
- Sarvam pricing page:
  - <https://www.sarvam.ai/api-pricing>
- OpenAPI spec:
  - <https://docs.sarvam.ai/openapi.json>
- AsyncAPI spec:
  - <https://docs.sarvam.ai/asyncapi.json>
- Deepgram TTS models:
  - <https://developers.deepgram.com/docs/tts-models>
- Deepgram pricing:
  - <https://deepgram.com/pricing>

## Note On Context7

Per repo instructions, I used Context7 first for Sarvam and Deepgram docs lookup. The plan above then combines those doc results with direct official specs and live API probes done from this workspace session.
