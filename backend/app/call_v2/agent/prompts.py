"""Prompt rendering for the call v2 agent boundary."""

from __future__ import annotations

import json

from app.call_v2.agent.config import AgentInput


RESPONSE_FORMAT_INSTRUCTIONS = """Return only a structured object with:
- spoken_text: plain text intended for TTS
- action: one of continue, pause_for_user, end_call_after_speaking, technical_recovery
- tool_calls: list of tool calls
- state_updates: object
- confidence: number between 0 and 1, or null
- internal_notes: private trace notes, or null
Do not include role labels, Markdown, JSON snippets inside spoken_text, or implementation details."""


REPAIR_INSTRUCTIONS = """Your previous response did not satisfy the required structured output contract. Return one valid structured object only."""


def build_system_prompt(agent_input: AgentInput) -> str:
    config = agent_input.agent_config
    sections = [
        "# Agent Identity",
        config.agent_name,
        "# Purpose",
        config.scope.purpose,
        "# Instructions",
        config.instructions,
        "# Scope",
        _json_block(config.scope.to_dict()),
        "# Objectives",
        _list_block(config.objectives),
        "# Constraints",
        _list_block(config.constraints),
        "# Response Style",
        _json_block(config.response_style.to_dict()),
        "# Static Context",
        _json_block(config.context),
        "# Available Tools",
        _json_block([tool.to_dict() for tool in agent_input.available_tools]),
        "# Response Format",
        RESPONSE_FORMAT_INSTRUCTIONS,
    ]
    return "\n\n".join(sections)


def build_turn_prompt(
    agent_input: AgentInput,
    *,
    repair: bool = False,
) -> str:
    payload = {
        "call_id": agent_input.call_id,
        "generation_id": agent_input.generation_id,
        "speculative": agent_input.speculative,
        "call_state": agent_input.call_state.to_dict(),
        "conversation": [message.to_dict() for message in agent_input.conversation],
        "latest_user_turn": agent_input.latest_user_turn.to_dict(),
    }
    sections = ["# Current Turn", _json_block(payload)]
    if repair:
        sections.append(REPAIR_INSTRUCTIONS)
    return "\n\n".join(sections)


def _json_block(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2)


def _list_block(items: list[str]) -> str:
    if not items:
        return "[]"
    return "\n".join(f"- {item}" for item in items)
