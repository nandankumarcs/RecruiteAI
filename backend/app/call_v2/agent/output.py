"""Structured agent output validation for call v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.call_v2.agent.tools import ToolSpec, validate_tool_arguments


AgentAction = Literal[
    "continue",
    "pause_for_user",
    "end_call_after_speaking",
    "technical_recovery",
]

ALLOWED_ACTIONS: set[str] = {
    "continue",
    "pause_for_user",
    "end_call_after_speaking",
    "technical_recovery",
}


class AgentOutputValidationError(ValueError):
    """Raised when an LLM output fails the call v2 structured contract."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    call_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentOutput:
    spoken_text: str
    action: AgentAction
    tool_calls: list[ToolCall] = field(default_factory=list)
    state_updates: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    internal_notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spoken_text": self.spoken_text,
            "action": self.action,
            "tool_calls": [tool_call.to_dict() for tool_call in self.tool_calls],
            "state_updates": self.state_updates,
            "confidence": self.confidence,
            "internal_notes": self.internal_notes,
        }


def validate_agent_output(
    raw: dict[str, Any] | AgentOutput,
    *,
    available_tools: list[ToolSpec],
    speculative: bool,
) -> AgentOutput:
    if isinstance(raw, AgentOutput):
        output = raw
    elif isinstance(raw, dict):
        output = _parse_output(raw)
    else:
        raise AgentOutputValidationError("agent output must be an object")

    if not isinstance(output.spoken_text, str):
        raise AgentOutputValidationError("spoken_text must be text")
    _validate_spoken_text(output.spoken_text)
    if output.action not in ALLOWED_ACTIONS:
        raise AgentOutputValidationError(f"unknown agent action {output.action!r}")
    if output.confidence is not None:
        if isinstance(output.confidence, bool):
            raise AgentOutputValidationError("confidence must be numeric")
        if not 0 <= output.confidence <= 1:
            raise AgentOutputValidationError("confidence must be between 0 and 1")
    _validate_tool_calls(
        output.tool_calls,
        available_tools=available_tools,
        speculative=speculative,
    )
    return output


def technical_recovery_output() -> AgentOutput:
    return AgentOutput(
        spoken_text=(
            "I'm sorry, I ran into a technical issue. "
            "We'll end the call here and follow up later."
        ),
        action="end_call_after_speaking",
        tool_calls=[],
        state_updates={"technical_recovery": True},
        confidence=None,
        internal_notes="structured output validation failed twice",
    )


def _parse_output(raw: dict[str, Any]) -> AgentOutput:
    spoken_text = raw.get("spoken_text")
    if not isinstance(spoken_text, str) or not spoken_text.strip():
        raise AgentOutputValidationError("spoken_text is required")

    action = raw.get("action")
    if not isinstance(action, str):
        raise AgentOutputValidationError("action is required")

    tool_calls = raw.get("tool_calls", [])
    if not isinstance(tool_calls, list):
        raise AgentOutputValidationError("tool_calls must be a list")

    state_updates = raw.get("state_updates", {})
    if not isinstance(state_updates, dict):
        raise AgentOutputValidationError("state_updates must be an object")

    confidence = raw.get("confidence")
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, int | float)
    ):
        raise AgentOutputValidationError("confidence must be numeric")

    internal_notes = raw.get("internal_notes")
    if internal_notes is not None and not isinstance(internal_notes, str):
        raise AgentOutputValidationError("internal_notes must be text")

    return AgentOutput(
        spoken_text=" ".join(spoken_text.split()),
        action=action,  # type: ignore[arg-type]
        tool_calls=[_parse_tool_call(item) for item in tool_calls],
        state_updates=state_updates,
        confidence=float(confidence) if confidence is not None else None,
        internal_notes=internal_notes,
    )


def _parse_tool_call(raw: Any) -> ToolCall:
    if not isinstance(raw, dict):
        raise AgentOutputValidationError("tool call must be an object")
    tool_name = raw.get("tool_name")
    arguments = raw.get("arguments")
    call_id = raw.get("call_id")
    if not isinstance(tool_name, str) or not tool_name:
        raise AgentOutputValidationError("tool_name is required")
    if not isinstance(arguments, dict):
        raise AgentOutputValidationError("tool arguments must be an object")
    if not isinstance(call_id, str) or not call_id:
        raise AgentOutputValidationError("tool call_id is required")
    return ToolCall(tool_name=tool_name, arguments=arguments, call_id=call_id)


def _validate_spoken_text(spoken_text: str) -> None:
    stripped = spoken_text.strip()
    if stripped.startswith(("{", "[")):
        raise AgentOutputValidationError("spoken_text must not contain JSON")
    lowered = stripped.lower()
    if lowered.startswith(("assistant:", "candidate:", "user:", "system:")):
        raise AgentOutputValidationError("spoken_text must not include role labels")
    if "```" in stripped:
        raise AgentOutputValidationError("spoken_text must not include Markdown code")


def _validate_tool_calls(
    tool_calls: list[ToolCall],
    *,
    available_tools: list[ToolSpec],
    speculative: bool,
) -> None:
    if speculative and tool_calls:
        raise AgentOutputValidationError("speculative runs cannot request tool calls")

    tools_by_name = {tool.name: tool for tool in available_tools}
    for tool_call in tool_calls:
        tool = tools_by_name.get(tool_call.tool_name)
        if tool is None:
            raise AgentOutputValidationError(
                f"unknown tool {tool_call.tool_name!r}"
            )
        try:
            validate_tool_arguments(tool=tool, arguments=tool_call.arguments)
        except ValueError as exc:
            raise AgentOutputValidationError(str(exc)) from exc
