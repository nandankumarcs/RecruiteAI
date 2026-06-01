"""
TTS Provider Benchmark — Sarvam vs Deepgram vs ElevenLabs
==========================================================
Measures time-to-first-byte (TTFB), total stream time, audio duration,
and estimates cost per provider.

Usage:
    cd backend
    source venv/bin/activate
    ELEVENLABS_API_KEY=sk_... python scripts/tts_benchmark.py

Required env vars (reads from .env automatically):
    SARVAM_API_KEY
    DEEPGRAM_API_KEY
    ELEVENLABS_API_KEY   (optional — provider skipped if absent)

No existing app code is imported. Fully standalone.
"""

from __future__ import annotations

import asyncio
import io
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

import aiohttp
from dotenv import load_dotenv

# ── Load .env from backend/ ──────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

SARVAM_API_KEY    = os.environ.get("SARVAM_API_KEY", "")
DEEPGRAM_API_KEY  = os.environ.get("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

# ── Pricing constants (USD) ───────────────────────────────────────────────────
# Sarvam: ₹30 / 10K chars → at ₹84/USD ≈ $0.00036 / char
SARVAM_COST_PER_CHAR_USD   = 30.0 / 84.0 / 10_000
# Deepgram Aura: $0.030 / 1K chars
DEEPGRAM_COST_PER_CHAR_USD = 0.030 / 1_000
# ElevenLabs Flash v2.5: $0.11 / 1K chars (pay-as-you-go)
ELEVENLABS_COST_PER_CHAR_USD = 0.11 / 1_000

# ── Test phrases (realistic interview sentences) ──────────────────────────────
TEST_PHRASES = [
    # Short acknowledgement
    "That's great, thank you.",
    # Medium question
    "Can you tell me about a specific project where you used React and how you handled state management?",
    # Long agent turn
    (
        "That's really interesting. You've worked with some solid technologies. "
        "Let me ask — when you hit a tricky bug in production with limited tooling, "
        "how do you typically approach debugging it?"
    ),
]


# ── Result container ──────────────────────────────────────────────────────────
@dataclass
class RunResult:
    provider: str
    phrase_index: int
    char_count: int
    ttfb_ms: float          # ms to first audio byte
    total_ms: float         # ms to last audio byte
    audio_bytes: int
    error: str | None = None

    @property
    def audio_duration_ms(self) -> float:
        """Rough estimate based on provider output format."""
        return 0.0  # filled by each provider


@dataclass
class ProviderSummary:
    provider: str
    runs: list[RunResult] = field(default_factory=list)

    def valid_runs(self) -> list[RunResult]:
        return [r for r in self.runs if r.error is None]

    def avg_ttfb_ms(self) -> float:
        v = [r.ttfb_ms for r in self.valid_runs()]
        return statistics.mean(v) if v else 0.0

    def avg_total_ms(self) -> float:
        v = [r.total_ms for r in self.valid_runs()]
        return statistics.mean(v) if v else 0.0

    def total_chars(self) -> int:
        return sum(r.char_count for r in self.valid_runs())

    def cost_usd(self, cost_per_char: float) -> float:
        return self.total_chars() * cost_per_char

    def cost_per_1k_chars_usd(self, cost_per_char: float) -> float:
        return cost_per_char * 1_000


# ── Sarvam TTS ────────────────────────────────────────────────────────────────
async def stream_sarvam(session: aiohttp.ClientSession, text: str) -> RunResult:
    url = "https://api.sarvam.ai/text-to-speech/stream"
    payload = {
        "text": text,
        "target_language_code": "en-IN",
        "speaker": "priya",
        "model": "bulbul:v3",
        "pace": 1.2,
        "sample_rate": 8000,
        "enable_preprocessing": False,
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    ttfb_ms = None
    total_bytes = 0
    error = None

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                return RunResult("sarvam", -1, len(text), 0, 0, 0, error=f"HTTP {resp.status}: {body[:120]}")
            async for chunk in resp.content.iter_chunked(2048):
                if chunk:
                    if ttfb_ms is None:
                        ttfb_ms = (time.perf_counter() - t0) * 1000
                    total_bytes += len(chunk)
    except Exception as exc:
        error = str(exc)

    total_ms = (time.perf_counter() - t0) * 1000
    return RunResult("sarvam", -1, len(text), ttfb_ms or 0, total_ms, total_bytes, error=error)


# ── Deepgram Aura TTS ─────────────────────────────────────────────────────────
async def stream_deepgram(session: aiohttp.ClientSession, text: str) -> RunResult:
    # Deepgram Aura TTS streams linear16 PCM at 24000 Hz
    url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=8000"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"text": text}
    t0 = time.perf_counter()
    ttfb_ms = None
    total_bytes = 0
    error = None

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                return RunResult("deepgram", -1, len(text), 0, 0, 0, error=f"HTTP {resp.status}: {body[:120]}")
            async for chunk in resp.content.iter_chunked(2048):
                if chunk:
                    if ttfb_ms is None:
                        ttfb_ms = (time.perf_counter() - t0) * 1000
                    total_bytes += len(chunk)
    except Exception as exc:
        error = str(exc)

    total_ms = (time.perf_counter() - t0) * 1000
    return RunResult("deepgram", -1, len(text), ttfb_ms or 0, total_ms, total_bytes, error=error)


# ── ElevenLabs Flash TTS ──────────────────────────────────────────────────────
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — neutral English female

async def stream_elevenlabs(session: aiohttp.ClientSession, text: str) -> RunResult:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_flash_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        "output_format": "mp3_22050_32",
    }
    t0 = time.perf_counter()
    ttfb_ms = None
    total_bytes = 0
    error = None

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                body = await resp.text()
                return RunResult("elevenlabs", -1, len(text), 0, 0, 0, error=f"HTTP {resp.status}: {body[:120]}")
            async for chunk in resp.content.iter_chunked(2048):
                if chunk:
                    if ttfb_ms is None:
                        ttfb_ms = (time.perf_counter() - t0) * 1000
                    total_bytes += len(chunk)
    except Exception as exc:
        error = str(exc)

    total_ms = (time.perf_counter() - t0) * 1000
    return RunResult("elevenlabs", -1, len(text), ttfb_ms or 0, total_ms, total_bytes, error=error)


# ── Audio duration helpers ─────────────────────────────────────────────────────
def pcm_duration_ms(byte_count: int, sample_rate: int = 8000, channels: int = 1, bits: int = 16) -> float:
    bytes_per_sample = bits // 8
    bytes_per_sec = sample_rate * channels * bytes_per_sample
    return (byte_count / bytes_per_sec) * 1000 if bytes_per_sec else 0


# ── Main benchmark ─────────────────────────────────────────────────────────────
REPEATS = 3  # runs per phrase per provider to average out jitter

async def benchmark_provider(
    name: str,
    key: str,
    stream_fn,
    session: aiohttp.ClientSession,
) -> ProviderSummary:
    summary = ProviderSummary(provider=name)
    if not key:
        print(f"  [{name}] SKIPPED — no API key")
        return summary

    for phrase_idx, phrase in enumerate(TEST_PHRASES):
        run_ttfbs, run_totals, run_bytes = [], [], []
        run_error = None

        for run in range(REPEATS):
            result = await stream_fn(session, phrase)
            result.phrase_index = phrase_idx
            summary.runs.append(result)

            if result.error:
                run_error = result.error
                print(f"  [{name}] phrase={phrase_idx} run={run+1} ERROR: {result.error}")
                break
            else:
                run_ttfbs.append(result.ttfb_ms)
                run_totals.append(result.total_ms)
                run_bytes.append(result.audio_bytes)
                print(
                    f"  [{name}] phrase={phrase_idx} run={run+1} "
                    f"ttfb={result.ttfb_ms:.0f}ms  total={result.total_ms:.0f}ms  "
                    f"bytes={result.audio_bytes:,}"
                )
            await asyncio.sleep(0.3)  # avoid rate limits

    return summary


async def main():
    providers = [
        ("sarvam",     SARVAM_API_KEY,     stream_sarvam),
        ("deepgram",   DEEPGRAM_API_KEY,   stream_deepgram),
        ("elevenlabs", ELEVENLABS_API_KEY, stream_elevenlabs),
    ]

    cost_map = {
        "sarvam":     SARVAM_COST_PER_CHAR_USD,
        "deepgram":   DEEPGRAM_COST_PER_CHAR_USD,
        "elevenlabs": ELEVENLABS_COST_PER_CHAR_USD,
    }

    summaries: list[ProviderSummary] = []

    print("\n" + "═" * 60)
    print("  TTS BENCHMARK  —  Sarvam · Deepgram · ElevenLabs")
    print("═" * 60)
    print(f"  Phrases: {len(TEST_PHRASES)}  ×  Repeats: {REPEATS}  =  {len(TEST_PHRASES)*REPEATS} runs/provider\n")

    # Print phrase summary
    for i, p in enumerate(TEST_PHRASES):
        print(f"  Phrase {i}: [{len(p)} chars] {p[:60]}{'…' if len(p)>60 else ''}")
    print()

    connector = aiohttp.TCPConnector(limit=5)
    async with aiohttp.ClientSession(connector=connector) as session:
        for name, key, fn in providers:
            print(f"── {name.upper()} {'─'*(50-len(name))}")
            summary = await benchmark_provider(name, key, fn, session)
            summaries.append(summary)
            print()

    # ── Results table ────────────────────────────────────────────────────────
    COST_PER_CHAR = {k: v for k, v in cost_map.items()}

    # Compute per-phrase averages
    phrase_rows: dict[str, list[tuple[float,float]]] = {}  # provider → [(ttfb, total), ...]
    for s in summaries:
        phrase_rows[s.provider] = []
        for pi in range(len(TEST_PHRASES)):
            runs = [r for r in s.valid_runs() if r.phrase_index == pi]
            if runs:
                phrase_rows[s.provider].append((
                    statistics.mean(r.ttfb_ms for r in runs),
                    statistics.mean(r.total_ms for r in runs),
                ))
            else:
                phrase_rows[s.provider].append((0.0, 0.0))

    print("\n" + "═" * 60)
    print("  RESULTS SUMMARY")
    print("═" * 60)

    # Per-phrase table
    phrase_labels = ["Short (25c)", "Medium (98c)", "Long (252c)"]
    col_w = 18
    header = f"  {'Phrase':<14}" + "".join(f"{'TTFB':>{col_w}}{'Total':>{col_w}}" for _ in summaries)
    print(f"\n  Per-phrase latency (avg of {REPEATS} runs):\n")
    print(f"  {'':14}" + "".join(f"{'─ '+s.provider.upper()+' ─':^{col_w*2}}" for s in summaries))
    print(f"  {'Phrase':<14}" + "".join(f"{'TTFB (ms)':>{col_w}}{'Total (ms)':>{col_w}}" for _ in summaries))
    print(f"  {'─'*14}" + ("─"*(col_w*2) * len(summaries)))

    for pi, label in enumerate(phrase_labels):
        row = f"  {label:<14}"
        for s in summaries:
            rows = phrase_rows.get(s.provider, [])
            if pi < len(rows) and rows[pi][0] > 0:
                ttfb, total = rows[pi]
                row += f"{ttfb:>{col_w}.0f}{total:>{col_w}.0f}"
            else:
                row += f"{'—':>{col_w}}{'—':>{col_w}}"
        print(row)

    # Overall averages
    print(f"\n  {'─'*14}" + ("─"*(col_w*2) * len(summaries)))
    avg_row = f"  {'AVERAGE':<14}"
    for s in summaries:
        if s.valid_runs():
            avg_row += f"{s.avg_ttfb_ms():>{col_w}.0f}{s.avg_total_ms():>{col_w}.0f}"
        else:
            avg_row += f"{'—':>{col_w}}{'—':>{col_w}}"
    print(avg_row)

    # Pricing table
    print(f"\n  {'─'*60}")
    print(f"\n  Pricing (public list prices, USD):\n")
    print(f"  {'Provider':<14}{'Per 1K chars':>16}{'Per 10K chars':>16}{'vs cheapest':>14}")
    print(f"  {'─'*14}{'─'*16}{'─'*16}{'─'*14}")

    min_cost = min((COST_PER_CHAR[s.provider] for s in summaries if s.valid_runs()), default=1)
    for s in summaries:
        cpc = COST_PER_CHAR[s.provider]
        per1k = cpc * 1_000
        per10k = cpc * 10_000
        ratio = cpc / min_cost if min_cost > 0 else 0
        indicator = "◀ cheapest" if ratio == 1.0 else f"{ratio:.1f}×"
        print(f"  {s.provider:<14}{per1k:>15.4f}{'$':>1}{per10k:>15.4f}{'$':>1}{indicator:>14}")

    # Notes on audio quality
    print(f"\n  Notes:")
    print(f"  • Sarvam:     8kHz linear16 PCM, en-IN accent (Indian English), HTTP stream")
    print(f"  • Deepgram:   8kHz linear16 PCM, en-US accent (Aura Asteria), HTTP stream")
    print(f"  • ElevenLabs: MP3 22050Hz 32kbps, en-US accent (Rachel / Flash v2.5), HTTP stream")
    print(f"  • TTFB = time to first audio byte from request sent")
    print(f"  • Sarvam pricing: ₹30/10K chars converted at ₹84/USD")
    print(f"  • ElevenLabs pricing: Flash v2.5 pay-as-you-go (~$0.11/1K chars)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
