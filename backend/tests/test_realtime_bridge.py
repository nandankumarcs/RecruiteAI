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

    assert "Warm, professional recruiter" in instructions
    assert "No consent = No interview questions." in instructions
    assert "Tell me about your RAG experience." in instructions
    assert "Ask for consent to continue the screening." in instructions


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

    assert "Consent granted. Ask exactly ONE interview question" in consented
    assert "Candidate declined/ended. Say thank you and goodbye." in ending


def test_realtime_bridge_detects_end_of_call_script():
    assert RealtimeBridge._should_end_call(
        "Thank you for your time today. We'll be in touch soon. Goodbye and have a great day."
    )
    assert not RealtimeBridge._should_end_call(
        "Could you tell me more about your experience with FastAPI?"
    )


def test_clean_assistant_spoken_text_removes_role_prefixes():
    assert (
        RealtimeBridge._clean_assistant_spoken_text(
            "Assistant: Recruiter: Could you tell me about your Python experience?"
        )
        == "Could you tell me about your Python experience?"
    )
    assert (
        RealtimeBridge._clean_assistant_spoken_text("RecruiteAI assistant: Hello there.")
        == "Hello there."
    )


def test_compress_assistant_spoken_text_shortens_common_recruiter_question():
    assert (
        RealtimeBridge._compress_assistant_spoken_text(
            "Great! Can you briefly introduce yourself and explain why you are interested in this Junior Software Engineer position?"
        )
        == "Tell me about yourself and why this role interests you."
    )
    assert (
        RealtimeBridge._compress_assistant_spoken_text(
            "It seems like you might need clarification. Can you briefly introduce yourself and explain why you are interested in this Junior Software Engineer position?"
        )
        == "I'm here. Tell me about yourself and why this role interests you."
    )


def test_initial_consent_prompt_is_deterministic():
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
        candidate_name="Sarthak Sharma",
        phone_number="+91-1111111111",
        email="sarthak@example.com",
        file_path="/tmp/resume.pdf",
        file_type="pdf",
    )

    prompt = bridge._build_initial_consent_prompt(resume=resume, job=job)

    assert prompt == (
        "Hi Sarthak, this is RecruiteAI calling about your application. "
        "Is now a good time for a short screening?"
    )


def test_candidate_turn_fast_analysis_skips_obvious_llm_classification():
    consent = RealtimeBridge._analyze_candidate_turn_fast(
        "Yes, please continue.",
        ConversationState(consent_prompt_delivered=True),
    )
    termination = RealtimeBridge._analyze_candidate_turn_fast(
        "I am not interested, please disconnect.",
        ConversationState(consent_prompt_delivered=True),
    )
    clarification = RealtimeBridge._analyze_candidate_turn_fast(
        "Can you repeat the question?",
        ConversationState(consent_granted=True),
    )
    needs_llm = RealtimeBridge._analyze_candidate_turn_fast(
        "I worked on a FastAPI service for two years.",
        ConversationState(consent_granted=True),
    )

    assert consent and consent.grant_consent is True
    assert termination and termination.request_termination is True
    assert clarification
    assert clarification.grant_consent is False
    assert clarification.request_termination is False
    assert clarification.off_topic_request is False
    assert needs_llm is None


@pytest.mark.asyncio
async def test_candidate_turn_analysis_uses_contextual_classification():
    class FakeCreate:
        def __init__(self, payload: str):
            self.payload = payload

        async def create(self, **kwargs):
            message = type("Message", (), {"content": self.payload})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    class FakeChat:
        def __init__(self, payload: str):
            self.completions = FakeCreate(payload)

    class FakeClient:
        def __init__(self, payload: str):
            self.chat = FakeChat(payload)

    bridge = RealtimeBridge()
    bridge._analysis_client = FakeClient(
        '{"grant_consent": true, "request_termination": false, "off_topic_request": false}'
    )

    analysis = await bridge._analyze_candidate_turn(
        transcript="Yes, that works for me.",
        state=ConversationState(consent_prompt_delivered=True),
    )

    assert analysis.grant_consent is True
    assert analysis.request_termination is False
    assert analysis.off_topic_request is False
    assert RealtimeBridge._is_consent_prompt(
        "Hello, this is a recruiter screening call for the role. Is now a good time, and do you consent to continue?"
    )


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


@pytest.mark.asyncio
async def test_update_call_finished_preserves_existing_terminal_status(db_session, test_user):
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
        twilio_call_sid="CA_REALTIME_TEST_3",
        status="failed",
        phone_number=resume.phone_number,
    )
    db_session.add(call)
    await db_session.commit()

    await bridge._update_call_finished(call.id)

    await db_session.refresh(call)
    assert call.status == "failed"
    assert call.ended_at is not None
