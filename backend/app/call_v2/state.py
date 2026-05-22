"""Explicit state machine for the call v2 runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class CallRuntimeState(StrEnum):
    INITIALIZING = "initializing"
    WAITING_FOR_STREAM = "waiting_for_stream"
    LISTENING = "listening"
    SPECULATING = "speculating"
    AGENT_RUNNING = "agent_running"
    SPEAKING = "speaking"
    POST_TTS_GUARD = "post_tts_guard"
    RECOVERING = "recovering"
    ENDING = "ending"
    ENDED = "ended"


class InvalidStateTransition(ValueError):
    """Raised when a runtime transition violates the v2 state machine."""


ALLOWED_TRANSITIONS: dict[CallRuntimeState, set[CallRuntimeState]] = {
    CallRuntimeState.INITIALIZING: {
        CallRuntimeState.WAITING_FOR_STREAM,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.WAITING_FOR_STREAM: {
        CallRuntimeState.LISTENING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.LISTENING: {
        CallRuntimeState.SPECULATING,
        CallRuntimeState.AGENT_RUNNING,
        CallRuntimeState.SPEAKING,
        CallRuntimeState.RECOVERING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.SPECULATING: {
        CallRuntimeState.LISTENING,
        CallRuntimeState.AGENT_RUNNING,
        CallRuntimeState.SPEAKING,
        CallRuntimeState.RECOVERING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.AGENT_RUNNING: {
        CallRuntimeState.SPEAKING,
        CallRuntimeState.RECOVERING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.SPEAKING: {
        CallRuntimeState.POST_TTS_GUARD,
        CallRuntimeState.LISTENING,
        CallRuntimeState.RECOVERING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.POST_TTS_GUARD: {
        CallRuntimeState.LISTENING,
        CallRuntimeState.SPECULATING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.RECOVERING: {
        CallRuntimeState.SPEAKING,
        CallRuntimeState.LISTENING,
        CallRuntimeState.ENDING,
    },
    CallRuntimeState.ENDING: {CallRuntimeState.ENDED},
    CallRuntimeState.ENDED: set(),
}


@dataclass(slots=True)
class StateTransition:
    previous_state: CallRuntimeState
    next_state: CallRuntimeState
    reason: str


@dataclass(slots=True)
class CallStateMachine:
    state: CallRuntimeState = CallRuntimeState.INITIALIZING
    history: list[StateTransition] = field(default_factory=list)

    def can_transition_to(self, next_state: CallRuntimeState) -> bool:
        return next_state in ALLOWED_TRANSITIONS[self.state]

    def transition_to(
        self,
        next_state: CallRuntimeState,
        *,
        reason: str,
    ) -> StateTransition:
        if not self.can_transition_to(next_state):
            raise InvalidStateTransition(
                f"cannot transition from {self.state.value} to {next_state.value}"
            )
        transition = StateTransition(
            previous_state=self.state,
            next_state=next_state,
            reason=reason,
        )
        self.state = next_state
        self.history.append(transition)
        return transition
