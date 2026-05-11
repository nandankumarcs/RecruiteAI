# RecruiteAI — Cost Optimization Analysis
> **Filter applied:** Only providers with a free tier or free trial credits are included. OpenAI is already configured and kept as-is.

---

## Current Architecture & Cost Profile

Your system is built as a **custom Twilio ↔ OpenAI Realtime bridge**:

```
Recruiter Dashboard → Twilio (outbound PSTN call)
                         ↕ audio stream (WebSocket)
                    Your FastAPI backend
                         ↕ WebSocket
                    OpenAI Realtime API (gpt-4o-mini-realtime-preview)
```

Three additional AI workloads consume tokens too:
| Agent | Model Used | When |
|---|---|---|
| `ResumeParserAgent` | `gpt-4o` (OPENAI_MODEL) | Once per resume upload |
| `QuestionGeneratorAgent` | `gpt-4o` (OPENAI_MODEL) | Once per call start |
| `EvaluationAgent` | `gpt-4o` (OPENAI_MODEL) | Once per completed call |

---

## Current Cost Per 10-min Interview: ~$0.65

| Component | Cost |
|---|---|
| Twilio voice (10-min call) | $0.13 |
| GPT-4o-mini Realtime (audio tokens) | $0.35 |
| gpt-4o text agents (parse + Q-gen + eval) | $0.17 |
| **Total per candidate** | **~$0.65** |

---

## ✅ Eligible Alternatives (Free Tier / Free Credits Available)

### 1. Text AI Agents — Switch `gpt-4o` → `gpt-4o-mini`
> **You already have OpenAI. Zero new signup needed. ~$0.15/call savings.**

`gpt-4o-mini` is **15× cheaper** for structured JSON extraction tasks like resume parsing, question generation, and call evaluation. Quality difference is negligible for these structured tasks.

| Model | Input | Output |
|---|---|---|
| `gpt-4o` (current) | $5.00/1M tokens | $15.00/1M tokens |
| `gpt-4o-mini` | $0.15/1M tokens | $0.60/1M tokens |

**Savings: ~$0.15/call. 3-line code change. Do this today.**

---

### 2. Telephony — Plivo ✅ $10 Free Credits
> No credit card required to start.

