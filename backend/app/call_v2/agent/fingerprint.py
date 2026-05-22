"""Agent input fingerprinting for stale result protection."""

from __future__ import annotations

import json
from hashlib import sha256

from app.call_v2.agent.config import AgentInput


def agent_input_fingerprint(agent_input: AgentInput) -> str:
    payload = {
        "config_version": agent_input.agent_config.config_version,
        "generation_id": agent_input.generation_id,
        "conversation_message_ids": [
            message.message_id for message in agent_input.conversation
        ],
        "latest_user_turn": {
            "content_hash": _text_hash(agent_input.latest_user_turn.content),
        },
        "tool_schema": [
            {
                "name": tool.name,
                "arguments": [
                    {
                        "name": argument.name,
                        "kind": argument.kind,
                        "required": argument.required,
                    }
                    for argument in tool.arguments
                ],
                "side_effecting": tool.side_effecting,
            }
            for tool in agent_input.available_tools
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return sha256(normalized.encode("utf-8")).hexdigest()
