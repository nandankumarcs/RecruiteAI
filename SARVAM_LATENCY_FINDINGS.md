# Sarvam TTS Latency Investigation - Key Findings

## Executive Summary

After two test calls and latency analysis, we've identified that **Sarvam API generation time is the primary bottleneck**, not audio delivery. The chunking delay fix improved delivery but did not address the root cause.

## Test Results

### First Call (Before Fix)
- **Average TTS generation**: 3.27 seconds
- **Average delivery delay**: 6.52 seconds (chunking overhead)
- **Total latency per turn**: 9.80 seconds

### Second Call (After Chunking Fix)
- **TTS generation**: 3.20 seconds (NO IMPROVEMENT)
- **Delivery delay**: Reduced (but still waiting for full generation)
- **Problem**: Still 3+ second wait before ANY audio plays

## Root Cause: Sarvam API Performance

### Current Implementation
```python
# We're using Sarvam's HTTP streaming endpoint
url = "https://api.sarvam.ai/text-to-speech/stream"

# But we collect ALL chunks before returning
audio_chunks = []
async for chunk in response.aiter_bytes():
    audio_chunks.append(chunk)
audio_bytes = b"".join(audio_chunks)  # Wait for complete audio
return audio_bytes
```

### The Problem
1. **Sarvam API takes 3+ seconds** to generate complete audio
2. We wait for 100% generation before starting playback
3. User experiences 3+ second silence (feels broken)

### Expected vs Actual
- **Expected Sarvam TTS**: 0.4-0.6 seconds
- **Actual**: 3.0-3.3 seconds
- **Slowdown**: **5-8x slower than expected**

## Why Is Sarvam So Slow?

### Possible Reasons
1. **Network Latency**: Distance to Sarvam servers (India-based)
2. **Model Inference Time**: Bulbul:v3 model processing
3. **API Load**: Sarvam server capacity/load
4. **Request Overhead**: HTTP streaming setup time
5. **Our Implementation**: Not utilizing true streaming

### Evidence from Logs
```
22:33:44.831 - Requesting Sarvam HTTP stream...
22:33:48.027 - Sarvam TTS complete: 121000 bytes
Duration: 3.196 seconds for 121KB audio
```

## Impact on User Experience

### Current Flow (BAD)
```
User speaks → [3+ sec silence] → Audio starts playing
```

### What Users Experience
- Long awkward silence after speaking
- Feels like system is frozen/broken
- Unnatural conversation flow
- Poor user experience

### Comparison with Deepgram
- **Deepgram**: ~0.5 seconds (acceptable)
- **Sarvam**: ~3.2 seconds (unacceptable)
- **Difference**: 6.4x slower

## Solutions

### Option 1: True Streaming Playback (RECOMMENDED)
**Modify our implementation to start playing audio as soon as first chunk arrives**

```python
# Instead of collecting all chunks:
async for chunk in response.aiter_bytes():
    if chunk:
        await send_audio_chunk_immediately(chunk)  # Don't wait!
```

**Benefits**:
- Reduces perceived latency significantly
- Audio starts playing within ~0.5 seconds
- More natural conversation flow

**Challenges**:
- Need to modify deepgram_runtime.py to handle streaming
- May need to adjust chunking logic
- Requires testing with Exotel

### Option 2: Investigate Sarvam API Performance
**Contact Sarvam support to understand slow generation**

**Questions for Sarvam**:
- Is 3+ seconds normal for 121KB audio?
- Are there faster models available?
- Is there a WebSocket endpoint for lower latency?
- What's the expected latency for our configuration?

### Option 3: Hybrid Approach
**Use Deepgram for short responses, Sarvam for longer ones**

```python
if len(text) < 100:  # Short response
    use_deepgram()  # Fast (0.5s)
else:  # Long response
    use_sarvam()  # Indian accent worth the wait
```

### Option 4: Revert to Deepgram
**If Sarvam performance doesn't improve**

**Pros**:
- Fast (0.5s generation)
- Reliable performance
- Lower cost ($0.030 vs $0.036 per 1K chars)

**Cons**:
- Loses Indian accent
- Back to original problem

## Recommended Action Plan

### Immediate (Today)
1. **Implement true streaming playback** (Option 1)
   - Modify SarvamTTSProvider to yield chunks
   - Update deepgram_runtime.py to handle streaming
   - Test with Exotel

2. **Measure improvement**
   - Run test call with streaming
   - Compare perceived latency
   - Document results

### Short-term (This Week)
1. **Contact Sarvam support**
   - Report slow generation times
   - Ask about optimization options
   - Request WebSocket endpoint if available

2. **Implement hybrid approach** (Option 3)
   - Use Deepgram for short responses
   - Use Sarvam for longer responses
   - Add configuration for threshold

### Long-term (Next Sprint)
1. **Add monitoring**
   - Track TTS generation time per provider
   - Alert on slow responses (>2s)
   - Dashboard for latency metrics

2. **Evaluate alternatives**
   - Test other Indian accent TTS providers
   - Consider voice cloning with Deepgram
   - Benchmark against competitors

## Technical Details

### Current Sarvam Configuration
```python
model = "bulbul:v3"
speaker = "shubh"
language = "en-IN"
sample_rate = 8000
codec = "linear16"
pace = 1.0
```

### Performance Metrics
| Metric | Value |
|--------|-------|
| Average generation time | 3.2s |
| Expected generation time | 0.4-0.6s |
| Slowdown factor | 5-8x |
| Audio size (avg) | 120KB |
| Cost per call | $0.0054 |

### Comparison with Deepgram
| Provider | Generation | Cost/1K | Accent | Verdict |
|----------|-----------|---------|--------|---------|
| Sarvam | 3.2s | $0.036 | Indian | Too slow |
| Deepgram | 0.5s | $0.030 | American | Fast but wrong accent |

## Conclusion

**The Sarvam TTS integration is functionally working but performance is unacceptable for real-time conversations.** The 3+ second generation time creates an awkward user experience that makes the system feel broken.

**Next Step**: Implement true streaming playback (Option 1) to start playing audio immediately as chunks arrive. This should reduce perceived latency from 3+ seconds to ~0.5 seconds, making the conversation feel natural again.

If streaming doesn't help (because Sarvam sends all data at once), we'll need to either:
1. Contact Sarvam support about performance
2. Implement hybrid Deepgram/Sarvam approach
3. Revert to Deepgram until Sarvam improves

---

**Status**: Ready to implement streaming playback
**Priority**: HIGH - User experience is currently poor
**Estimated Effort**: 2-3 hours
