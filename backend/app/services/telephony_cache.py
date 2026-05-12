import sys

# Global cache for Exotel call SID to resume ID mapping
# In a production environment, this should be Redis
exotel_call_cache: dict[str, str] = {}

def cache_exotel_call(call_sid: str, resume_id: str):
    exotel_call_cache[call_sid] = resume_id
    sys.stderr.write(f"CACHED EXOTEL CALL: {call_sid} -> {resume_id}\n")
    sys.stderr.flush()

def get_cached_resume_id(call_sid: str = None) -> str | None:
    if call_sid and call_sid in exotel_call_cache:
        return exotel_call_cache[call_sid]
    if not call_sid and exotel_call_cache:
        # Return most recent
        return list(exotel_call_cache.values())[-1]
    return None
