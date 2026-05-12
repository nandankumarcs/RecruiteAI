"""Pricing and cost estimation helpers for AI and telephony runtimes."""

from __future__ import annotations

from typing import Any

from app.config import get_settings

settings = get_settings()


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_currency(value: float) -> float:
    return round(max(value, 0.0), 6)


def estimate_openai_text_cost(
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> float:
    input_cost = (_safe_float(input_tokens) / 1_000_000.0) * settings.OPENAI_TEXT_INPUT_COST_PER_1M
    output_cost = (_safe_float(output_tokens) / 1_000_000.0) * settings.OPENAI_TEXT_OUTPUT_COST_PER_1M
    return _round_currency(input_cost + output_cost)


def estimate_openai_realtime_cost(
    *,
    text_input_tokens: int | None = None,
    text_output_tokens: int | None = None,
    audio_input_tokens: int | None = None,
    audio_output_tokens: int | None = None,
) -> float:
    text_input_cost = (
        _safe_float(text_input_tokens) / 1_000_000.0
    ) * settings.OPENAI_REALTIME_TEXT_INPUT_COST_PER_1M
    text_output_cost = (
        _safe_float(text_output_tokens) / 1_000_000.0
    ) * settings.OPENAI_REALTIME_TEXT_OUTPUT_COST_PER_1M
    audio_input_cost = (
        _safe_float(audio_input_tokens) / 1_000_000.0
    ) * settings.OPENAI_REALTIME_AUDIO_INPUT_COST_PER_1M
    audio_output_cost = (
        _safe_float(audio_output_tokens) / 1_000_000.0
    ) * settings.OPENAI_REALTIME_AUDIO_OUTPUT_COST_PER_1M
    return _round_currency(
        text_input_cost + text_output_cost + audio_input_cost + audio_output_cost
    )


def estimate_deepgram_stt_cost(*, duration_seconds: int | float | None) -> float:
    minutes = _safe_float(duration_seconds) / 60.0
    return _round_currency(minutes * settings.DEEPGRAM_STT_COST_PER_MINUTE_USD)


def estimate_deepgram_tts_cost(*, characters: int | None) -> float:
    chars = _safe_float(characters)
    return _round_currency((chars / 1000.0) * settings.DEEPGRAM_TTS_COST_PER_1K_CHARS_USD)


def estimate_telephony_cost(*, provider: str, duration_seconds: int | None) -> float:
    minutes = _safe_float(duration_seconds) / 60.0
    rate = 0.0
    if provider == "twilio":
        rate = settings.TWILIO_ESTIMATED_COST_PER_MINUTE_USD
    elif provider == "exotel":
        rate = settings.EXOTEL_ESTIMATED_COST_PER_MINUTE_USD
    return _round_currency(minutes * rate)


def hydrate_cost_breakdown(
    *,
    existing: dict | None,
    provider: str | None,
    duration_seconds: int | None,
) -> dict | None:
    normalized_provider = (provider or "unknown").lower()
    has_existing = isinstance(existing, dict) and bool(existing)
    telephony_cost = estimate_telephony_cost(
        provider=normalized_provider,
        duration_seconds=duration_seconds,
    )

    if has_existing:
        costs = dict((existing or {}).get("costs") or {})
        if telephony_cost and not costs.get("telephony_usd"):
            costs["telephony_usd"] = telephony_cost

        total = _safe_float((existing or {}).get("estimated_total_usd"))
        if total <= 0 and costs:
            total = sum(_safe_float(value) for value in costs.values())

        hydrated = dict(existing or {})
        hydrated["provider"] = normalized_provider
        hydrated["currency"] = hydrated.get("currency") or "USD"
        hydrated["costs"] = costs
        hydrated["estimated_total_usd"] = _round_currency(total)
        return hydrated

    if telephony_cost <= 0:
        return None

    return {
        "currency": "USD",
        "provider": normalized_provider,
        "costs": {
            "telephony_usd": telephony_cost,
        },
        "estimated_total_usd": telephony_cost,
        "notes": ["legacy_call_estimate=telephony_only"],
    }


def merge_cost_breakdown(
    existing: dict | None,
    *,
    provider: str,
    llm_cost_usd: float | None = None,
    telephony_cost_usd: float | None = None,
    stt_cost_usd: float | None = None,
    tts_cost_usd: float | None = None,
    usage: dict | None = None,
    notes: list[str] | None = None,
) -> dict:
    base = dict(existing or {})
    costs = dict(base.get("costs") or {})
    if llm_cost_usd is not None:
        costs["llm_usd"] = _round_currency(llm_cost_usd)
    if telephony_cost_usd is not None:
        costs["telephony_usd"] = _round_currency(telephony_cost_usd)
    if stt_cost_usd is not None:
        costs["stt_usd"] = _round_currency(stt_cost_usd)
    if tts_cost_usd is not None:
        costs["tts_usd"] = _round_currency(tts_cost_usd)
    total = sum(_safe_float(value) for value in costs.values())
    base.update(
        {
            "currency": "USD",
            "provider": provider,
            "costs": costs,
            "estimated_total_usd": _round_currency(total),
        }
    )
    if usage:
        base["usage"] = usage
    if notes:
        merged_notes = list(base.get("notes") or [])
        for note in notes:
            if note not in merged_notes:
                merged_notes.append(note)
        base["notes"] = merged_notes
    return base
