#!/usr/bin/env python3
"""Analyze TTS latency from the call."""

from datetime import datetime

# Extract timing data from logs
turns = [
    {
        "turn": 1,
        "text": "Hello Shreyansh, I'm your RecruiteAI assistant...",
        "start": "2026-05-12 22:19:34.548927",
        "complete": "2026-05-12 22:19:38.650649",
        "sent": "2026-05-12 22:19:48.152023",
        "bytes": 158400
    },
    {
        "turn": 2,
        "text": "Hello Shreyansh! Just to confirm...",
        "start": "2026-05-12 22:20:27.687531",
        "complete": "2026-05-12 22:20:29.988199",
        "sent": "2026-05-12 22:20:34.890635",
        "bytes": 81400
    },
    {
        "turn": 3,
        "text": "Great! Can you briefly introduce yourself...",
        "start": "2026-05-12 22:20:40.798455",
        "complete": "2026-05-12 22:20:43.030061",
        "sent": "2026-05-12 22:20:47.930869",
        "bytes": 81400
    },
    {
        "turn": 4,
        "text": "I'm looking for a brief introduction...",
        "start": "2026-05-12 22:20:54.139326",
        "complete": "2026-05-12 22:20:56.762043",
        "sent": "2026-05-12 22:21:02.519938",
        "bytes": 94600
    },
    {
        "turn": 5,
        "text": "Sure! I'm asking for a brief introduction...",
        "start": "2026-05-12 22:21:11.554726",
        "complete": "2026-05-12 22:21:15.784910",
        "sent": "2026-05-12 22:21:25.461800",
        "bytes": 160600
    },
    {
        "turn": 6,
        "text": "Thank you for sharing that, Shreyansh!...",
        "start": "2026-05-12 22:21:33.872849",
        "complete": "2026-05-12 22:21:37.183846",
        "sent": "2026-05-12 22:21:37.565886",  # Overlapping with next
        "bytes": 125400
    },
    {
        "turn": 7,
        "text": "That's interesting! Can you explain...",
        "start": "2026-05-12 22:21:42.521931",
        "complete": "2026-05-12 22:21:45.399440",
        "sent": "2026-05-12 22:21:51.922913",
        "bytes": 107800
    },
    {
        "turn": 8,
        "text": "Thank you for sharing that, Shreyansh! It sounds...",
        "start": "2026-05-12 22:22:07.564942",
        "complete": "2026-05-12 22:22:12.085928",
        "sent": "2026-05-12 22:22:22.639241",
        "bytes": 176000
    },
]

print("=" * 100)
print("SARVAM TTS LATENCY ANALYSIS")
print("=" * 100)
print()

total_generation = 0
total_delivery = 0
total_end_to_end = 0

for turn in turns:
    start_dt = datetime.fromisoformat(turn["start"])
    complete_dt = datetime.fromisoformat(turn["complete"])
    sent_dt = datetime.fromisoformat(turn["sent"])
    
    generation_time = (complete_dt - start_dt).total_seconds()
    delivery_time = (sent_dt - complete_dt).total_seconds()
    end_to_end = (sent_dt - start_dt).total_seconds()
    
    audio_duration = turn["bytes"] / 2 / 8000  # bytes / 2 bytes per sample / 8000 Hz
    
    total_generation += generation_time
    total_delivery += delivery_time
    total_end_to_end += end_to_end
    
    print(f"Turn {turn['turn']}: {turn['text'][:50]}...")
    print(f"  Audio size: {turn['bytes']:,} bytes ({audio_duration:.1f}s of audio)")
    print(f"  Generation time: {generation_time:.2f}s (Sarvam API)")
    print(f"  Delivery time: {delivery_time:.2f}s (chunking + network)")
    print(f"  End-to-end: {end_to_end:.2f}s")
    print(f"  Ratio: {end_to_end/audio_duration:.2f}x audio duration")
    print()

print("=" * 100)
print("SUMMARY")
print("=" * 100)
print(f"Average generation time: {total_generation/len(turns):.2f}s")
print(f"Average delivery time: {total_delivery/len(turns):.2f}s")
print(f"Average end-to-end: {total_end_to_end/len(turns):.2f}s")
print()

print("BOTTLENECK ANALYSIS:")
print("-" * 100)
print(f"Sarvam API generation: {total_generation/len(turns):.2f}s avg ({total_generation/total_end_to_end*100:.1f}% of total)")
print(f"Chunking + delivery: {total_delivery/len(turns):.2f}s avg ({total_delivery/total_end_to_end*100:.1f}% of total)")
print()

print("COMPARISON:")
print("-" * 100)
print(f"Target (from plan): ~0.4-0.6s generation time")
print(f"Actual: {total_generation/len(turns):.2f}s generation time")
print(f"Difference: +{total_generation/len(turns) - 0.5:.2f}s ({(total_generation/len(turns) / 0.5 - 1) * 100:.0f}% slower)")
print()

print("RECOMMENDATIONS:")
print("-" * 100)
if total_generation/len(turns) > 3:
    print("🔴 CRITICAL: Sarvam API is taking 3+ seconds per turn")
    print("   - This is 5-7x slower than expected")
    print("   - Consider switching to Sarvam WebSocket for streaming")
    print("   - Or revert to Deepgram TTS for lower latency")
elif total_generation/len(turns) > 2:
    print("🟡 WARNING: Sarvam API is taking 2+ seconds per turn")
    print("   - This is 3-4x slower than expected")
    print("   - Test WebSocket endpoint for better performance")
elif total_generation/len(turns) > 1:
    print("🟡 MODERATE: Sarvam API is taking 1+ seconds per turn")
    print("   - Acceptable but could be improved")
    print("   - Monitor for consistency")
else:
    print("✅ GOOD: Sarvam API latency is acceptable")

if total_delivery/len(turns) > 5:
    print()
    print("🔴 CRITICAL: Delivery time is very high")
    print("   - Chunking/pacing may be too slow")
    print("   - Consider reducing sleep time between chunks")
