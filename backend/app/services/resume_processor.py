"""
Resume Processor Service

Handles sequential resume processing with progress streaming.
Processes resumes one at a time, emitting progress events at each stage.
"""

import logging
import os
import uuid
from typing import List, Optional

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.resume_parser_agent import ResumeParserAgent, CandidateMatch
from app.models.job import Job
from app.models.resume import Resume
from app.services.ai_models import build_structured_chat_model
from app.services.resume_progress_emitter import ResumeProgressEmitter
from app.services.resume_session_manager import ResumeSessionManager
from app.services.storage import StorageProvider

logger = logging.getLogger(__name__)


class ResumeProcessor:
    """Processes resumes sequentially with progress streaming."""
    
    def __init__(
        self,
        session_manager: ResumeSessionManager,
        storage: StorageProvider,
        parser: ResumeParserAgent
    ):
        """
        Initialize the resume processor.
        
        Args:
            session_manager: Session manager for event distribution
            storage: Storage provider for file operations
            parser: Resume parser agent for extracting structured data
        """
        self._session_manager = session_manager
        self._emitter = ResumeProgressEmitter(session_manager)
        self._storage = storage
        self._parser = parser
        self._evaluation_llm = None
        
        # Initialize evaluation LLM if parser has LLM enabled
        if self._parser.enable_llm and hasattr(self._parser, '_ranking_llm'):
            self._evaluation_llm = self._parser._ranking_llm
    
    async def process_resumes(
        self,
        session_id: str,
        job_id: uuid.UUID,
        files: List[UploadFile],
        job_description: Optional[str],
        db: AsyncSession
    ) -> None:
        """
        Process resumes sequentially, emitting progress events.
        This runs as a background task.
        
        Args:
            session_id: Session identifier for progress tracking
            job_id: Job ID to associate resumes with
            files: List of uploaded resume files
            job_description: Job description for evaluation (optional)
            db: Database session
        """
        total_resumes = len(files)
        logger.info(f"Starting resume processing for session {session_id}: {total_resumes} resumes")
        
        for index, file in enumerate(files):
            filename = file.filename or f"resume_{index}"
            
            try:
                # Starting
                await self._emitter.emit_starting(
                    session_id, index, total_resumes, filename
                )
                
                # Uploading
                await self._emitter.emit_uploading(
                    session_id, index, total_resumes, filename
                )
                file_path = await self._upload_file(job_id, file)
                
                # Parsing
                await self._emitter.emit_parsing(
                    session_id, index, total_resumes, filename
                )
                parsed_data = await self._parse_resume(file_path, file)
                
                # Evaluating (if job description is provided)
                evaluation = None
                if job_description and parsed_data.get("raw_text"):
                    await self._emitter.emit_evaluating(
                        session_id, index, total_resumes, filename
                    )
                    evaluation = await self._evaluate_resume(
                        parsed_data["raw_text"], job_description
                    )
                
                # Save to database
                resume = await self._save_resume(
                    db, job_id, file_path, file, parsed_data, evaluation
                )
                
                # Completed
                await self._emitter.emit_completed(
                    session_id, index, total_resumes, filename,
                    candidate_name=resume.candidate_name,
                    email=resume.email,
                    phone_number=resume.phone_number,
                    matching_score=resume.matching_score
                )
                
                logger.info(f"Successfully processed resume {index + 1}/{total_resumes}: {filename}")
                
            except Exception as e:
                # Error - log and emit error event
                logger.error(f"Error processing resume {filename}: {str(e)}", exc_info=True)
                
                failed_stage = self._determine_failed_stage(e)
                await self._emitter.emit_error(
                    session_id, index, total_resumes, filename,
                    error_message=str(e),
                    failed_stage=failed_stage
                )
                
                # Continue processing next resume
                continue
        
        # All completed
        await self._emitter.emit_all_completed(session_id, total_resumes)
        self._session_manager.mark_completed(session_id)
        
        logger.info(f"Completed all resume processing for session {session_id}")
    
    async def _upload_file(self, job_id: uuid.UUID, file: UploadFile) -> str:
        """
        Upload file to storage.
        
        Args:
            job_id: Job ID for organizing files
            file: Uploaded file
            
        Returns:
            File path in storage
        """
        # Generate safe filename
        safe_name = os.path.basename(file.filename or "resume")
        destination = f"resumes/{job_id}/{uuid.uuid4()}-{safe_name}"
        
        # Save file
        file_path = await self._storage.save_file(file, destination)
        
        return file_path
    
    async def _parse_resume(self, file_path: str, file: UploadFile) -> dict:
        """
        Parse resume using ResumeParserAgent.
        
        Args:
            file_path: Path to the resume file
            file: Original uploaded file
            
        Returns:
            Dictionary with parsed data and raw text
        """
        # Determine file type
        file_type = self._get_file_type(file.filename or "")
        
        # Use the parser's async parse_resume method
        # This handles text extraction, structured parsing, and normalization
        parsed_result = await self._parser.parse_resume(file_path, file_type)
        
        return parsed_result
    
    async def _evaluate_resume(self, raw_text: str, job_description: str) -> dict:
        """
        Evaluate resume against job description.
        
        Args:
            raw_text: Raw text of the resume
            job_description: Job description to evaluate against
            
        Returns:
            Dictionary with matching score and explanation
        """
        if not self._evaluation_llm:
            logger.warning("Evaluation LLM not available, skipping evaluation")
            return None
        
        try:
            # Create evaluation prompt
            prompt = (
                f"Evaluate this candidate's resume against the job description. "
                f"Provide a matching score (0-100) and a brief explanation.\n\n"
                f"Job Description:\n{job_description}\n\n"
                f"Resume:\n{raw_text[:8000]}"  # Limit to avoid token limits
            )
            
            # Get evaluation from LLM
            result = await self._evaluation_llm.ainvoke(prompt)
            
            # Extract parsed data
            parsed = result.get("parsed") if isinstance(result, dict) else None
            
            if parsed:
                return {
                    "matching_score": parsed.matching_score,
                    "explanation": parsed.explanation
                }
            
            logger.warning("Failed to parse evaluation result")
            return None
            
        except Exception as e:
            logger.error(f"Error evaluating resume: {e}", exc_info=True)
            return None
    
    async def _save_resume(
        self, 
        db: AsyncSession, 
        job_id: uuid.UUID, 
        file_path: str, 
        file: UploadFile, 
        parsed_data: dict, 
        evaluation: Optional[dict]
    ) -> Resume:
        """
        Save resume to database.
        
        Args:
            db: Database session
            job_id: Job ID
            file_path: Path to the resume file
            file: Original uploaded file
            parsed_data: Parsed resume data from parser
            evaluation: Evaluation results (optional)
            
        Returns:
            Created Resume object
        """
        # Create resume record
        resume = Resume(
            job_id=job_id,
            candidate_name=parsed_data.get("candidate_name"),
            email=parsed_data.get("email"),
            phone_number=parsed_data.get("phone_number"),
            file_path=file_path,
            file_type=self._get_file_type(file.filename or ""),
            raw_text=parsed_data.get("raw_text"),
            parsed_data=parsed_data.get("parsed_data"),
            matching_score=evaluation.get("matching_score") if evaluation else None,
            match_explanation=evaluation.get("explanation") if evaluation else None,
            status="parsed"
        )
        
        db.add(resume)
        await db.commit()
        await db.refresh(resume)
        
        return resume
    
    def _get_file_type(self, filename: str) -> str:
        """
        Extract file type from filename.
        
        Args:
            filename: Name of the file
            
        Returns:
            File extension (pdf, docx, etc.)
        """
        _, ext = os.path.splitext(filename)
        return ext.lstrip(".").lower()
    
    def _determine_failed_stage(self, error: Exception) -> str:
        """
        Determine which stage failed based on exception type.
        
        Args:
            error: Exception that occurred
            
        Returns:
            Stage name where failure occurred
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check error message for clues
        if "upload" in error_str or "storage" in error_str or "file" in error_str:
            return "uploading"
        elif "parse" in error_str or "extract" in error_str or "pdf" in error_str or "docx" in error_str:
            return "parsing"
        elif "evaluat" in error_str or "match" in error_str or "score" in error_str:
            return "evaluating"
        elif "database" in error_str or "save" in error_str or "commit" in error_str:
            return "saving"
        
        # Check exception type
        if "FileNotFoundError" in error_type or "IOError" in error_type:
            return "uploading"
        elif "ValueError" in error_type or "AttributeError" in error_type:
            return "parsing"
        
        # Default to generic error
        return "processing"


def get_resume_processor(
    session_manager: ResumeSessionManager,
    storage: StorageProvider,
    parser: ResumeParserAgent
) -> ResumeProcessor:
    """
    Dependency factory for resume processor.
    
    Args:
        session_manager: Session manager instance
        storage: Storage provider instance
        parser: Resume parser agent instance
        
    Returns:
        ResumeProcessor instance
    """
    return ResumeProcessor(session_manager, storage, parser)
