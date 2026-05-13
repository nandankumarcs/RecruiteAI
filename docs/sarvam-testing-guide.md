# Sarvam TTS Testing Guide

## Quick Start

### Prerequisites
1. Sarvam API key from https://www.sarvam.ai/
2. Exotel account configured
3. Backend running with `VOICE_RUNTIME=deepgram_openai`

### Enable Sarvam TTS

Add to `backend/.env`:
```bash
# Switch to Sarvam TTS
TTS_PROVIDER=sarvam
SARVAM_API_KEY=your-api-key-here

# Ensure using Exotel
TELEPHONY_PROVIDER=exotel
VOICE_RUNTIME=deepgram_openai

# Optional: Customize voice
SARVAM_TTS_SPEAKER=shubh
SARVAM_TTS_MODEL=bulbul:v3
```

Restart backend:
```bash
cd backend
uvicorn app.main:app --reload
```

## Test Scenarios

### Test 1: Basic TTS Synthesis
**Goal:** Verify Sarvam can generate audio

**Steps:**
1. Start backend with `TTS_PROVIDER=sarvam`
2. Check logs for: `Requesting TTS from sarvam...`
3. Place a test call
4. Listen for Indian-accented English

**Expected:**
- Logs show: `[xxx] Sarvam TTS complete: N bytes`
- Audio plays with Indian accent
- No errors in logs

**If Failed:**
- Check logs for: `Sarvam TTS failed: ...`
- Should see: `Falling back to deepgram...`
- Audio should still play (American accent)

### Test 2: Fallback Behavior
**Goal:** Verify automatic fallback to Deepgram

**Steps:**
1. Use invalid Sarvam API key
2. Place test call
3. Check logs

**Expected:**
- Logs show: `Sarvam TTS failed: ...`
- Logs show: `Falling back to deepgram...`
- Logs show: `Fallback TTS success: N bytes`
- Call continues normally with Deepgram voice

### Test 3: Indian Name Pronunciation
**Goal:** Verify accent quality for Indian names

**Test Names:**
- Rahul
- Priya
- Arjun
- Ananya
- Vikram

**Steps:**
1. Create test job with Indian candidate names
2. Place call
3. Listen to greeting

**Expected:**
- Names pronounced with natural Indian accent
- Clear and intelligible
- No awkward pauses or mispronunciations

### Test 4: Barge-in/Interruption
**Goal:** Verify interruption handling still works

**Steps:**
1. Place call with Sarvam TTS
2. Wait for assistant to start speaking
3. Interrupt by speaking
4. Check if assistant stops

**Expected:**
- Assistant stops speaking when interrupted
- Logs show: `Confirmed barge-in from transcript...`
- User speech is processed correctly

### Test 5: Cost Tracking
**Goal:** Verify costs are tracked correctly

**Steps:**
1. Place complete call with Sarvam
2. Check database: `calls` table
3. Inspect `cost_breakdown` JSON field

**Expected:**
```json
{
  "currency": "USD",
  "provider": "exotel",
  "costs": {
    "llm_usd": 0.00123,
    "stt_usd": 0.00456,
    "tts_usd": 0.00036,
    "telephony_usd": 0.00789
  },
  "estimated_total_usd": 0.01404
}
```

### Test 6: Latency Comparison
**Goal:** Compare Sarvam vs Deepgram latency

**Steps:**
1. Place call with `TTS_PROVIDER=deepgram`
2. Note time to first audio in logs
3. Place call with `TTS_PROVIDER=sarvam`
4. Note time to first audio in logs
5. Compare

**Expected:**
- Sarvam: ~0.4-0.6s to first byte (based on plan)
- Deepgram: baseline comparison
- Both should feel responsive

### Test 7: Long Utterances
**Goal:** Verify Sarvam handles longer text

**Test Texts:**
- Short: "Hello, this is a test."
- Medium: "Hello Rahul, thank you for taking the time to speak with me today. I'm calling from the recruitment team at TechCorp."
- Long: Full job description or multi-sentence question

**Expected:**
- All lengths synthesize successfully
- No timeouts
- Audio quality consistent

## Monitoring

### Key Log Patterns

**Success:**
```
[abc123] Starting TTS for text: Hello Rahul...
[abc123] Requesting TTS from sarvam...
[abc123] Sarvam TTS success: 12800 bytes
[abc123] Sending 12800 audio bytes in chunks...
[abc123] TTS complete. Sent 8 chunks.
```

**Fallback:**
```
[abc123] Sarvam TTS failed: ...
[abc123] Falling back to deepgram...
[abc123] Fallback TTS success: 12800 bytes
```

**Error:**
```
[abc123] Sarvam TTS failed: ...
[abc123] Fallback TTS also failed: ...
[abc123] FATAL ERROR in _speak_text: ...
```

### Database Queries

