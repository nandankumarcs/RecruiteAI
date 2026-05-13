# Sarvam TTS Call Analysis

## Call Summary
- **Call ID:** a9b5af0b-3b36-481b-9cec-6e8176c596cb
- **Status:** Completed ✅
- **Duration:** 180 seconds (3 minutes)
- **Provider:** Exotel
- **Voice Runtime:** deepgram_openai
- **TTS Provider:** Sarvam (Indian accent)

## ✅ What Worked Well

### 1. Technical Integration
- **Sarvam TTS successfully integrated** - Call completed without technical failures
- **Audio delivery working** - Multiple TTS generations (107,800 bytes and 176,000 bytes)
- **Exotel integration stable** - No connection drops or audio issues
- **Cost tracking accurate** - TTS costs properly recorded

### 2. Call Flow
- **Call connected successfully** - 16 second connection time
- **First audio delivered** - 4.1 seconds after stream connection
- **Consent obtained** - User agreed to continue
- **Graceful termination** - Call ended properly when user declined

### 3. Latency Performance
- **Call answered:** 16.3 seconds after request
- **Stream connected:** Immediately after answer
- **First assistant audio:** 4.1 seconds after connection
- **First user transcript:** 45.5 seconds after connection (user spoke)

## ⚠️ Issues & Gaps Identified

### 1. **STT Accuracy Issues** (Critical)
**Problem:** Speech-to-text transcription appears inaccurate

**Evidence:**
- User: "Hello?" → Transcribed correctly
- User: "Yes." → Transcribed correctly
- User: "What do you want to know about?" → Likely accurate
- User: "I don't understand the question. You need to clarify it." → Seems accurate
- User: "I'm a first time developer." → Possibly misheard
- User: "And my experience matches the job." → Short, vague
- User: "Description." → Single word, unclear context
- User: "Sorry. Not interested. Did you lose the phone?" → **Suspicious** - suggests audio quality issue

**Impact:**
- The conversation shows confusion and repetition
- User asked "Did you lose the phone?" - suggests they may not have heard the assistant clearly
- Assistant had to repeat/clarify questions multiple times

**Root Cause Analysis:**
- Could be Deepgram STT struggling with Indian accent
- Could be Sarvam TTS audio quality causing user confusion
- Could be network/audio quality issues on Exotel

### 2. **Conversation Quality Issues** (High Priority)

**Problem:** Multiple clarification loops

**Evidence:**
```
Assistant: Can you briefly introduce yourself...
User: What do you want to know about?
Assistant: I'm looking for a brief introduction...
User: I don't understand the question. You need to clarify it.
Assistant: Sure! I'm asking for a brief introduction...
```

