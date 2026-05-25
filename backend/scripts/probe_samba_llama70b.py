"""Focused probe: SambaNova Llama-3.3-70B-Instruct on the live agent prompt.

Single model, paced requests to avoid SambaNova free-tier rate limits / balance
exhaustion. Same 6 scenarios as scripts/probe_groq_models.py.

Usage (from backend/):
    source venv/bin/activate
    SAMBANOVA_API_KEY=... python -m scripts.probe_samba_llama70b

Defaults:
    - 3 trials per scenario (18 total requests)
    - 8 seconds sleep between requests (~2.4 minute total)

Tune via env:
    PROBE_TRIALS=2          # trials per scenario
    PROBE_SLEEP_S=10        # sleep between requests
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

# Reuse helpers from the existing probe script.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from openai import AsyncOpenAI

from app.call_v2.agent.prompts import build_system_prompt, build_turn_prompt
from app.call_v2.runtime import build_agent_config
from scripts.probe_groq_models import SCENARIOS, make_input, stub_context


MODEL = "Meta-Llama-3.3-70B-Instruct"
BASE_URL = "https://api.sambanova.ai/v1"


async def probe_one(client: AsyncOpenAI, agent_input, trial: int):
    messages = [
        {"role": "system", "content": build_system_prompt(agent_input)},
        {"role": "user", "content": build_turn_prompt(agent_input)},
    ]
    t0 = time.perf_counter()
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2,
        max_tokens=320,
        response_format={"type": "json_object"},
    )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    content = response.choices[0].message.content or ""
    try:
        parsed = json.loads(content)
    except Exception:
        parsed = {"_parse_error": True, "raw": content[:200]}
    return {
        "trial": trial,
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "spoken_text": parsed.get("spoken_text"),
        "action": parsed.get("action"),
        "parse_error": parsed.get("_parse_error", False),
    }


async def main():
    api_key = os.environ.get("SAMBANOVA_API_KEY")
    if not api_key:
        raise SystemExit("SAMBANOVA_API_KEY missing.")
    trials = int(os.environ.get("PROBE_TRIALS", "3"))
    sleep_s = float(os.environ.get("PROBE_SLEEP_S", "8"))

    client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
    agent_config = build_agent_config(stub_context())

    print(f"Model: {MODEL}")
    print(f"Pacing: {trials} trials/scenario, {sleep_s}s sleep between requests")
    print(f"Estimated runtime: ~{int(len(SCENARIOS) * trials * sleep_s)}s\n")

    all_rows: list[dict] = []
    request_idx = 0
    total_requests = len(SCENARIOS) * trials

    for scenario in SCENARIOS:
        print(f"\n{'=' * 90}")
        print(f"{scenario['name']}")
        print(f"  user: {scenario['user']!r}")
        print(f"  expected: {scenario['expected']}")
        print(f"{'=' * 90}")
        agent_input = make_input(
            agent_config,
            scenario["conversation"],
            scenario["user"],
            consent=scenario["consent"],
        )
        for trial in range(trials):
            request_idx += 1
            try:
                row = await probe_one(client, agent_input, trial)
            except Exception as exc:
                print(f"  trial {trial + 1} ({request_idx}/{total_requests}): ERROR — {exc}")
                # Even on error, pace the next request so we don't pile on
                if request_idx < total_requests:
                    await asyncio.sleep(sleep_s)
                continue
            all_rows.append({**row, "scenario": scenario["name"]})
            spoken = (row["spoken_text"] or "").strip().replace("\n", " ")
            print(
                f"  trial {trial + 1} ({request_idx}/{total_requests})  "
                f"{row['elapsed_ms']:>5}ms  "
                f"prompt={row['prompt_tokens']:>4}  "
                f"action={(row['action'] or '?')[:24]:<24}  "
                f"→ {spoken[:90]}"
            )
            # Pace: sleep between every request except the last.
            if request_idx < total_requests:
                await asyncio.sleep(sleep_s)

    # ----- Summary -----
    print(f"\n{'=' * 90}\nSUMMARY\n{'=' * 90}")
    if not all_rows:
        print("No successful trials.")
        return
    latencies = sorted(r["elapsed_ms"] for r in all_rows)
    n = len(latencies)
    action_counts: dict[str, int] = {}
    for r in all_rows:
        action_counts[r["action"] or "?"] = action_counts.get(r["action"] or "?", 0) + 1
    print(f"\nModel: {MODEL}")
    print(f"  successful trials : {n} / {total_requests}")
    print(
        f"  latency  ms       : min {latencies[0]}  p50 {latencies[n // 2]}  "
        f"max {latencies[-1]}  avg {sum(latencies) // n}"
    )
    print(f"  actions seen      : {action_counts}")

    # Per-scenario detail
    print("\nPer-scenario breakdown:")
    by_scenario: dict[str, list[dict]] = {}
    for r in all_rows:
        by_scenario.setdefault(r["scenario"], []).append(r)
    for scenario_name, rows in by_scenario.items():
        s_lat = [r["elapsed_ms"] for r in rows]
        s_actions = {r["action"] for r in rows}
        print(f"  {scenario_name}")
        print(f"    trials       : {len(rows)}")
        print(f"    latency  ms  : min {min(s_lat)}  median {sorted(s_lat)[len(s_lat) // 2]}  max {max(s_lat)}")
        print(f"    actions      : {s_actions}")


if __name__ == "__main__":
    asyncio.run(main())