- **Free signup credits:** $10 (no CC required)
- **Outbound US rate:** ~$0.009–$0.011/min (~30% cheaper than Twilio's $0.013)
- **TwiML-compatible:** Yes — your `RealtimeBridge` and webhook routes don't change
- **Migration:** Swap SDK import in `telephony.py`, update 3 env vars
- **Signup:** [plivo.com](https://plivo.com)

**$10 credit ≈ ~900 minutes of outbound calls to test with.**

---

### 3. Telephony — Telnyx ✅ ~$5 Free Credits + AI Startup Program
> Requires business email. Biggest long-term savings on telephony.

- **Free signup credits:** ~$5 on standard signup; up to **$20,000** via [Telnyx AI Accelerator](https://telnyx.com/ai-accelerator) for AI startups
- **Outbound US rate:** ~$0.007/min (~50% cheaper than Twilio)
- **TwiML-compatible:** Yes — same Media Stream WebSocket protocol
- **Migration:** Same as Plivo — swap SDK + 3 env vars
- **Signup:** [telnyx.com/sign-up](https://telnyx.com/sign-up)

> **Note:** Requires a business/professional email (Gmail/Yahoo not accepted).

---

### 4. Realtime Voice AI — Google Gemini Live API ✅ $300 Free Credits (90 days)
> Biggest potential cost reduction. 14× cheaper than OpenAI Realtime.

- **Free credits:** **$300** via Google Cloud free trial (90 days, new GCP accounts)
- **Also:** Free prototyping via [Google AI Studio](https://aistudio.google.com) — no billing needed at all for testing
- **Model:** `gemini-live-2.5-flash-native-audio`
- **Audio pricing vs OpenAI Realtime:**

| Direction | OpenAI gpt-4o-mini Realtime | Gemini Flash Live |
|---|---|---|
| Audio input | $10/1M tokens | ~$0.70/1M tokens |
| Audio output | $20/1M tokens | ~$1.40/1M tokens |
| **Cost per 10-min call** | **~$0.35** | **~$0.025** |

- **Compatibility:** Supports mulaw/PCMU audio (same as Twilio Media Streams), server-side VAD, bidirectional WebSocket
- **Migration effort:** Rewrite `realtime_bridge.py` to target Gemini WebSocket endpoint. The Twilio↔Backend layer (all of `twilio_webhooks.py` + `telephony.py`) stays unchanged.
- **Signup:** [console.cloud.google.com](https://console.cloud.google.com) (new account gets $300 free)

---

### 5. All-in-One Platform — Retell AI ✅ $10 Free Credits
> Drop-in managed alternative to your entire Twilio + Realtime bridge stack.

- **Free credits:** **$10** on signup + 20 free concurrent calls, 10 free knowledge bases
- **Fully loaded rate:** ~$0.07–$0.12/min (includes telephony + STT + LLM + TTS)
- **What you replace:** The entire `realtime_bridge.py` + `telephony.py` → ~10 lines of Retell API calls
- **What you keep:** Your `call_evaluation.py`, transcript storage, `calls.py` router (Retell sends webhooks with transcripts)
- **Tradeoff:** Less control over your custom consent state machine and conversation flow logic — would need to be re-expressed in Retell's agent prompt system
- **Signup:** [retellai.com](https://retellai.com)

---

### 6. All-in-One Platform — Vapi.ai ✅ $10 Free Credits
> Similar to Retell but more modular — bring your own LLM/voice providers.

- **Free credits:** **$10** on signup
- **Platform fee:** $0.05/min (orchestration only)
- **You still bring:** LLM + STT + TTS (can reuse your OpenAI key)
- **Fully loaded with OpenAI mini + Deepgram:** ~$0.09–$0.13/min estimated
- **Signup:** [vapi.ai](https://vapi.ai)

---

### 7. LLM for Text Tasks — Groq ✅ Permanently Free Tier (Rate-Limited)
> Use for question generation & evaluation instead of gpt-4o.

- **Free tier:** **Permanently free**, no credits, no expiry — just rate-limited
- **No credit card required**
- **Models:** Llama 3.3 70B, Llama 3.1 8B, Mixtral (open-source)
- **Speed:** Extremely fast inference (Groq's LPU hardware) — lower latency than OpenAI for text tasks
- **Use case in RecruiteAI:** Replace `gpt-4o` in `EvaluationAgent` and `QuestionGeneratorAgent` via `langchain-groq`
- **Signup:** [console.groq.com](https://console.groq.com)

> **Caveat:** Rate limits may be a bottleneck at high call volume; the free tier is best for low-to-medium load testing.

---

### 8. STT (if building modular pipeline) — Deepgram ✅ $200 Free Credits
> Only relevant if you build a custom STT+LLM+TTS pipeline instead of using OpenAI Realtime or Retell.

- **Free credits:** **$200** on signup (no credit card required)
- **Model:** Nova-3 (best accuracy/cost for real-time)
- **Rate:** ~$0.0043/min for streaming STT
- **$200 credit ≈ ~46,500 minutes of transcription** — extensive testing runway
- **Signup:** [deepgram.com](https://deepgram.com)

---

## ❌ Excluded (No Free Tier Confirmed)

| Provider | Reason |
|---|---|
| **SignalWire** | Only $5 trial credit; requires $5 top-up to exit trial mode — effectively not free |
| **Groq TTS / Cartesia** | No confirmed free tier for TTS at production quality |

---

## Recommended Test Sequence

```
Step 1 — Today (0 effort, uses existing OpenAI key)
────────────────────────────────────────────────────
✅ Switch gpt-4o → gpt-4o-mini in all 3 text agents
   → 3-line code change, ~$0.15/call saved immediately

Step 2 — This week (sign up for free credits)
─────────────────────────────────────────────
✅ Sign up for Plivo ($10 free) — test telephony swap
   → Verify TwiML webhook + Media Stream works end-to-end

Step 3 — Next week (biggest impact)
─────────────────────────────────────
✅ Sign up for Google Cloud ($300 free / 90 days)
   → Prototype Gemini Live bridge in a branch
   → OR sign up for Retell AI ($10 free) for a managed drop-in

Step 4 — Parallel testing
──────────────────────────
✅ Sign up for Groq (free forever)
   → Replace gpt-4o in evaluation + question agents
```

---

## Projected Savings Summary

| Action | Current | After | Saved |
|---|---|---|---|
| `gpt-4o` → `gpt-4o-mini` (text agents) | $0.17 | $0.02 | **$0.15** |
| Twilio → Plivo/Telnyx | $0.13 | $0.09 | **$0.04–$0.06** |
| OpenAI Realtime → Gemini Live | $0.35 | $0.025 | **$0.325** |
| **Total per 10-min interview** | **$0.65** | **~$0.085–$0.115** | **~82%** |

---

## Quick Code Change for Step 1 (gpt-4o → gpt-4o-mini)

**`app/config.py`** — add one line:
```python
OPENAI_MINI_MODEL: str = "gpt-4o-mini"
```

**`evaluation_agent.py`**, **`question_generator_agent.py`**, **`resume_parser_agent.py`** — change:
```python
# Before
llm = ChatOpenAI(model=settings.OPENAI_MODEL, ...)

# After
llm = ChatOpenAI(model=settings.OPENAI_MINI_MODEL, ...)
```
