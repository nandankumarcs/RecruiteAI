"""Phase 6 tests for call v2 agent contracts."""

import pytest

from app.call_v2.agent.config import (
    AgentConfig,
    AgentInput,
    AgentVisibleCallState,
    CallScope,
    ConversationMessage,
    ResponseStyle,
)
from app.call_v2.agent.fake import FakeAgentRunner
from app.call_v2.agent.fingerprint import agent_input_fingerprint
from app.call_v2.agent.output import (
    AgentOutput,
    AgentOutputValidationError,
    validate_agent_output,
)
from app.call_v2.agent.prompts import build_system_prompt, build_turn_prompt
from app.call_v2.agent.runner import StructuredModelAgentRunner
from app.call_v2.agent.tools import ToolArgumentSpec, ToolSpec


def _agent_input(
    *,
    speculative: bool = False,
    latest_text: str = "Yes, we can continue.",
    tools: list[ToolSpec] | None = None,
) -> AgentInput:
    config = AgentConfig(
        agent_name="Recruiting Call Agent",
        instructions=(
            "Conduct a concise screening call. Ask one thing at a time and "
            "handle clarification naturally."
        ),
        scope=CallScope(
            purpose="Screen a candidate for a backend engineer role.",
            allowed_topics=[
                "role fit",
                "technical experience",
                "candidate questions about the screening",
            ],
            disallowed_topics=["medical advice", "legal advice"],
            compliance_notes=["Ask for consent before the screening conversation."],
            success_criteria=["Collect enough signal for post-call evaluation."],
        ),
        context={
            "candidate": {"name": "Asha", "skills": ["Python", "FastAPI"]},
            "job": {"title": "Backend Engineer"},
            "questions": [
                {
                    "id": "q1",
                    "text": "Tell me about a backend project you owned.",
                    "priority": 1,
                }
            ],
        },
        objectives=[
            "Confirm consent to continue.",
            "Ask screening questions naturally.",
            "Clarify or explain questions when the candidate asks.",
        ],
        constraints=[
            "Do not ask interview questions before consent.",
            "Do not provide hiring decisions.",
        ],
        response_style=ResponseStyle(tone="warm and professional"),
    )
    latest = ConversationMessage(
        role="user",
        content=latest_text,
        message_id="m-user-1",
        generation_id=1,
        committed=not speculative,
        interrupted=False,
        created_at_ms=1000,
    )
    return AgentInput(
        call_id="call-1",
        generation_id=1,
        speculative=speculative,
        agent_config=config,
        call_state=AgentVisibleCallState(
            phase="screening",
            consent_status="unknown",
            open_items=["q1"],
            elapsed_call_seconds=12,
        ),
        conversation=[
            ConversationMessage(
                role="assistant",
                content="Hi, may I continue with this screening call?",
                message_id="m-assistant-1",
                generation_id=None,
                committed=True,
                interrupted=False,
                created_at_ms=500,
            )
        ],
        latest_user_turn=latest,
        available_tools=tools or [],
    )


def _signal_tool() -> ToolSpec:
    return ToolSpec(
        name="record_screening_signal",
        description="Record a non-critical screening signal.",
        arguments=[
            ToolArgumentSpec(name="question_id", kind="string"),
            ToolArgumentSpec(name="signal", kind="string"),
            ToolArgumentSpec(name="score", kind="number", required=False),
        ],
    )


@pytest.mark.parametrize(
    ("case_name", "raw_output"),
    [
        (
            "consent",
            {
                "spoken_text": "Thanks. May I ask you a few role-related questions?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {"consent_status": "requested"},
                "confidence": 0.9,
            },
        ),
        (
            "refusal",
            {
                "spoken_text": "No problem. Thank you for your time.",
                "action": "end_call_after_speaking",
                "tool_calls": [],
                "state_updates": {"consent_status": "refused"},
            },
        ),
        (
            "repeat",
            {
                "spoken_text": "Sure. I asked about a backend project you owned.",
                "action": "pause_for_user",
                "tool_calls": [],
                "state_updates": {},
            },
        ),
        (
            "explain_question",
            {
                "spoken_text": (
                    "I mean a project where you were responsible for design, "
                    "implementation, or delivery. What did you own?"
                ),
                "action": "pause_for_user",
                "tool_calls": [],
                "state_updates": {},
            },
        ),
        (
            "short_answer",
            {
                "spoken_text": "Got it. What part of that project was most challenging?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {},
            },
        ),
        (
            "long_answer",
            {
                "spoken_text": "Thanks, that gives useful context. What was the outcome?",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {"covered_items": ["q1"]},
            },
        ),
        (
            "off_scope",
            {
                "spoken_text": (
                    "I cannot advise on that, but I can answer questions about "
                    "this screening call."
                ),
                "action": "pause_for_user",
                "tool_calls": [],
                "state_updates": {},
            },
        ),
        (
            "terminal",
            {
                "spoken_text": "Thanks for speaking with me. We will follow up soon.",
                "action": "end_call_after_speaking",
                "tool_calls": [],
                "state_updates": {"call_complete": True},
            },
        ),
    ],
)
def test_agent_output_accepts_required_conversation_cases(case_name, raw_output):
    output = validate_agent_output(
        raw_output,
        available_tools=[],
        speculative=False,
    )

    assert isinstance(output, AgentOutput)
    assert output.spoken_text
    assert output.action in {
        "continue",
        "pause_for_user",
        "end_call_after_speaking",
        "technical_recovery",
    }


