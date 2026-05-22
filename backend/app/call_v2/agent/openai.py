"""OpenAI structured model adapter for the call v2 agent."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI


class OpenAIStructuredModelError(RuntimeError):
    """Raised when OpenAI does not return a structured object."""


@dataclass(slots=True)
class OpenAIChatStructuredModel:
    """Uses OpenAI-compatible JSON mode behind the provider-neutral v2 model contract.

    Works with any OpenAI-compatible API (OpenAI, Groq, etc.) by optionally
    accepting a custom base_url.
    """

    api_key: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 320
    base_url: str | None = None
    client: Any | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self.client = AsyncOpenAI(**kwargs)

    async def ainvoke(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if isinstance(content, list):
            content = "".join(
                str(part.get("text") or part.get("content") or "")
                if isinstance(part, dict)
                else str(part)
                for part in content
            )
        if not isinstance(content, str) or not content.strip():
            raise OpenAIStructuredModelError("OpenAI returned empty structured content")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenAIStructuredModelError("OpenAI returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise OpenAIStructuredModelError("OpenAI structured content must be an object")
        return parsed
