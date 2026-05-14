"""
Tests for the ResumeSessionManager service.

Tests session creation, event emission, subscription, and cleanup functionality.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, UTC

import pytest

from app.services.resume_session_manager import (
    ProgressEvent,
    ProcessingSession,
    ResumeSessionManager,
)


@pytest.fixture
def session_manager():
    """Provide a fresh ResumeSessionManager instance for each test."""
    # Create a new instance with short TTL for testing
    manager = ResumeSessionManager(session_ttl_seconds=2)
    yield manager
    # Cleanup: cancel any running tasks
    if manager._cleanup_task and not manager._cleanup_task.done():
        manager._cleanup_task.cancel()
    for task in manager._keepalive_tasks.values():
        if not task.done():
            task.cancel()


@pytest.fixture
def sample_job_id():
    """Provide a sample job UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_user_id():
    """Provide a sample user UUID."""
    return str(uuid.uuid4())


def test_create_session(session_manager, sample_job_id, sample_user_id):
    """Test creating a new session returns a valid session_id."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=5
    )
    
    # Verify session_id is a valid UUID string
    assert session_id is not None
    assert isinstance(session_id, str)
    uuid.UUID(session_id)  # Should not raise
    
    # Verify session exists
    session = session_manager.get_session(session_id)
    assert session is not None
    assert session.job_id == sample_job_id
    assert session.user_id == sample_user_id
    assert session.total_resumes == 5
    assert session.completed is False
    assert session.active_connections == 0


def test_get_session_not_found(session_manager):
    """Test getting a non-existent session returns None."""
    session = session_manager.get_session("non-existent-id")
    assert session is None


@pytest.mark.asyncio
async def test_emit_progress(session_manager, sample_job_id, sample_user_id):
    """Test emitting a progress event adds it to the session queue."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=3
    )
    
    event = ProgressEvent(
        event_type="starting",
        session_id=session_id,
        resume_index=0,
        total_resumes=3,
        filename="resume1.pdf"
    )
    
    await session_manager.emit_progress(session_id, event)
    
    # Verify event is in queue
    session = session_manager.get_session(session_id)
    assert session.event_queue.qsize() == 1
    
    # Retrieve and verify event
    queued_event = await session.event_queue.get()
    assert queued_event.event_type == "starting"
    assert queued_event.filename == "resume1.pdf"
    assert queued_event.resume_index == 0


@pytest.mark.asyncio
async def test_emit_progress_updates_last_activity(session_manager, sample_job_id, sample_user_id):
    """Test emitting progress updates the session's last_activity timestamp."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    session = session_manager.get_session(session_id)
    original_time = session.last_activity
    
    # Wait a bit to ensure timestamp difference
    await asyncio.sleep(0.1)
    
    event = ProgressEvent(
        event_type="uploading",
        session_id=session_id,
        resume_index=0,
        total_resumes=1,
        filename="test.pdf"
    )
    
    await session_manager.emit_progress(session_id, event)
    
    # Verify last_activity was updated
    assert session.last_activity > original_time


@pytest.mark.asyncio
async def test_subscribe_receives_events(session_manager, sample_job_id, sample_user_id):
    """Test subscribing to a session receives emitted events."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=2
    )
    
    received_events = []
    
    async def emit_events():
        """Emit test events after a short delay."""
        await asyncio.sleep(0.1)
        
        event1 = ProgressEvent(
            event_type="starting",
            session_id=session_id,
            resume_index=0,
            total_resumes=2,
            filename="resume1.pdf"
        )
        await session_manager.emit_progress(session_id, event1)
        
        event2 = ProgressEvent(
            event_type="completed",
            session_id=session_id,
            resume_index=0,
            total_resumes=2,
            filename="resume1.pdf",
            candidate_name="John Doe",
            matching_score=85.5
        )
        await session_manager.emit_progress(session_id, event2)
        
        event3 = ProgressEvent(
            event_type="all_completed",
            session_id=session_id,
            resume_index=1,
            total_resumes=2,
            filename=""
        )
        await session_manager.emit_progress(session_id, event3)
    
    async def subscribe_and_collect():
        """Subscribe and collect events."""
        async for event in session_manager.subscribe(session_id):
            received_events.append(event)
            if event.event_type == "all_completed":
                break
    
    # Run both tasks concurrently
    await asyncio.gather(
        emit_events(),
        subscribe_and_collect()
    )
    
    # Verify received events (excluding keepalive events)
    non_keepalive_events = [e for e in received_events if e.event_type != "keepalive"]
    assert len(non_keepalive_events) == 3
    assert non_keepalive_events[0].event_type == "starting"
    assert non_keepalive_events[1].event_type == "completed"
    assert non_keepalive_events[1].candidate_name == "John Doe"
    assert non_keepalive_events[1].matching_score == 85.5
    assert non_keepalive_events[2].event_type == "all_completed"


