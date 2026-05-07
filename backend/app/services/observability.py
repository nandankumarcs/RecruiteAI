"""Shared helpers for tracing, usage capture, and call metrics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.services.pricing import estimate_openai_text_cost

settings = get_settings()
logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_usage_metadata(raw_usage: Any) -> dict:
    if not isinstance(raw_usage, dict):
        return {}

    input_tokens = raw_usage.get("input_tokens") or raw_usage.get("prompt_tokens") or 0
    output_tokens = raw_usage.get("output_tokens") or raw_usage.get("completion_tokens") or 0
    total_tokens = raw_usage.get("total_tokens") or (input_tokens + output_tokens)
    normalized = {
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }
    for key in (
        "input_token_details",
        "output_token_details",
        "audio_input_tokens",
        "audio_output_tokens",
        "reasoning_tokens",
    ):
        value = raw_usage.get(key)
        if value is not None:
            normalized[key] = value
    return normalized


def summarize_text_model_usage(*, agent_name: str, model: str, usage: dict | None, metadata: dict | None = None) -> dict:
    normalized = normalize_usage_metadata(usage)
    estimated_cost_usd = estimate_openai_text_cost(
        input_tokens=normalized.get("input_tokens"),
        output_tokens=normalized.get("output_tokens"),
    )
    payload = {
        "agent": agent_name,
        "model": model,
        "usage": normalized,
        "estimated_cost_usd": estimated_cost_usd,
        "metadata": metadata or {},
        "timestamp": utc_now_iso(),
    }
    logger.info("ai_usage %s", payload)
    return payload


def merge_latency_metric(existing: dict | None, *, key: str, value: Any) -> dict:
    data = dict(existing or {})
    data[key] = value
    return data


def append_latency_marker(existing: dict | None, *, key: str) -> dict:
    return merge_latency_metric(existing, key=key, value=utc_now_iso())
