# Sarvam WebSocket vs HTTP Streaming Analysis

## Summary

**Yes, Sarvam provides a WebSocket API for TTS!**

- **WebSocket endpoint**: `wss://api.sarvam.ai/text-to-speech/ws`
- **HTTP streaming endpoint**: `https://api.sarvam.ai/text-to-speech/stream` (currently using)

## WebSocket API Details

### Connection

```
WSS wss://api.sarvam.ai/text-to-speech/ws
Method: GET
Status: 101 Switching Protocols
```

### Authentication

```
Headers:
  Api-Subscription-Key: <your-api-key>
```

### Query Parameters

- `model`: `bulbul:v2` or `bulbul:v3` (default: bulbul:v2)
- `send_completion_event`: `true` or `false` (default: true)

### Message Protocol

#### 1. Configure Connection (Initial)
```json
{
  "type": "config",
  "data": {
    "target_language_code": "en-IN",
    "speaker": "shubh",
    "model": "bulbul:v3",
    "pace": 1.0,
    "speech_sample_rate": 8000,
    "output_audio_codec": "linear16"
  }
}
```

#### 2. Send Text (Multiple times)
```json
{
  "type": "text",
  "data": {
    "text": "Hello, this is a test message."
  }
}
```

#### 3. Flush Signal (End of text)
```json
{
  "type": "flush"
}
```

#### 4. Receive Audio (Multiple chunks)
```json
{
  "type": "audio",
  "data": {
    "content_type": "audio/wav",
    "audio": "<base64-encoded-audio>"
  }
}
```

#### 5. Completion Event (Optional)
```json
{
  "type": "event",
  "data": {
    "event_type": "completion"
  }
}
```

#### 6. Ping/Pong (Keep-alive)
```json
{
  "type": "ping"
}
```

## Comparison: WebSocket vs HTTP Streaming

### Current Implementation (HTTP Streaming)

**Pros:**
- ✅ Simple to implement (already done)
- ✅ Works with standard HTTP libraries (httpx)
- ✅ No connection management needed
- ✅ Automatic reconnection on failure

**Cons:**
- ❌ New connection for each request
- ❌ HTTP overhead per request
- ❌ Inconsistent performance (0.4s - 8s)
- ❌ No persistent connection benefits

**Performance:**
- Fast: 0.4-0.7s (67% of requests)
- Slow: 5-8s (33% of requests)
- Average: 2.6s

### WebSocket Implementation (Proposed)

**Pros:**
- ✅ Persistent connection (lower latency)
- ✅ No HTTP overhead per request
- ✅ Bidirectional communication
- ✅ Potentially more consistent performance
- ✅ Can send multiple texts without reconnecting
- ✅ Real-time completion events

**Cons:**
- ❌ More complex to implement
- ❌ Connection management required
- ❌ Need to handle disconnections/reconnections
- ❌ State management across requests

**Expected Performance:**
- Potentially faster and more consistent
- Lower latency due to persistent connection
- Better for high-frequency requests

## Should We Switch to WebSocket?

### Analysis

**Current Problem:**
- Sarvam HTTP streaming is inconsistent (33% slow responses)
- Slow responses are 5-8 seconds (unacceptable)
- Fast responses are 0.4-0.7 seconds (excellent)

**Will WebSocket Fix This?**

**Likely YES for connection overhead:**
- Eliminates HTTP handshake per request
- Reduces network round-trips
- May improve consistency

**Likely NO for API processing time:**
- If Sarvam's TTS generation is slow, WebSocket won't help
- The 5-8s delays might be model inference time, not network

### Recommendation

**Try WebSocket, but with caveats:**

1. **Implement WebSocket as an experiment**
   - Test if it improves consistency
   - Measure time-to-first-chunk
   - Compare with HTTP streaming

2. **Keep HTTP streaming as fallback**
   - Don't remove current implementation
   - Use WebSocket as primary, HTTP as backup

3. **Add timeout-based fallback to Deepgram**
   - If WebSocket OR HTTP takes > 2s, use Deepgram
   - Ensures consistent user experience

## Implementation Plan

### Phase 1: WebSocket Implementation (2-3 hours)

```python
class SarvamWebSocketTTSProvider:
    """Sarvam TTS provider using WebSocket for lower latency."""
    
    provider_name = "sarvam_ws"
    supports_streaming = True
    
    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.ws_url = "wss://api.sarvam.ai/text-to-speech/ws"
        self._ws = None
        self._lock = asyncio.Lock()
    
    async def _ensure_connected(self):
        """Ensure WebSocket connection is established."""
        if self._ws is None or self._ws.closed:
            headers = {"Api-Subscription-Key": self.api_key}
            params = {"model": "bulbul:v3"}
            self._ws = await websockets.connect(
                f"{self.ws_url}?model=bulbul:v3",
                additional_headers=headers
            )
            # Send initial config
            await self._ws.send(json.dumps({
                "type": "config",
                "data": {
                    "target_language_code": "en-IN",
                    "speaker": "shubh",
                    "pace": 1.0,
                    "speech_sample_rate": 8000,
                    "output_audio_codec": "linear16"
                }
            }))
    
    async def synthesize_stream(self, *, text: str, telephony_provider: str):
        """Synthesize using WebSocket with progressive delivery."""
        async with self._lock:  # Ensure sequential access
            await self._ensure_connected()
            
            # Send text
            await self._ws.send(json.dumps({
                "type": "text",
                "data": {"text": text}
            }))
            
            # Send flush to indicate end of text
            await self._ws.send(json.dumps({"type": "flush"}))
            
            # Receive audio chunks
            while True:
                message = await self._ws.recv()
                data = json.loads(message)
                
                if data["type"] == "audio":
                    audio_b64 = data["data"]["audio"]
                    audio_bytes = base64.b64decode(audio_b64)
                    yield audio_bytes
                
                elif data["type"] == "event":
                    # Completion event
                    break
                
                elif data["type"] == "error":
                    raise RuntimeError(f"Sarvam WebSocket error: {data}")
```

