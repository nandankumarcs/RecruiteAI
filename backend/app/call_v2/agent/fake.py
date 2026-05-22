"""Deterministic fake agent runner for call v2 tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.call_v2.agent.config import AgentInput
from app.call_v2.agent.output import AgentOutput, validate_agent_output


@dataclass(slots=True)
class FakeAgentRunner:
    outputs: list[dict[str, Any] | AgentOutput] = field(default_factory=list)
    calls: list[AgentInput] = field(default_factory=list)

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        self.calls.append(agent_input)
        if not self.outputs:
            raise RuntimeError("FakeAgentRunner has no queued outputs")
        raw = self.outputs.pop(0)
        return validate_agent_output(
            raw,
            available_tools=agent_input.available_tools,
            speculative=agent_input.speculative,
        )
