# Sarvam TTS Implementation Checklist

## ✅ Implementation Complete

### Phase 1: Configuration ✅
- [x] Added `TTS_PROVIDER` to `backend/app/config.py`
- [x] Added Sarvam configuration variables to `backend/app/config.py`
- [x] Updated `backend/.env.example` with Sarvam settings
- [x] Default remains `TTS_PROVIDER=deepgram` (backward compatible)

### Phase 2 & 3: TTS Provider Abstraction ✅
- [x] Created `backend/app/services/tts_providers.py`
- [x] Implemented `BaseTTSProvider` protocol
- [x] Implemented `DeepgramTTSProvider` (extracted from runtime)
- [x] Implemented `SarvamTTSProvider` with HTTP streaming
- [x] Created `get_tts_provider()` factory function
- [x] All imports verified working

### Phase 4: Pricing Integration ✅
- [x] Added `estimate_sarvam_tts_cost()` to `backend/app/services/pricing.py`
- [x] Added `estimate_tts_cost()` dispatcher function
- [x] INR to USD conversion implemented (₹1 = $0.012)
- [x] Pricing calculations verified

### Phase 5: Runtime Integration ✅
- [x] Updated `backend/app/services/deepgram_runtime.py`
- [x] Refactored `_speak_text()` to use provider abstraction
- [x] Implemented automatic fallback to Deepgram
- [x] Preserved all existing functionality:
  - [x] Cost tracking
  - [x] Chunking and pacing
  - [x] First audio marker
  - [x] Interruption handling
  - [x] WebSocket error handling

### Code Quality ✅
- [x] All Python files compile without syntax errors
- [x] All imports verified
- [x] Config loading verified
- [x] Pricing functions verified
- [x] No breaking changes to existing code

## 📋 Pre-Testing Checklist

Before testing, ensure:
- [ ] Sarvam API key obtained from https://www.sarvam.ai/
- [ ] Exotel account configured and working
- [ ] Backend `.env` file has all required variables
- [ ] `VOICE_RUNTIME=deepgram_openai` is set
- [ ] `TELEPHONY_PROVIDER=exotel` is set

## 🧪 Testing Checklist

### Local Testing
- [ ] Test 1: Basic TTS with Deepgram (baseline)
- [ ] Test 2: Basic TTS with Sarvam
- [ ] Test 3: Fallback behavior (invalid API key)
- [ ] Test 4: Indian name pronunciation
- [ ] Test 5: Barge-in/interruption handling
- [ ] Test 6: Cost tracking verification
- [ ] Test 7: Latency comparison
- [ ] Test 8: Long utterances

### Live Call Testing
- [ ] Place test call with Sarvam TTS
- [ ] Verify Indian accent is clear and natural
- [ ] Test with multiple Indian names
- [ ] Verify interruption works
- [ ] Check transcript persistence
- [ ] Monitor logs for errors
- [ ] Verify cost breakdown in database

### Performance Testing
- [ ] Measure time to first byte
- [ ] Measure total synthesis time
- [ ] Compare with Deepgram baseline
- [ ] Test under load (multiple concurrent calls)
- [ ] Monitor fallback rate

## 📊 Success Criteria

- [ ] Sarvam TTS produces clear Indian-accented English
- [ ] Latency is acceptable (< 0.6s to first byte)
- [ ] Fallback to Deepgram works automatically
- [ ] Cost tracking is accurate
- [ ] No regressions in existing functionality
- [ ] Barge-in/interruption still works
- [ ] Transcript persistence unchanged

## 🚀 Deployment Checklist

### Staging
- [ ] Deploy to staging environment
- [ ] Set `TTS_PROVIDER=sarvam` in staging `.env`
- [ ] Run full test suite
- [ ] Monitor for 24-48 hours
- [ ] Collect voice quality feedback
- [ ] Verify cost estimates vs actuals

### Production
- [ ] Review staging results
- [ ] Get stakeholder approval
- [ ] Deploy to production
- [ ] Initially keep `TTS_PROVIDER=deepgram`
- [ ] Enable Sarvam for subset of calls (A/B test)
- [ ] Monitor metrics:
  - [ ] Success rate
  - [ ] Fallback rate
  - [ ] Latency
  - [ ] Cost per call
  - [ ] Voice quality feedback
- [ ] Gradually increase Sarvam usage
- [ ] Full rollout when confident

## 🔄 Rollback Plan

If issues arise:

### Immediate Rollback (< 1 minute)
```bash
# In backend/.env
TTS_PROVIDER=deepgram

# Restart backend
pkill -f uvicorn
uvicorn app.main:app --reload
```

### Verification After Rollback
- [ ] Check logs show "Requesting TTS from deepgram"
- [ ] Place test call
- [ ] Verify American accent
- [ ] Confirm no errors

## 📝 Documentation

- [x] Implementation plan: `docs/sarvam-implementation-plan.md`
- [x] Implementation summary: `docs/sarvam-implementation-summary.md`
- [x] Testing guide: `docs/sarvam-testing-guide.md`
- [x] This checklist: `SARVAM_IMPLEMENTATION_CHECKLIST.md`

## 🔮 Future Enhancements

- [ ] Add Twilio support to Sarvam provider (mulaw codec)
- [ ] Explore Sarvam WebSocket endpoint
- [ ] Add more speaker options
- [ ] Add pronunciation dictionary support
- [ ] Add unit tests for TTS providers
- [ ] Add integration tests for fallback behavior
- [ ] Add metrics dashboard for TTS performance
- [ ] Optimize INR→USD conversion rate updates

## 📞 Support

If you encounter issues:

1. Check logs in `backend/backend.log` or `backend/debug.log`
2. Review `docs/sarvam-testing-guide.md` troubleshooting section
3. Verify all environment variables are set correctly
4. Test fallback by using invalid API key
5. Compare with Deepgram baseline

## 🎯 Current Status

**Implementation:** ✅ Complete  
**Testing:** ⏳ Pending  
**Staging:** ⏳ Pending  
**Production:** ⏳ Pending  

**Next Step:** Add Sarvam API key to `.env` and begin testing

---

## Quick Start Commands

```bash
# 1. Add to backend/.env
echo "TTS_PROVIDER=sarvam" >> backend/.env
echo "SARVAM_API_KEY=your-key-here" >> backend/.env

# 2. Restart backend
cd backend
uvicorn app.main:app --reload

# 3. Check logs
tail -f backend.log | grep -i sarvam

# 4. Place test call via Exotel

# 5. Rollback if needed
# Change TTS_PROVIDER=deepgram in .env and restart
```

## Files Modified/Created

### Modified
- `backend/app/config.py` - Added Sarvam config
- `backend/app/services/deepgram_runtime.py` - Refactored to use providers
- `backend/app/services/pricing.py` - Added Sarvam cost estimation
- `backend/.env.example` - Added Sarvam env vars

### Created
- `backend/app/services/tts_providers.py` - TTS provider abstraction
- `docs/sarvam-implementation-summary.md` - Implementation summary
- `docs/sarvam-testing-guide.md` - Testing guide
- `SARVAM_IMPLEMENTATION_CHECKLIST.md` - This file

### No Changes Required
- `backend/requirements.txt` - httpx already present
- Database migrations - No schema changes
- Frontend - No changes needed