### Phase 2: Testing (1 hour)

1. Place test calls with WebSocket
2. Measure time-to-first-chunk
3. Compare with HTTP streaming
4. Check consistency

### Phase 3: Fallback Logic (1 hour)

```python
async def synthesize_stream_with_fallback(self, *, text: str, telephony_provider: str):
    """Try WebSocket, fall back to HTTP, then Deepgram."""
    
    # Try WebSocket first
    try:
        async with asyncio.timeout(2.0):
            async for chunk in self._ws_provider.synthesize_stream(...):
                yield chunk
                return  # Success!
    except (asyncio.TimeoutError, Exception) as e:
        log_debug(f"WebSocket failed: {e}, trying HTTP...")
    
    # Try HTTP streaming
    try:
        async with asyncio.timeout(2.0):
            async for chunk in self._http_provider.synthesize_stream(...):
                yield chunk
                return  # Success!
    except (asyncio.TimeoutError, Exception) as e:
        log_debug(f"HTTP failed: {e}, falling back to Deepgram...")
    
    # Fall back to Deepgram
    audio = await self._deepgram_provider.synthesize(...)
    yield audio
```

## Expected Outcomes

### Best Case
- WebSocket reduces latency to 0.3-0.5s consistently
- No more 5-8s slow responses
- User experience is excellent

### Likely Case
- WebSocket improves consistency slightly
- Still some slow responses (Sarvam API issue)
- Fallback to Deepgram handles slow cases

### Worst Case
- WebSocket doesn't improve performance
- Same inconsistency as HTTP
- We keep HTTP streaming and add Deepgram fallback

## Cost Implications

**WebSocket vs HTTP:**
- Same pricing ($0.036 per 1K characters)
- No additional cost for WebSocket
- Potential savings from persistent connection (fewer API calls for reconnection)

## Risks

1. **Complexity**: WebSocket is more complex than HTTP
2. **Connection management**: Need to handle disconnections
3. **State management**: Ensure sequential access to WebSocket
4. **Testing**: Need thorough testing before production

## Decision Matrix

| Factor | HTTP Streaming | WebSocket | Winner |
|--------|---------------|-----------|--------|
| Simplicity | ✅ Simple | ❌ Complex | HTTP |
| Latency | ⚠️ Variable | ✅ Potentially better | WebSocket |
| Consistency | ❌ Inconsistent | ✅ Potentially better | WebSocket |
| Reliability | ✅ Auto-reconnect | ⚠️ Manual reconnect | HTTP |
| Implementation time | ✅ Done | ❌ 2-3 hours | HTTP |
| Production readiness | ✅ Tested | ❌ Untested | HTTP |

## Recommendation

### Short-term (This Week)
1. **Add timeout-based fallback to Deepgram** (1 hour)
   - If HTTP streaming takes > 2s, use Deepgram
   - Ensures consistent user experience
   - Low risk, high impact

2. **Monitor Sarvam HTTP performance** (ongoing)
   - Track time-to-first-chunk
   - Identify patterns in slow responses
   - Gather data for Sarvam support

### Medium-term (Next Sprint)
1. **Implement WebSocket as experiment** (2-3 hours)
   - Test in development environment
   - Compare performance with HTTP
   - Decide based on results

2. **Contact Sarvam support** (1 hour)
   - Report inconsistent performance
   - Ask about optimization options
   - Request guidance on WebSocket vs HTTP

### Long-term (Next Month)
1. **Evaluate alternative providers** (1 week)
   - Test other Indian accent TTS providers
   - Benchmark performance and cost
   - Have backup ready

2. **Implement hybrid approach** (1 week)
   - Use Deepgram for short responses (<100 chars)
   - Use Sarvam for long responses (>100 chars)
   - Best of both worlds

## Conclusion

**Yes, Sarvam provides WebSocket API, and it's worth trying!**

**Immediate action:**
- Add timeout-based fallback to Deepgram (HIGH PRIORITY)
- This solves the 33% slow response problem immediately

**Next step:**
- Implement WebSocket as an experiment
- Test if it improves consistency
- Keep HTTP as fallback

**The WebSocket API might help with connection overhead, but won't fix slow API processing. The timeout-based fallback to Deepgram is the safest solution for production.**

---

**WebSocket Endpoint**: `wss://api.sarvam.ai/text-to-speech/ws`
**Documentation**: https://docs.sarvam.ai/api-reference-docs/text-to-speech/stream
**Status**: Available and documented
**Recommendation**: Try it, but add Deepgram fallback first