@pytest.mark.asyncio
async def test_subscribe_increments_active_connections(session_manager, sample_job_id, sample_user_id):
    """Test subscribing increments the active_connections counter."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    session = session_manager.get_session(session_id)
    assert session.active_connections == 0
    
    # Start subscription in background
    subscription_task = asyncio.create_task(
        consume_subscription(session_manager, session_id)
    )
    
    # Wait for subscription to start
    await asyncio.sleep(0.2)
    
    # Check active connections increased
    assert session.active_connections == 1
    
    # Emit completion event to end subscription
    event = ProgressEvent(
        event_type="all_completed",
        session_id=session_id,
        resume_index=0,
        total_resumes=1,
        filename=""
    )
    await session_manager.emit_progress(session_id, event)
    
    # Wait for subscription to end
    await subscription_task
    
    # Give a moment for cleanup to complete
    await asyncio.sleep(0.1)
    
    # Check active connections decreased
    assert session.active_connections == 0


async def consume_subscription(session_manager, session_id):
    """Helper to consume subscription events."""
    async for event in session_manager.subscribe(session_id):
        if event.event_type == "all_completed":
            break


def test_mark_completed(session_manager, sample_job_id, sample_user_id):
    """Test marking a session as completed."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    session = session_manager.get_session(session_id)
    assert session.completed is False
    
    session_manager.mark_completed(session_id)
    
    assert session.completed is True


@pytest.mark.asyncio
async def test_cleanup_stale_sessions(session_manager, sample_job_id, sample_user_id):
    """Test cleanup removes sessions that exceed TTL."""
    # Create session with short TTL (2 seconds from fixture)
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    # Verify session exists
    assert session_manager.get_session(session_id) is not None
    
    # Manually set last_activity to past (simulate stale session)
    session = session_manager.get_session(session_id)
    session.last_activity = datetime.now(UTC) - timedelta(seconds=10)
    
    # Run cleanup
    await session_manager.cleanup_stale_sessions()
    
    # Verify session was removed
    assert session_manager.get_session(session_id) is None


@pytest.mark.asyncio
async def test_cleanup_completed_sessions_with_no_connections(session_manager, sample_job_id, sample_user_id):
    """Test cleanup removes completed sessions with no active connections."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    # Mark as completed
    session_manager.mark_completed(session_id)
    
    # Verify session exists
    assert session_manager.get_session(session_id) is not None
    
    # Run cleanup
    await session_manager.cleanup_stale_sessions()
    
    # Verify session was removed (completed + no active connections)
    assert session_manager.get_session(session_id) is None


@pytest.mark.asyncio
async def test_cleanup_preserves_active_sessions(session_manager, sample_job_id, sample_user_id):
    """Test cleanup does not remove active sessions."""
    session_id = session_manager.create_session(
        job_id=sample_job_id,
        user_id=sample_user_id,
        total_resumes=1
    )
    
    # Session is recent and not completed
    await session_manager.cleanup_stale_sessions()
    
    # Verify session still exists
    assert session_manager.get_session(session_id) is not None


def test_progress_event_to_dict():
    """Test ProgressEvent.to_dict() serialization."""
    event = ProgressEvent(
        event_type="completed",
        session_id="test-session",
        resume_index=0,
        total_resumes=1,
        filename="resume.pdf",
        candidate_name="Jane Smith",
        email="jane@example.com",
        phone_number="+1234567890",
        matching_score=92.3,
        resume_id="resume-uuid"
    )
    
    data = event.to_dict()
    
    assert data["event_type"] == "completed"
    assert data["session_id"] == "test-session"
    assert data["resume_index"] == 0
    assert data["total_resumes"] == 1
    assert data["filename"] == "resume.pdf"
    assert data["candidate_name"] == "Jane Smith"
    assert data["email"] == "jane@example.com"
    assert data["phone_number"] == "+1234567890"
    assert data["matching_score"] == 92.3
    assert data["resume_id"] == "resume-uuid"
    assert "timestamp" in data


def test_progress_event_to_dict_minimal():
    """Test ProgressEvent.to_dict() with minimal fields."""
    event = ProgressEvent(
        event_type="starting",
        session_id="test-session",
        resume_index=0,
        total_resumes=5,
        filename="test.pdf"
    )
    
    data = event.to_dict()
    
    assert data["event_type"] == "starting"
    assert data["filename"] == "test.pdf"
    assert "candidate_name" not in data
    assert "error_message" not in data


def test_progress_event_to_dict_error():
    """Test ProgressEvent.to_dict() with error fields."""
    event = ProgressEvent(
        event_type="error",
        session_id="test-session",
        resume_index=2,
        total_resumes=5,
        filename="bad_resume.pdf",
        error_message="Failed to parse PDF",
        failed_stage="parsing"
    )
    
    data = event.to_dict()
    
    assert data["event_type"] == "error"
    assert data["error_message"] == "Failed to parse PDF"
    assert data["failed_stage"] == "parsing"


def test_singleton_instance():
    """Test get_session_manager returns singleton instance."""
    from app.services.resume_session_manager import get_session_manager
    
    manager1 = get_session_manager()
    manager2 = get_session_manager()
    
    assert manager1 is manager2