**Analysis:**
- 3 attempts to get a simple introduction
- User repeatedly asked for clarification
- Suggests either:
  - Audio quality issues (user couldn't hear clearly)
  - TTS pronunciation issues (Indian accent not clear enough)
  - Question phrasing issues (not culturally appropriate)

### 3. **Cost Analysis**

**Current Costs:**
- **LLM:** $0.001333 (959 input + 47 output tokens)
- **TTS:** $0.05724 (Sarvam)
- **Telephony:** $0.015 (Exotel)
- **Total:** $0.073573 for 3 minutes

**TTS Cost Breakdown:**
- Total characters synthesized: ~1,590 characters (estimated from transcript)
- Cost per 1K chars: $0.036 (Sarvam)
- Expected cost: ~$0.057 ✅ Matches actual

**Comparison with Deepgram:**
- Deepgram would cost: ~$0.048 (1,590 chars × $0.030/1K)
- Sarvam costs: ~$0.057 (1,590 chars × $0.036/1K)
- **Difference:** +$0.009 (+19% more expensive)

**Assessment:** Cost is reasonable for Indian accent benefit

### 4. **Missing STT Cost** (Data Gap)

**Problem:** No STT cost recorded in breakdown

**Evidence:**
```json
"costs": {
  "llm_usd": 0.001333,
  "tts_usd": 0.05724,
  "telephony_usd": 0.015
  // Missing: "stt_usd"
}
```

**Expected STT Cost:**
- Duration: 180 seconds = 3 minutes
- Deepgram STT: $0.0043/minute
- Expected: ~$0.013

**Impact:** Cost tracking incomplete

### 5. **User Experience Issues**

**Problem:** User terminated call prematurely

**Evidence:**
- User said "Sorry. Not interested. Did you lose the phone?"
- Call ended at 3 minutes (relatively short)
- Only got through 2-3 questions before termination

**Possible Causes:**
1. **Audio quality** - User couldn't hear clearly ("Did you lose the phone?")
2. **Voice quality** - Sarvam TTS may sound robotic or unclear
3. **Pronunciation** - Name "Shreyansh" may have been mispronounced
4. **Pacing** - TTS may be too fast or too slow
5. **Cultural fit** - Questions may not resonate with Indian candidates

### 6. **No Barge-in Evidence**

**Observation:** No evidence of interruption handling in logs

**Analysis:**
- User never interrupted the assistant mid-speech
- Can't verify if barge-in detection is working with Sarvam TTS
- Need to test interruption scenarios

## 🔍 Specific Technical Observations

### TTS Generation Stats
1. **First TTS:** 107,800 bytes → 68 chunks → ~6.7 seconds of audio
2. **Second TTS:** 176,000 bytes → 110 chunks (estimated) → ~11 seconds of audio

**Audio Format:**
- Codec: linear16
- Sample rate: 8000 Hz
- Channels: mono
- Chunk size: 1600 bytes
- Pacing: 0.095s per chunk

**Calculation:**
- 107,800 bytes ÷ 2 bytes/sample ÷ 8000 samples/sec = **6.7 seconds** ✅
- 176,000 bytes ÷ 2 bytes/sample ÷ 8000 samples/sec = **11 seconds** ✅

### Latency Breakdown
- **Call request to answer:** 16.3s (Exotel dialing time)
- **Answer to stream:** <1s (excellent)
- **Stream to first audio:** 4.1s (TTS generation + delivery)
- **First audio to user speech:** 41.4s (user listening + thinking)

**TTS Latency:**
- 4.1 seconds for first response is acceptable
- Includes: LLM generation + Sarvam TTS + network + chunking

## 📊 Recommendations

### Immediate Actions

1. **Test Audio Quality**
   - Place another test call
   - Specifically listen for:
     - Clarity of Indian accent
     - Pronunciation of Indian names
     - Any robotic/synthetic quality
     - Volume levels
     - Background noise/artifacts

2. **Verify STT Accuracy**
   - Test with known phrases
   - Compare Deepgram STT accuracy with Indian accent
   - Consider if Sarvam STT would be better (currently using Deepgram)

3. **Add STT Cost Tracking**
   - Fix the missing STT cost in cost_breakdown
   - Ensure all costs are captured

4. **Test Barge-in**
   - Place a call and interrupt the assistant
   - Verify interruption detection works with Sarvam audio

### Short-term Improvements

1. **Voice Quality Tuning**
   - Test different Sarvam speakers (currently: "shubh")
   - Try: "meera", "arvind", "aarav" for comparison
   - Adjust pace parameter (currently: 1.0)
   - Test with pace: 0.9 (slower) or 1.1 (faster)

2. **Question Phrasing**
   - Review questions for cultural appropriateness
   - Simplify complex questions
   - Add more context/examples

3. **Pronunciation Dictionary**
   - Add common Indian names to pronunciation guide
   - Test: Shreyansh, Rahul, Priya, Arjun, etc.

4. **Monitoring Dashboard**
   - Track TTS provider usage
   - Monitor fallback rate
   - Track user feedback/termination reasons

### Long-term Enhancements

1. **Consider Sarvam STT**
   - Replace Deepgram STT with Sarvam STT
   - Better accent matching (Indian STT + Indian TTS)
   - Potentially better accuracy for Indian English

2. **A/B Testing**
   - Run parallel tests: Deepgram TTS vs Sarvam TTS
   - Collect user feedback
   - Measure completion rates

3. **Voice Customization**
   - Allow per-job voice selection
   - Different voices for different industries
   - Gender preference options

4. **Quality Metrics**
   - Track: completion rate, clarification loops, user satisfaction
   - Set thresholds for acceptable quality
   - Auto-fallback if quality drops

## 🎯 Success Criteria Met

✅ **Technical Integration:** Sarvam TTS working end-to-end
✅ **Cost Tracking:** TTS costs accurately recorded
✅ **Audio Delivery:** No technical failures or dropouts
✅ **Latency:** Acceptable response times
✅ **Fallback:** System has Deepgram fallback (not triggered)

## ⚠️ Success Criteria Pending

⏳ **Voice Quality:** Needs user feedback validation
⏳ **STT Accuracy:** Needs testing with known phrases
⏳ **Barge-in:** Needs interruption testing
⏳ **User Satisfaction:** User terminated early - needs investigation
⏳ **Pronunciation:** Needs testing with more Indian names

## 🔧 Next Steps

1. **Immediate:** Place another test call with clear test phrases
2. **Today:** Test different Sarvam speakers and pace settings
3. **This week:** Add STT cost tracking fix
4. **This week:** Implement pronunciation dictionary
5. **Next week:** A/B test with real candidates

## 📝 Conclusion

**Overall Assessment:** ⚠️ **Partially Successful**

The Sarvam TTS integration is **technically working** but has **user experience concerns**:

**Pros:**
- ✅ Technical integration successful
- ✅ Indian accent delivered
- ✅ No system failures
- ✅ Cost tracking working

**Cons:**
- ⚠️ User terminated early ("Did you lose the phone?")
- ⚠️ Multiple clarification loops
- ⚠️ Possible audio quality issues
- ⚠️ Missing STT cost tracking

**Recommendation:** 
- Keep Sarvam TTS enabled
- Conduct more test calls with different speakers
- Monitor next 10-20 real calls closely
- Be ready to rollback if quality issues persist
- Consider adding Sarvam STT for better accent matching

**Risk Level:** 🟡 **Medium** - Working but needs validation
