"""Shared model construction helpers for traced, structured text agents."""

from __future__ import annotations

from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()

try:
    from langchain_openai import ChatOpenAI
except Exception:  # pragma: no cover
    ChatOpenAI = None


def build_structured_chat_model(
    *,
    schema: type[BaseModel],
    run_name: str,
    metadata: dict | None = None,
):
    if ChatOpenAI is None:
        return None

    llm = ChatOpenAI(
        model=settings.OPENAI_TEXT_MODEL or settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        stream_usage=True,
    ).with_config(
        {
            "run_name": run_name,
            "tags": ["recruiteai", run_name],
            "metadata": metadata or {},
        }
    )
    return llm.with_structured_output(
        schema,
        include_raw=True,
        method="function_calling",
    )
