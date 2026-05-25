"""Offline probe: compare Groq Scout vs gpt-oss-20b on the live agent prompt.

This script is a one-off benchmark. It does NOT modify any production code and
does NOT need the backend running. It reuses build_agent_config + the prompt
builders so the probe always reflects whatever the live prompt looks like.

Usage (from backend/):
    source venv/bin/activate
    python -m scripts.probe_groq_models

It prints:
    - Per-trial latency for each (scenario, model) combination
    - cached_tokens reported by Groq (only meaningful for models that support it)
    - The spoken_text + action returned, so we can eyeball instruction-following
    - A summary table at the end

Requires GROQ_API_KEY in the environment (loaded automatically from backend/.env
via app.config.get_settings).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from types import SimpleNamespace

# Make backend imports work when run as `python -m scripts.probe_groq_models`
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from openai import AsyncOpenAI

from app.call_v2.agent.config import (
    AgentInput,
    AgentVisibleCallState,
    ConversationMessage,
)
from app.call_v2.agent.prompts import build_system_prompt, build_turn_prompt
from app.call_v2.runtime import build_agent_config
from app.config import get_settings


# ----------------------------------------------------------------------------
# Stub CallV2Context — minimal namespaces, no DB access
# ----------------------------------------------------------------------------

def stub_context() -> SimpleNamespace:
    resume = SimpleNamespace(
        candidate_name="Shreyansh Pandey",
        email="shreyansh@example.com",
        phone_number="+910000000000",
        parsed_data={"skills": ["Python", "LangChain", "FastAPI"]},
        matching_score=85,
        match_explanation="Strong skills match",
    )
    job = SimpleNamespace(
        title="Junior AI Engineer",
        description=(
            "Build voice AI pipelines using Python, LangChain, FastAPI, and "
            "async I/O. Work on real-time STT/TTS systems. Help ship production "
            "features with a small founding team."
        ),
        requirements="Python, LangChain, FastAPI, async, REST APIs",
        evaluation_criteria="Communication, technical depth, problem solving",
    )
    questions = [
        SimpleNamespace(
            id=1,
            question_text="Tell me about your Python experience.",
            category="technical",
            difficulty="easy",
            order_index=0,
        ),
        SimpleNamespace(
            id=2,
            question_text="Have you worked with LangChain?",
            category="technical",
            difficulty="easy",
            order_index=1,
        ),
    ]
    call = SimpleNamespace(id="probe-call")
    return SimpleNamespace(resume=resume, job=job, questions=questions, call=call)


# ----------------------------------------------------------------------------
# AgentInput builder
# ----------------------------------------------------------------------------

def make_input(
    agent_config,
    conversation_pairs,
    latest_user_text,
    *,
    phase: str = "screening",
    consent: str = "unknown",
    last_assistant: str | None = None,
) -> AgentInput:
    """conversation_pairs: list of (role, text) tuples — chronological."""
    conversation: list[ConversationMessage] = []
    for i, (role, text) in enumerate(conversation_pairs):
        conversation.append(
            ConversationMessage(
                role=role,
                content=text,
                message_id=f"m{i}",
                generation_id=i,
                committed=True,
                interrupted=False,
                created_at_ms=i * 1000,
            )
        )
    latest = ConversationMessage(
        role="user",
        content=latest_user_text,
        message_id=f"m{len(conversation)}",
        generation_id=len(conversation),
        committed=False,
        interrupted=False,
        created_at_ms=len(conversation) * 1000,
    )
    last_msg = (
        last_assistant
        or next((m.content for m in reversed(conversation) if m.role == "assistant"), None)
    )
    return AgentInput(
        call_id="probe",
        generation_id=len(conversation) + 1,
        speculative=False,
        agent_config=agent_config,
        call_state=AgentVisibleCallState(
            phase=phase,
            consent_status=consent,
            previous_agent_action=None,
            covered_items=[],
            open_items=["q1", "q2"],
            last_assistant_message=last_msg,
            candidate_interrupted_last_turn=False,
            elapsed_call_seconds=len(conversation) * 5,
        ),
        conversation=conversation,
        latest_user_turn=latest,
        available_tools=[],
    )


# ----------------------------------------------------------------------------
# Scenarios — each probes a specific instruction-following invariant
# ----------------------------------------------------------------------------

OPENER = (
    "Hello Shreyansh Pandey, this is a screening call for the Junior AI "
    "Engineer position. This call may be recorded for quality purposes. Do "
    "I have your consent to proceed with a few questions?"
)
IDENTITY_ANSWER = (
    "I'm an AI assistant calling on behalf of Crownstack for a Junior AI "
    "Engineer screening interview."
)

SCENARIOS = [
    {
        "name": "1. Consent path: 'Sure'",
        "conversation": [("assistant", OPENER)],
        "user": "Sure.",
        "consent": "unknown",
        "expected": "Should move to first question; action=continue.",
    },
    {
        "name": "2. Identity probe: 'Who is this?'",
        "conversation": [("assistant", OPENER)],
        "user": "Who is this?",
        "consent": "unknown",
        "expected": "Identity answer + continue. MUST NOT repeat opener verbatim.",
    },
    {
        "name": "3. Re-identity probe (after answering already)",
        "conversation": [
            ("assistant", OPENER),
            ("user", "Who is this?"),
            ("assistant", IDENTITY_ANSWER),
        ],
        "user": "What do you want again?",
        "consent": "unknown",
        "expected": "MUST NOT verbatim-repeat the identity answer or the opener.",
    },
    {
        "name": "4. Busy decline: 'I am busy right now.'",
        "conversation": [("assistant", OPENER)],
        "user": "I am busy right now.",
        "consent": "unknown",
        "expected": "action=end_call_after_speaking. Brief polite reschedule.",
    },
    {
        "name": "5. Short answer to Python question",
        "conversation": [
            ("assistant", OPENER),
            ("user", "Sure."),
            ("assistant", "Great. Tell me about your Python experience."),
        ],
        "user": "I have one year of Python.",
        "consent": "granted",
        "expected": "MUST move to next question. MUST NOT drill on Python.",
    },
    {
        "name": "6. Long answer",
        "conversation": [
            ("assistant", OPENER),
            ("user", "Sure."),
            ("assistant", "Great. Tell me about your Python experience."),
        ],
        "user": (
            "I have one year of Python experience working with FastAPI and "
            "async I/O. Built a few production APIs and microservices."
        ),
        "consent": "granted",
        "expected": "MUST move to next question. No drill.",
    },
]


# ----------------------------------------------------------------------------
# Probe runner
# ----------------------------------------------------------------------------

async def probe_one(client: AsyncOpenAI, model: str, agent_input: AgentInput, trial: int, label: str = ""):
    messages = [
        {"role": "system", "content": build_system_prompt(agent_input)},
        {"role": "user", "content": build_turn_prompt(agent_input)},
    ]
    t0 = time.perf_counter()
    response = await client.chat.completions.create(
        model=model,
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

    # Groq surfaces cached prompt tokens. Newer OpenAI-compatible servers may
    # put them under prompt_tokens_details.cached_tokens; older ones expose
    # cached_tokens directly. Try both.
    usage = response.usage
    cached = getattr(usage, "cached_tokens", None)
    if cached is None:
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", None)

    return {
        "model": model,
        "label": label or model,
        "trial": trial,
        "elapsed_ms": elapsed_ms,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "cached_tokens": cached or 0,
        "spoken_text": parsed.get("spoken_text"),
        "action": parsed.get("action"),
        "parse_error": parsed.get("_parse_error", False),
    }


async def main():
    settings = get_settings()

    # Provider/model probes: list of dicts. Each describes one client
    # configuration to test. Keep the labels short for the printed columns.
    cerebras_key = os.environ.get("CEREBRAS_API_KEY") or ""
    probes: list[dict] = [
        # Current production baseline on Groq
        {
            "label": "groq-scout",
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "api_key": settings.GROQ_API_KEY,
            "base_url": settings.GROQ_BASE_URL,
        },
    ]
    sambanova_key = os.environ.get("SAMBANOVA_API_KEY") or ""
    if sambanova_key:
        # SambaNova account has: DeepSeek-V3.1/V3.2, Llama-4-Maverick, Llama-
        # 3.3-70B, MiniMax-M2.7, gemma-3-12b, gpt-oss-120b. Probe the four
        # candidates with distinct latency/quality profiles.
        probes.append({
            "label": "samba-maverick-17b",
            "model": "Llama-4-Maverick-17B-128E-Instruct",
            "api_key": sambanova_key,
            "base_url": "https://api.sambanova.ai/v1",
        })
        probes.append({
            "label": "samba-llama-3.3-70b",
            "model": "Meta-Llama-3.3-70B-Instruct",
            "api_key": sambanova_key,
            "base_url": "https://api.sambanova.ai/v1",
        })
        probes.append({
            "label": "samba-deepseek-v3.2",
            "model": "DeepSeek-V3.2",
            "api_key": sambanova_key,
            "base_url": "https://api.sambanova.ai/v1",
        })
        probes.append({
            "label": "samba-gpt-oss-120b",
            "model": "gpt-oss-120b",
            "api_key": sambanova_key,
            "base_url": "https://api.sambanova.ai/v1",
        })
    else:
        print("NOTE: SAMBANOVA_API_KEY not set — skipping SambaNova probes.")

    if cerebras_key:
        # Cerebras account has: gpt-oss-120b, llama3.1-8b, qwen-3-235b-a22b-
        # instruct-2507, zai-glm-4.7. Scout is NOT available here. Probe the
        # three Cerebras-exclusive candidates worth testing against Groq Scout.
        probes.append({
            "label": "cerebras-llama3.1-8b",
            "model": "llama3.1-8b",
            "api_key": cerebras_key,
            "base_url": "https://api.cerebras.ai/v1",
        })
        probes.append({
            "label": "cerebras-qwen3-235b",
            "model": "qwen-3-235b-a22b-instruct-2507",
            "api_key": cerebras_key,
            "base_url": "https://api.cerebras.ai/v1",
        })
        probes.append({
            "label": "cerebras-glm-4.7",
            "model": "zai-glm-4.7",
            "api_key": cerebras_key,
            "base_url": "https://api.cerebras.ai/v1",
        })
    else:
        print("NOTE: CEREBRAS_API_KEY not set — skipping Cerebras probes.")

    # Build a client per probe (each provider has its own base_url + key).
    clients = {
        p["label"]: AsyncOpenAI(api_key=p["api_key"], base_url=p["base_url"])
        for p in probes
    }

    ctx = stub_context()
    agent_config = build_agent_config(ctx)
    trials_per_combo = 3

    print(f"\nSystem prompt size: ~{len(build_system_prompt(make_input(agent_config, [], 'x'))):,} chars\n")
    print(f"Probes: {[p['label'] for p in probes]}\n")

    all_rows = []
    for scenario in SCENARIOS:
        print(f"\n{'=' * 95}")
        print(f"{scenario['name']}")
        print(f"  user: {scenario['user']!r}")
        print(f"  expected: {scenario['expected']}")
        print(f"{'=' * 95}")
        agent_input = make_input(
            agent_config,
            scenario["conversation"],
            scenario["user"],
            consent=scenario["consent"],
        )
        for probe in probes:
            label = probe["label"]
            client = clients[label]
            for trial in range(trials_per_combo):
                try:
                    row = await probe_one(
                        client, probe["model"], agent_input, trial, label=label
                    )
                except Exception as exc:
                    print(f"  [{label:<26}] trial {trial + 1}: ERROR — {exc}")
                    continue
                all_rows.append({**row, "scenario": scenario["name"]})
                spoken = (row["spoken_text"] or "").strip().replace("\n", " ")
                print(
                    f"  [{label:<26}] "
                    f"trial {trial + 1}  "
                    f"{row['elapsed_ms']:>5}ms  "
                    f"prompt={row['prompt_tokens']:>4}  "
                    f"cached={row['cached_tokens']:>4}  "
                    f"action={(row['action'] or '?')[:24]:<24}  "
                    f"→ {spoken[:90]}"
                )

    # ----- Summary -----
    print(f"\n{'=' * 95}\nSUMMARY\n{'=' * 95}\n")
    by_label: dict[str, list[dict]] = {}
    for r in all_rows:
        by_label.setdefault(r["label"], []).append(r)

    for label, rows in by_label.items():
        latencies = sorted(r["elapsed_ms"] for r in rows)
        prompt_tokens = [r["prompt_tokens"] for r in rows]
        cached_sum = sum(r["cached_tokens"] for r in rows)
        cache_hits = sum(1 for r in rows if r["cached_tokens"] > 0)
        action_counts: dict[str, int] = {}
        for r in rows:
            action_counts[r["action"] or "?"] = action_counts.get(r["action"] or "?", 0) + 1
        n = len(latencies)
        print(f"{label} ({rows[0]['model']})")
        print(f"  trials       : {n}")
        print(f"  latency  ms  : min {latencies[0]}  p50 {latencies[n // 2]}  max {latencies[-1]}  avg {sum(latencies) // n}")
        print(f"  prompt tokens: avg {sum(prompt_tokens) // len(prompt_tokens)}")
        print(f"  cache hits   : {cache_hits}/{n} requests had cached_tokens > 0, total cached {cached_sum}")
        print(f"  actions seen : {action_counts}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
