"""Agent runner interfaces for call v2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.call_v2.agent.config import AgentInput
from app.call_v2.agent.output import (
    AgentOutput,
    AgentOutputValidationError,
    technical_recovery_output,
    validate_agent_output,
)
from app.call_v2.agent.prompts import build_system_prompt, build_turn_prompt


class AgentRunner(Protocol):
    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """Return a validated structured response for one agent turn."""


class StructuredModel(Protocol):
    async def ainvoke(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Invoke a provider-backed structured model.

        The concrete provider must return the parsed structured object. The
        runner owns validation and one repair retry.
        """


@dataclass(slots=True)
class StructuredModelAgentRunner:
    model: StructuredModel

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        first_raw = await self.model.ainvoke(
            [
                {"role": "system", "content": build_system_prompt(agent_input)},
                {"role": "user", "content": build_turn_prompt(agent_input)},
            ]
        )
        try:
            return validate_agent_output(
                first_raw,
                available_tools=agent_input.available_tools,
                speculative=agent_input.speculative,
            )
        except AgentOutputValidationError:
            repair_raw = await self.model.ainvoke(
                [
                    {"role": "system", "content": build_system_prompt(agent_input)},
                    {
                        "role": "user",
                        "content": build_turn_prompt(agent_input, repair=True),
                    },
                ]
            )
            try:
                return validate_agent_output(
                    repair_raw,
                    available_tools=agent_input.available_tools,
                    speculative=agent_input.speculative,
                )
            except AgentOutputValidationError:
                return technical_recovery_output()