def test_prompt_builder_separates_static_config_and_dynamic_turn():
    agent_input = _agent_input(tools=[_signal_tool()])

    system_prompt = build_system_prompt(agent_input)
    turn_prompt = build_turn_prompt(agent_input)

    assert "Recruiting Call Agent" in system_prompt
    assert "Tell me about a backend project you owned." in system_prompt
    assert "record_screening_signal" in system_prompt
    assert '"latest_user_turn"' in turn_prompt
    assert "Yes, we can continue." in turn_prompt
    assert "stream_id" not in turn_prompt


def test_valid_tool_call_is_accepted_when_not_speculative():
    output = validate_agent_output(
        {
            "spoken_text": "Thanks, I noted that.",
            "action": "continue",
            "tool_calls": [
                {
                    "tool_name": "record_screening_signal",
                    "arguments": {
                        "question_id": "q1",
                        "signal": "owned API design",
                        "score": 0.8,
                    },
                    "call_id": "tool-call-1",
                }
            ],
            "state_updates": {},
        },
        available_tools=[_signal_tool()],
        speculative=False,
    )

    assert output.tool_calls[0].tool_name == "record_screening_signal"


def test_agent_input_fingerprint_changes_for_stale_result_inputs():
    base = _agent_input(tools=[_signal_tool()])
    changed_text = _agent_input(
        latest_text="No, I cannot continue.",
        tools=[_signal_tool()],
    )
    original_generation = _agent_input(tools=[_signal_tool()])
    changed_generation = AgentInput(
        call_id=original_generation.call_id,
        generation_id=2,
        speculative=original_generation.speculative,
        agent_config=original_generation.agent_config,
        call_state=original_generation.call_state,
        conversation=original_generation.conversation,
        latest_user_turn=original_generation.latest_user_turn,
        available_tools=original_generation.available_tools,
    )

    assert agent_input_fingerprint(base) == agent_input_fingerprint(base)
    assert agent_input_fingerprint(base) != agent_input_fingerprint(changed_text)
    assert agent_input_fingerprint(base) != agent_input_fingerprint(changed_generation)


@pytest.mark.parametrize(
    "raw_output",
    [
        {"action": "continue", "tool_calls": [], "state_updates": {}},
        {
            "spoken_text": "Hello",
            "action": "unknown",
            "tool_calls": [],
            "state_updates": {},
        },
        {
            "spoken_text": "Assistant: Hello",
            "action": "continue",
            "tool_calls": [],
            "state_updates": {},
        },
        {
            "spoken_text": '{"message": "hello"}',
            "action": "continue",
            "tool_calls": [],
            "state_updates": {},
        },
        {
            "spoken_text": "Hello",
            "action": "continue",
            "tool_calls": [],
            "state_updates": {},
            "confidence": True,
        },
    ],
)
def test_invalid_agent_outputs_are_rejected(raw_output):
    with pytest.raises(AgentOutputValidationError):
        validate_agent_output(
            raw_output,
            available_tools=[],
            speculative=False,
        )


def test_invalid_tool_arguments_are_rejected():
    with pytest.raises(AgentOutputValidationError, match="must be number"):
        validate_agent_output(
            {
                "spoken_text": "Thanks, I noted that.",
                "action": "continue",
                "tool_calls": [
                    {
                        "tool_name": "record_screening_signal",
                        "arguments": {
                            "question_id": "q1",
                            "signal": "owned API design",
                            "score": "high",
                        },
                        "call_id": "tool-call-1",
                    }
                ],
                "state_updates": {},
            },
            available_tools=[_signal_tool()],
            speculative=False,
        )


def test_speculative_tool_calls_are_blocked():
    with pytest.raises(AgentOutputValidationError, match="speculative"):
        validate_agent_output(
            {
                "spoken_text": "Thanks, I noted that.",
                "action": "continue",
                "tool_calls": [
                    {
                        "tool_name": "record_screening_signal",
                        "arguments": {"question_id": "q1", "signal": "owned API"},
                        "call_id": "tool-call-1",
                    }
                ],
                "state_updates": {},
            },
            available_tools=[_signal_tool()],
            speculative=True,
        )


@pytest.mark.asyncio
async def test_fake_agent_runner_records_input_and_validates_output():
    runner = FakeAgentRunner(
        outputs=[
            {
                "spoken_text": "Thanks. Tell me about a backend project you owned.",
                "action": "continue",
                "tool_calls": [],
                "state_updates": {"consent_status": "granted"},
            }
        ]
    )
    agent_input = _agent_input()

    output = await runner.run(agent_input)

    assert output.action == "continue"
    assert runner.calls == [agent_input]


class _FakeStructuredModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.messages = []

    async def ainvoke(self, messages):
        self.messages.append(messages)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_structured_model_runner_repairs_invalid_output_once():
    model = _FakeStructuredModel(
        [
            {"action": "continue"},
            {
                "spoken_text": "Thanks. Please continue.",
                "action": "pause_for_user",
                "tool_calls": [],
                "state_updates": {},
            },
        ]
    )
    runner = StructuredModelAgentRunner(model=model)

    output = await runner.run(_agent_input())

    assert output.spoken_text == "Thanks. Please continue."
    assert len(model.messages) == 2
    assert "previous response did not satisfy" in model.messages[1][1]["content"]


@pytest.mark.asyncio
async def test_structured_model_runner_falls_back_after_second_invalid_output():
    model = _FakeStructuredModel(
        [
            {"action": "continue"},
            {"spoken_text": "Assistant: bad", "action": "continue"},
        ]
    )
    runner = StructuredModelAgentRunner(model=model)

    output = await runner.run(_agent_input())

    assert output.action == "end_call_after_speaking"
    assert output.state_updates["technical_recovery"] is True
