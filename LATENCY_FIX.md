# Sarvam TTS Latency Fix

## Problem Identified

**User reported:** "latency per turn is very noticeable"

### Analysis Results

**Average per-turn latency: 9.80 seconds** 🔴

Breakdown:
- **Sarvam API generation:** 3.27s (33%)
- **Chunking + delivery:** 6.52s (67%)

### Detailed Findings

| Turn | Text Length | Audio Size | Generation | Delivery | Total |
|------|-------------|------------|------------|----------|-------|
| 1 | Long | 158KB (9.9s) | 4.10s | 9.50s | 13.60s |
| 2 | Short | 81KB (5.1s) | 2.30s | 4.90s | 7.20s |
| 3 | Short | 81KB (5.1s) | 2.23s | 4.90s | 7.13s |
| 4 | Medium | 95KB (5.9s) | 2.62s | 5.76s | 8.38s |
| 5 | Long | 161KB (10.0s) | 4.23s | 9.68s | 13.91s |
| 6 | Medium | 125KB (7.8s) | 3.31s | 0.38s | 3.69s |
| 7 | Medium | 108KB (6.7s) | 2.88s | 6.52s | 9.40s |
| 8 | Long | 176KB (11.0s) | 4.52s | 10.55s | 15.07s |

**Average:** 3.27s generation + 6.52s delivery = **9.80s total**

## Root Causes

### 1. Sarvam API Latency (3.27s avg)

**Expected:** 0.4-0.6s (from implementation plan)
**Actual:** 3.27s
**Difference:** **555% slower than expected!**

**Why:**
- HTTP streaming endpoint is not truly streaming
- Waits for complete audio generation before returning
- No incremental delivery

**Evidence:**
```
2026-05-12 22:19:34.548927 - Requesting TTS from sarvam...
2026-05-12 22:19:38.650649 - Sarvam TTS complete: 158400 bytes
```
→ 4.1 seconds for 9.9s of audio

### 2. Chunking Delay (6.52s avg)

**Problem:** Artificial pacing delay between chunks

**Code:**
```python
sleep_time = 0.095  # 95ms per chunk for Exotel
```

**Impact:**
- 100 chunks × 0.095s = **9.5 seconds of artificial delay**
- This was designed to match audio playback rate
- But it's unnecessary - client can buffer

**Evidence:**
```
Turn 1: 99 chunks × 0.095s = 9.4s delivery time
Turn 5: 101 chunks × 0.095s = 9.6s delivery time
```

## Solutions Implemented

### ✅ Quick Fix: Reduce Chunking Delay

**Change:**
```python
# Before
sleep_time = 0.095 if provider == "exotel" else 0.045

# After
sleep_time = 0.020 if provider == "exotel" else 0.010
```

**Impact:**
- Reduces delay from 95ms to 20ms per chunk
- **4.75x faster delivery**
- Expected delivery time: ~2 seconds (down from 6.5s)
- **Saves ~4.5 seconds per turn**

**New expected latency:**
- Generation: 3.27s (unchanged)
- Delivery: ~2.0s (improved)
- **Total: ~5.3s per turn** (down from 9.8s)

**Rationale:**
- Exotel/client can buffer audio appropriately
- No need to artificially slow down delivery
- Audio will play smoothly on client side

### 🔄 Future Improvements

#### Option 1: Switch to Sarvam WebSocket (Recommended)

**Endpoint:** `wss://api.sarvam.ai/text-to-speech/ws`

**Benefits:**
- True streaming - start playing as audio generates
- Should reduce generation time to <1s for first audio
- Better user experience

**Effort:** Medium (needs WebSocket implementation)

**Expected latency:**
- First audio: <1s
- Total: ~3-4s per turn

#### Option 2: Parallel TTS + Delivery

**Approach:**
- Start sending chunks as soon as first chunk is ready
- Don't wait for full audio generation

**Benefits:**
- Reduces perceived latency
- User hears response faster

**Effort:** Medium (refactor chunking logic)

#### Option 3: Revert to Deepgram TTS

**If Sarvam latency remains unacceptable:**
- Deepgram TTS is much faster (~1-2s total)
- Sacrifice Indian accent for better UX
- Keep as fallback option

## Testing Plan

### 1. Immediate Testing (After Quick Fix)

Place test call and measure:
- [ ] Per-turn latency
- [ ] Audio quality (no stuttering/buffering)
- [ ] User experience feedback

**Expected results:**
- Latency: ~5-6s per turn (down from 9.8s)
- Audio: Smooth playback
- UX: Noticeably faster

### 2. Monitor Production

Track for next 10-20 calls:
- [ ] Average latency per turn
- [ ] User completion rate
- [ ] Early termination rate
- [ ] Audio quality issues

### 3. If Still Too Slow

Implement WebSocket streaming:
- [ ] Test Sarvam WebSocket endpoint
- [ ] Implement streaming delivery
- [ ] A/B test vs HTTP endpoint

## Comparison: Before vs After

| Metric | Before | After (Quick Fix) | After (WebSocket) |
|--------|--------|-------------------|-------------------|
| Generation | 3.27s | 3.27s | <1s (streaming) |
| Delivery | 6.52s | ~2.0s | ~1s (streaming) |
| **Total** | **9.80s** | **~5.3s** | **~2-3s** |
| Improvement | - | **46% faster** | **70-80% faster** |

## Deployment

### Quick Fix (Implemented)
- ✅ Changed sleep_time from 0.095s to 0.020s
- ✅ Updated comments
- ⏳ Needs backend restart to take effect

### Restart Backend
```bash
# Kill existing process
lsof -ti:8000 | xargs kill -9

# Start with new code
cd backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Verify Fix
```bash
# Place test call
# Monitor logs for delivery time
tail -f debug.log | grep "TTS complete"
```

## Risk Assessment

### Quick Fix Risk: 🟢 LOW

**Potential issues:**
- Audio buffering on client side
- Possible stuttering if network is slow

**Mitigation:**
- Exotel should handle buffering
- 20ms is still conservative (50 chunks/second)
- Can increase if issues occur

**Rollback:**
- Change back to 0.095s if problems occur
- No data loss or breaking changes

## Success Criteria

✅ **Acceptable:** Latency < 6s per turn
✅ **Good:** Latency < 4s per turn  
✅ **Excellent:** Latency < 3s per turn

**Current:** 9.8s → **Unacceptable** 🔴
**After quick fix:** ~5.3s → **Acceptable** 🟡
**After WebSocket:** ~2-3s → **Excellent** 🟢

## Conclusion

**Immediate action taken:**
- Reduced chunking delay by 4.75x
- Expected improvement: 46% faster (9.8s → 5.3s)
- Low risk, easy rollback

**Next steps:**
1. Restart backend to apply fix
2. Place test call to verify
3. Monitor production calls
4. Plan WebSocket implementation if needed

**Recommendation:**
- Deploy quick fix immediately
- Test thoroughly
- Plan WebSocket implementation for next sprint
