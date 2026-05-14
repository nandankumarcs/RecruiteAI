"""
Resume Progress Emitter for emitting progress events during resume processing.

This module provides convenience methods for emitting different types of
progress events during resume processing stages.
"""

from typing import Optional
from datetime import datetime
import logging

from app.services.resume_session_manager import (
    ResumeSessionManager,
    ProgressEvent
)

logger = logging.getLogger(__name__)


class ResumeProgressEmitter:
    """Helper class to emit progress events during resume processing."""
    
    def __init__(self, session_manager: ResumeSessionManager):
        """
        Initialize the progress emitter.
        
        Args:
            session_manager: ResumeSessionManager instance for event emission
        """
        self._session_manager = session_manager
    
    async def emit_starting(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str
    ) -> None:
        """
        Emit 'starting' event when resume processing begins.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
        """
        event = ProgressEvent(
            event_type="starting",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.info(f"Starting processing: {filename} ({resume_index + 1}/{total_resumes})")
    
    async def emit_uploading(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str
    ) -> None:
        """
        Emit 'uploading' event when file upload begins.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
        """
        event = ProgressEvent(
            event_type="uploading",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.debug(f"Uploading: {filename}")
    
    async def emit_parsing(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str
    ) -> None:
        """
        Emit 'parsing' event when resume parsing begins.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
        """
        event = ProgressEvent(
            event_type="parsing",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.debug(f"Parsing: {filename}")
    
    async def emit_evaluating(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str
    ) -> None:
        """
        Emit 'evaluating' event when evaluation against job description begins.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
        """
        event = ProgressEvent(
            event_type="evaluating",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.debug(f"Evaluating: {filename}")
    
    async def emit_completed(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str,
        candidate_name: Optional[str] = None,
        email: Optional[str] = None,
        phone_number: Optional[str] = None,
        matching_score: Optional[float] = None
    ) -> None:
        """
        Emit 'completed' event when resume processing completes successfully.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
            candidate_name: Name of the candidate (optional)
            email: Email address of the candidate (optional)
            phone_number: Phone number of the candidate (optional)
            matching_score: Matching score against job description (optional)
        """
        event = ProgressEvent(
            event_type="completed",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            candidate_name=candidate_name,
            email=email,
            phone_number=phone_number,
            matching_score=matching_score,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.info(
            f"Completed: {filename} - {candidate_name or 'Unknown'} "
            f"(score: {matching_score if matching_score is not None else 'N/A'})"
        )
    
    async def emit_error(
        self, 
        session_id: str, 
        resume_index: int, 
        total_resumes: int, 
        filename: str,
        error_message: str,
        failed_stage: str
    ) -> None:
        """
        Emit 'error' event when resume processing fails.
        
        Args:
            session_id: Session identifier
            resume_index: Index of current resume (0-based)
            total_resumes: Total number of resumes in session
            filename: Name of the resume file
            error_message: Description of the error
            failed_stage: Stage at which processing failed
        """
        event = ProgressEvent(
            event_type="error",
            session_id=session_id,
            resume_index=resume_index,
            total_resumes=total_resumes,
            filename=filename,
            error_message=error_message,
            failed_stage=failed_stage,
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.error(
            f"Error processing {filename} at stage '{failed_stage}': {error_message}"
        )
    
    async def emit_all_completed(
        self, 
        session_id: str, 
        total_resumes: int
    ) -> None:
        """
        Emit 'all_completed' event when all resumes in the session are processed.
        
        This event signals the end of the processing session and will close
        the SSE stream.
        
        Args:
            session_id: Session identifier
            total_resumes: Total number of resumes that were processed
        """
        event = ProgressEvent(
            event_type="all_completed",
            session_id=session_id,
            resume_index=total_resumes - 1,  # Last resume index
            total_resumes=total_resumes,
            filename="",  # No specific filename for session completion
            timestamp=datetime.utcnow()
        )
        await self._session_manager.emit_progress(session_id, event)
        logger.info(f"All resumes completed for session {session_id} ({total_resumes} total)")
