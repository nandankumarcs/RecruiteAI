"""Tests for realtime bridge helper behavior."""

from __future__ import annotations

import uuid

import pytest

from app.models.call import Call
from app.models.job import Job
from app.models.question import InterviewQuestion
from app.models.resume import Resume
from app.services.realtime_bridge import ConversationState, RealtimeBridge


def test_realtime_bridge_instructions_include_grounding_rules():
    bridge = RealtimeBridge()
    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="AI Engineer",
        description="Build AI recruiting systems.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    resume = Resume(
        id=uuid.uuid4(),
        job_id=job.id,
        candidate_name="Sarthak",
        phone_number="+91-1111111111",
        email="sarthak@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "RAG engineer", "skills": ["Python", "FastAPI", "FAISS"]},
    )
    questions = [
        InterviewQuestion(
            id=uuid.uuid4(),
            job_id=job.id,
            resume_id=resume.id,
            question_text="Tell me about your RAG experience.",
            category="technical",
            difficulty=3,
            order_index=1,
        )
    ]

    instructions = bridge._build_instructions(
        resume=resume,
        job=job,
        questions=questions,
        state=ConversationState(),
    )

    assert "Never invent candidate experience" in instructions
    assert "Do not answer on the candidate's behalf" in instructions
    assert "Tell me about your RAG experience." in instructions
    assert "Consent has not been granted yet" in instructions


def test_realtime_bridge_instructions_shift_after_consent_and_end_request():
    bridge = RealtimeBridge()
    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        title="AI Engineer",
        description="Build AI recruiting systems.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    resume = Resume(
        id=uuid.uuid4(),
        job_id=job.id,
        candidate_name="Sarthak",
        phone_number="+91-1111111111",
        email="sarthak@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "RAG engineer", "skills": ["Python", "FastAPI", "FAISS"]},
    )

    consented = bridge._build_instructions(
        resume=resume,
        job=job,
        questions=[],
        state=ConversationState(consent_granted=True),
    )
    ending = bridge._build_instructions(
        resume=resume,
        job=job,
        questions=[],
        state=ConversationState(consent_granted=True, termination_requested=True),
    )

    assert "Consent granted. Continue the interview." in consented
    assert "Your only next response should be a brief thank-you and goodbye." in ending


def test_realtime_bridge_detects_end_of_call_script():
    assert RealtimeBridge._should_end_call(
        "Thank you for your time today. We'll be in touch soon. Goodbye and have a great day."
    )
    assert not RealtimeBridge._should_end_call(
        "Could you tell me more about your experience with FastAPI?"
    )


def test_consent_and_off_topic_helpers():
    assert RealtimeBridge._is_affirmative_consent("Yes, go ahead.")
    assert RealtimeBridge._is_negative_or_decline("No thanks, not now.")
    assert RealtimeBridge._is_end_intent("Can you disconnect the call?")
    assert RealtimeBridge._is_clarification_request("What is this again?")
    assert RealtimeBridge._is_off_topic_request("Write a poem for me, please.")


def test_incomplete_assistant_fragment_detection():
    assert RealtimeBridge._looks_like_incomplete_assistant_fragment(
        "I understand. Could you share which"
    )
    assert not RealtimeBridge._looks_like_incomplete_assistant_fragment(
        "Could you tell me why you're interested in this role?"
    )


def test_extract_transcript_text_supports_direct_and_item_content_payloads():
    direct_event = {"transcript": "Candidate answer from direct field"}
    nested_event = {
        "item": {
            "id": "item_123",
            "content": [
                {"type": "input_audio", "transcript": "Candidate answer from nested content"}
            ],
        }
    }

    assert (
        RealtimeBridge._extract_transcript_text(direct_event)
        == "Candidate answer from direct field"
    )
    assert (
        RealtimeBridge._extract_transcript_text(nested_event)
        == "Candidate answer from nested content"
    )
    assert RealtimeBridge._extract_item_id(nested_event) == "item_123"


@pytest.mark.asyncio
async def test_append_message_merges_incremental_transcript_updates(db_session, test_user):
    bridge = RealtimeBridge()
    job = Job(
        user_id=test_user.id,
        title="AI Engineer",
        description="Build AI recruiting systems.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Candidate",
        phone_number="+91-1111111111",
        email="candidate@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "RAG engineer"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_REALTIME_TEST",
        status="in_progress",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    await bridge._append_message(
        call.id, "assistant", "Tell me about", item_key="assistant-item-1"
    )
    await bridge._append_message(
        call.id,
        "assistant",
        "Tell me about your recent project.",
        item_key="assistant-item-1",
    )

    await db_session.refresh(call)
    assert call.transcript == "Assistant: Tell me about your recent project."


@pytest.mark.asyncio
async def test_append_message_keeps_distinct_user_turns_separate(db_session, test_user):
    bridge = RealtimeBridge()
    job = Job(
        user_id=test_user.id,
        title="AI Engineer",
        description="Build AI recruiting systems.",
        requirements="Python, FastAPI, LLMs",
        status="active",
    )
    db_session.add(job)
    await db_session.flush()

    resume = Resume(
        job_id=job.id,
        candidate_name="Candidate",
        phone_number="+91-1111111111",
        email="candidate@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
        raw_text="resume text",
        status="parsed",
        parsed_data={"summary": "RAG engineer"},
    )
    db_session.add(resume)
    await db_session.flush()

    call = Call(
        resume_id=resume.id,
        job_id=job.id,
        twilio_call_sid="CA_REALTIME_TEST_2",
        status="in_progress",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    await bridge._append_message(
        call.id, "user", "My first answer", item_key="user-item-1"
    )
    await bridge._append_message(
        call.id, "user", "My second answer", item_key="user-item-2"
    )

    await db_session.refresh(call)
    assert call.transcript == "User: My first answer\nUser: My second answer"
