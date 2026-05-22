"""Agent input and configuration contracts for call v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.call_v2.agent.tools import ToolSpec


@dataclass(frozen=True, slots=True)
class CallScope:
    purpose: str
    allowed_topics: list[str] = field(default_factory=list)
    disallowed_topics: list[str] = field(default_factory=list)
    compliance_notes: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResponseStyle:
    tone: str = "professional"
    max_spoken_sentences: int = 2
    ask_one_thing_at_a_time: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentConfig:
    agent_name: str
    instructions: str
    scope: CallScope
    context: dict[str, Any] = field(default_factory=dict)
    objectives: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    response_style: ResponseStyle = field(default_factory=ResponseStyle)
    config_version: str = "call-agent.v1"
    opener_template: str = ""
    # Template variables are resolved from AgentConfig.context keys plus
    # standard runtime fields (candidate_name, job_title, company_name).
    # Use Python str.format_map syntax: "Hello {candidate_name}, ..."
    # Leave empty to let the agent generate the opener dynamically (default).

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentVisibleCallState:
    phase: str
    consent_status: Literal["unknown", "granted", "refused"]
    previous_agent_action: str | None = None
    covered_items: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    last_assistant_message: str | None = None
    candidate_interrupted_last_turn: bool = False
    elapsed_call_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: Literal["assistant", "user", "tool"]
    content: str
    message_id: str
    generation_id: int | None
    committed: bool
    interrupted: bool
    created_at_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentInput:
    call_id: str
    generation_id: int
    speculative: bool
    agent_config: AgentConfig
    call_state: AgentVisibleCallState
    conversation: list[ConversationMessage]
    latest_user_turn: ConversationMessage
    available_tools: list[ToolSpec] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "generation_id": self.generation_id,
            "speculative": self.speculative,
            "agent_config": self.agent_config.to_dict(),
            "call_state": self.call_state.to_dict(),
            "conversation": [message.to_dict() for message in self.conversation],
            "latest_user_turn": self.latest_user_turn.to_dict(),
            "available_tools": [tool.to_dict() for tool in self.available_tools],
        }
