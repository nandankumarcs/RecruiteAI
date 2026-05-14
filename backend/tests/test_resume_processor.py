"""
Tests for Resume Processor Service
"""

import uuid
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_parser_agent import ResumeParserAgent
from app.services.resume_processor import ResumeProcessor
from app.services.resume_session_manager import ResumeSessionManager
from app.services.storage import StorageProvider


class MockStorageProvider(StorageProvider):
    """Mock storage provider for testing."""
    
    async def save_file(self, file: UploadFile, destination_path: str) -> str:
        return f"/mock/storage/{destination_path}"
    
    async def delete_file(self, file_path: str) -> bool:
        return True
    
    async def get_file_content(self, file_path: str) -> bytes:
        return b"mock content"


class MockResumeParser(ResumeParserAgent):
    """Mock resume parser for testing."""
    
    def __init__(self):
        super().__init__(enable_llm=False)
    
    async def parse_resume(self, file_path: str, file_type: str) -> dict:
        return {
            "candidate_name": "Test Candidate",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "raw_text": "Test resume content",
            "parsed_data": {
                "schema_version": "resume.v2",
                "summary": "Test summary",
                "skills": ["Python", "FastAPI"],
                "skill_categories": [],
                "experience": [],
                "projects": [],
                "education": [],
                "certifications": [],
                "links": []
            }
        }


@pytest.fixture
def session_manager():
    """Create a session manager instance."""
    return ResumeSessionManager(session_ttl_seconds=3600)


@pytest.fixture
def storage_provider():
    """Create a mock storage provider."""
    return MockStorageProvider()


@pytest.fixture
def resume_parser():
    """Create a mock resume parser."""
    return MockResumeParser()


@pytest.fixture
def resume_processor(session_manager, storage_provider, resume_parser):
    """Create a resume processor instance."""
    return ResumeProcessor(session_manager, storage_provider, resume_parser)


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_upload_file():
    """Create a mock upload file."""
    file_content = b"Mock PDF content"
    file = UploadFile(
        filename="test_resume.pdf",
        file=BytesIO(file_content)
    )
    return file


@pytest.mark.asyncio
async def test_process_resumes_emits_all_stages(
    resume_processor,
    session_manager,
    mock_db_session,
    mock_upload_file
):
    """Test that process_resumes emits all expected progress events."""
    job_id = uuid.uuid4()
    session_id = session_manager.create_session(
        job_id=str(job_id),
        user_id=str(uuid.uuid4()),
        total_resumes=1
    )
    
    # Collect emitted events
    emitted_events = []
    
    # Subscribe to events
    async def collect_events():
        async for event in session_manager.subscribe(session_id):
            emitted_events.append(event.event_type)
            if event.event_type == "all_completed":
                break
    
    # Start collecting events in background
    import asyncio
    collect_task = asyncio.create_task(collect_events())
    
    # Process resumes
    await resume_processor.process_resumes(
        session_id=session_id,
        job_id=job_id,
        files=[mock_upload_file],
        job_description=None,
        db=mock_db_session
    )
    
    # Wait for event collection to complete
    await collect_task
    
    # Verify all stages were emitted
    expected_stages = ["starting", "uploading", "parsing", "completed", "all_completed"]
    assert emitted_events == expected_stages


@pytest.mark.asyncio
async def test_process_resumes_handles_errors_gracefully(
    resume_processor,
    session_manager,
    mock_db_session
):
    """Test that process_resumes continues after individual resume failures."""
    job_id = uuid.uuid4()
    session_id = session_manager.create_session(
        job_id=str(job_id),
        user_id=str(uuid.uuid4()),
        total_resumes=2
    )
    
    # Create two files - one will fail
    file1 = UploadFile(filename="good.pdf", file=BytesIO(b"content"))
    file2 = UploadFile(filename="bad.pdf", file=BytesIO(b"content"))
    
    # Mock storage to fail on second file
    call_count = 0
    original_save = resume_processor._storage.save_file
    
    async def failing_save(file, dest):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("Storage error")
        return await original_save(file, dest)
    
    resume_processor._storage.save_file = failing_save
    
    # Collect events
    emitted_events = []
    
    async def collect_events():
        async for event in session_manager.subscribe(session_id):
            emitted_events.append(event.event_type)
            if event.event_type == "all_completed":
                break
    
    import asyncio
    collect_task = asyncio.create_task(collect_events())
    
    # Process resumes
    await resume_processor.process_resumes(
        session_id=session_id,
        job_id=job_id,
        files=[file1, file2],
        job_description=None,
        db=mock_db_session
    )
    
    await collect_task
    
    # Verify first resume completed and second errored
    assert "completed" in emitted_events
    assert "error" in emitted_events
    assert "all_completed" in emitted_events


@pytest.mark.asyncio
async def test_process_resumes_with_evaluation(
    resume_processor,
    session_manager,
    mock_db_session,
    mock_upload_file
):
    """Test that process_resumes includes evaluation when job description is provided."""
    job_id = uuid.uuid4()
    session_id = session_manager.create_session(
        job_id=str(job_id),
        user_id=str(uuid.uuid4()),
        total_resumes=1
    )
    
    # Mock evaluation LLM
    mock_evaluation_result = {
        "parsed": MagicMock(
            matching_score=85.0,
            explanation="Good match for the position"
        )
    }
    resume_processor._evaluation_llm = AsyncMock()
    resume_processor._evaluation_llm.ainvoke = AsyncMock(return_value=mock_evaluation_result)
    
    # Collect events
    emitted_events = []
    
    async def collect_events():
        async for event in session_manager.subscribe(session_id):
            emitted_events.append(event.event_type)
            if event.event_type == "all_completed":
                break
    
    import asyncio
    collect_task = asyncio.create_task(collect_events())
    
    # Process with job description
    await resume_processor.process_resumes(
        session_id=session_id,
        job_id=job_id,
        files=[mock_upload_file],
        job_description="Looking for a Python developer",
        db=mock_db_session
    )
    
    await collect_task
    
    # Verify evaluating stage was emitted
    assert "evaluating" in emitted_events
    assert "completed" in emitted_events


@pytest.mark.asyncio
async def test_determine_failed_stage():
    """Test that _determine_failed_stage correctly identifies failure stages."""
    processor = ResumeProcessor(
        ResumeSessionManager(),
        MockStorageProvider(),
        MockResumeParser()
    )
    
    # Test different error types
    assert processor._determine_failed_stage(Exception("upload failed")) == "uploading"
    assert processor._determine_failed_stage(Exception("parse error")) == "parsing"
    assert processor._determine_failed_stage(Exception("evaluation failed")) == "evaluating"
    assert processor._determine_failed_stage(FileNotFoundError("file not found")) == "uploading"
    assert processor._determine_failed_stage(ValueError("invalid value")) == "parsing"
    assert processor._determine_failed_stage(Exception("unknown error")) == "processing"