**Check recent calls:**
```sql
SELECT 
  id,
  status,
  duration_seconds,
  cost_breakdown->'costs'->>'tts_usd' as tts_cost,
  cost_breakdown->'estimated_total_usd' as total_cost
FROM calls
ORDER BY created_at DESC
LIMIT 10;
```

**Check TTS provider usage:**
```sql
SELECT 
  cost_breakdown->>'provider' as telephony_provider,
  COUNT(*) as call_count,
  AVG((cost_breakdown->'costs'->>'tts_usd')::float) as avg_tts_cost
FROM calls
WHERE cost_breakdown IS NOT NULL
GROUP BY cost_breakdown->>'provider';
```

## Troubleshooting

### Issue: No audio plays
**Check:**
1. Is `SARVAM_API_KEY` set correctly?
2. Is `TELEPHONY_PROVIDER=exotel`?
3. Check logs for error messages
4. Verify fallback is working

**Solution:**
- If Sarvam fails, fallback should activate
- If both fail, check API keys

### Issue: Audio is choppy
**Check:**
1. Network latency to Sarvam API
2. Chunk size and pacing settings
3. WebSocket connection stability

**Solution:**
- Current settings: 1600 byte chunks, 0.095s pacing
- May need tuning based on network conditions

### Issue: Wrong accent (American instead of Indian)
**Check:**
1. Is `TTS_PROVIDER=sarvam` in .env?
2. Did backend restart after changing .env?
3. Check logs - is Sarvam being called?

**Solution:**
- Verify config: `echo $TTS_PROVIDER`
- Restart backend
- Check logs for "Requesting TTS from sarvam"

### Issue: Costs seem wrong
**Check:**
1. Verify `SARVAM_ESTIMATED_COST_INR_PER_10K_CHARS=30.0`
2. Check INR→USD conversion rate (currently 0.012)
3. Compare with actual Sarvam invoice

**Solution:**
- Adjust conversion rate in `pricing.py` if needed
- Update cost estimate in config

### Issue: Fallback not working
**Check:**
1. Is `DEEPGRAM_API_KEY` set?
2. Check logs for "Falling back to deepgram"
3. Verify DeepgramTTSProvider initialization

**Solution:**
- Ensure Deepgram key is valid
- Check fallback provider initialization in runtime

## Performance Benchmarks

### Target Metrics
- **Time to First Byte:** < 0.5s
- **Total Synthesis Time:** < 2s for typical utterance
- **Audio Quality:** Clear, natural Indian accent
- **Reliability:** > 99% success rate
- **Fallback Rate:** < 1% of calls

### How to Measure

**Latency:**
```python
# Check logs for timestamps
[abc123] Starting TTS for text: ...  # T0
[abc123] Sarvam TTS complete: ...    # T1
# Latency = T1 - T0
```

**Success Rate:**
```sql
SELECT 
  COUNT(*) FILTER (WHERE cost_breakdown->'costs'->>'tts_usd' IS NOT NULL) as successful,
  COUNT(*) as total,
  (COUNT(*) FILTER (WHERE cost_breakdown->'costs'->>'tts_usd' IS NOT NULL)::float / COUNT(*)) * 100 as success_rate
FROM calls
WHERE created_at > NOW() - INTERVAL '1 day';
```

## Comparison Matrix

| Feature | Deepgram | Sarvam |
|---------|----------|--------|
| Accent | American | Indian (en-IN) |
| Latency | ~0.3-0.5s | ~0.4-0.6s |
| Cost | $0.03/1K chars | ~$0.036/1K chars |
| Telephony | Exotel + Twilio | Exotel only |
| Codec | linear16, mulaw | linear16 |
| Fallback | N/A | → Deepgram |

## Next Steps After Testing

### If Tests Pass ✅
1. Enable Sarvam in staging environment
2. Monitor for 24-48 hours
3. Compare voice quality feedback
4. Check cost actuals vs estimates
5. Gradually roll out to production

### If Tests Fail ❌
1. Document specific failure modes
2. Check Sarvam API status
3. Review error logs
4. Test with different speakers
5. Consider WebSocket endpoint
6. Keep using Deepgram until resolved

## Rollback Procedure

**Immediate (< 1 minute):**
```bash
# In backend/.env
TTS_PROVIDER=deepgram

# Restart
pkill -f uvicorn
uvicorn app.main:app --reload
```

**Verification:**
- Check logs: "Requesting TTS from deepgram"
- Place test call
- Verify American accent

## Support Resources

- **Sarvam Docs:** https://docs.sarvam.ai/
- **Sarvam API Status:** Check their status page
- **Internal Docs:** 
  - `sarvam-implementation-plan.md`
  - `sarvam-implementation-summary.md`
- **Code:**
  - `backend/app/services/tts_providers.py`
  - `backend/app/services/deepgram_runtime.py`
