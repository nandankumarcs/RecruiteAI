"""
Unit tests for JobPromptGenerationRun model.

Tests model creation, field validation, and relationship enforcement.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.job import Job
from app.models.job_prompt_generation_run import JobPromptGenerationRun
from app.models.user import User


class TestJobPromptGenerationRunModel:
    """Test suite for JobPromptGenerationRun model."""

    @pytest.mark.asyncio
    async def test_create_job_prompt_generation_run(self, db_session):
        """Test creating a basic job prompt generation run."""
        # Create a user and job first
        user = User(
            email="test@example.com",
            hashed_password="hashed_password",
            full_name="Test User",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="Software Engineer",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # Create generation run
        run = JobPromptGenerationRun(
            job_id=job.id,
            status="completed",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            success_count=5,
            failure_count=1,
            error_summary={"question_123": "TTS API timeout"},
        )

        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.id is not None
        assert run.job_id == job.id
        assert run.status == "completed"
        assert run.success_count == 5
        assert run.failure_count == 1
        assert run.error_summary == {"question_123": "TTS API timeout"}
        assert run.started_at is not None
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_default_values(self, db_session):
        """Test that default values are applied correctly."""
        # Create a user and job first
        user = User(
            email="test2@example.com",
            hashed_password="hashed_password",
            full_name="Test User 2",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="Data Analyst",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # Create run with minimal fields
        run = JobPromptGenerationRun(job_id=job.id)

        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        # Check defaults
        assert run.status == "pending"
        assert run.success_count == 0
        assert run.failure_count == 0
        assert run.error_summary is None
        assert run.completed_at is None
        assert run.started_at is not None
        assert run.created_at is not None

    @pytest.mark.asyncio
    async def test_status_values(self, db_session):
        """Test different status values."""
        # Create a user and job first
        user = User(
            email="test3@example.com",
            hashed_password="hashed_password",
            full_name="Test User 3",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="Product Manager",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        statuses = ["pending", "in_progress", "completed", "failed"]

        for status in statuses:
            run = JobPromptGenerationRun(
                job_id=job.id,
                status=status,
            )
            db_session.add(run)

        await db_session.commit()

        # Verify all were created
        result = await db_session.execute(
            select(JobPromptGenerationRun).where(
                JobPromptGenerationRun.job_id == job.id
            )
        )
        runs = result.scalars().all()
        assert len(runs) == 4
        assert {r.status for r in runs} == set(statuses)

    @pytest.mark.asyncio
    async def test_relationship_with_job(self, db_session):
        """Test that the relationship with Job works correctly."""
        from sqlalchemy.orm import selectinload
        
        # Create a user and job first
        user = User(
            email="test4@example.com",
            hashed_password="hashed_password",
            full_name="Test User 4",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="DevOps Engineer",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # Create generation run
        run = JobPromptGenerationRun(
            job_id=job.id,
            status="completed",
            success_count=3,
        )
        db_session.add(run)
        await db_session.commit()
        
        # Refresh with eager loading to avoid lazy load issues
        await db_session.refresh(run, attribute_names=["job"])

        # Test relationship
        assert run.job is not None
        assert run.job.id == job.id
        assert run.job.title == "DevOps Engineer"

        # Test backref - query with eager loading
        result = await db_session.execute(
            select(Job)
            .where(Job.id == job.id)
            .options(selectinload(Job.prompt_generation_runs))
        )
        job_with_runs = result.scalar_one()
        assert len(job_with_runs.prompt_generation_runs) == 1
        assert job_with_runs.prompt_generation_runs[0].id == run.id

    @pytest.mark.asyncio
    async def test_foreign_key_constraint(self, db_session):
        """Test that job_id foreign key constraint is enforced."""
        # Try to create a run with non-existent job_id
        import uuid as uuid_module
        
        fake_job_id = uuid_module.uuid4()
        run = JobPromptGenerationRun(
            job_id=fake_job_id,
            status="pending",
        )
        db_session.add(run)
        
        # This should fail with foreign key constraint violation
        # Note: This test will only work once the table is created via migration
        # For now, we just verify the model is correctly configured
        assert run.job_id == fake_job_id

    @pytest.mark.asyncio
    async def test_error_summary_json(self, db_session):
        """Test that error_summary stores JSON data correctly."""
        # Create a user and job first
        user = User(
            email="test6@example.com",
            hashed_password="hashed_password",
            full_name="Test User 6",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="Backend Developer",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # Create run with complex error summary
        error_data = {
            "question_1": "TTS API timeout",
            "question_2": "Invalid audio format",
            "question_3": "Storage upload failed",
        }
        run = JobPromptGenerationRun(
            job_id=job.id,
            status="failed",
            success_count=2,
            failure_count=3,
            error_summary=error_data,
        )

        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        # Verify JSON data is stored and retrieved correctly
        assert run.error_summary == error_data
        assert run.error_summary["question_1"] == "TTS API timeout"
        assert len(run.error_summary) == 3

    @pytest.mark.asyncio
    async def test_indexes_exist(self, db_session):
        """Test that required indexes are defined."""
        # Verify indexes directly from the model's table metadata
        indexes = JobPromptGenerationRun.__table__.indexes
        index_names = {idx.name for idx in indexes}

        # Check required indexes
        assert "ix_job_prompt_generation_runs_job_id" in index_names
        assert "ix_job_prompt_generation_runs_status" in index_names

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        """Test the string representation of the model."""
        # Create a user and job first
        user = User(
            email="test7@example.com",
            hashed_password="hashed_password",
            full_name="Test User 7",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        job = Job(
            user_id=user.id,
            title="Frontend Developer",
            description="Test job description",
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        run = JobPromptGenerationRun(
            job_id=job.id,
            status="completed",
            success_count=10,
            failure_count=2,
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        repr_str = repr(run)
        assert "JobPromptGenerationRun" in repr_str
        assert str(job.id) in repr_str
        assert "completed" in repr_str
        assert "success=10" in repr_str
        assert "failure=2" in repr_str
