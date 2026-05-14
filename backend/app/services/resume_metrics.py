"""
Resume Processing Metrics Service

Tracks metrics for resume processing sessions including:
- Active sessions count
- Average processing time per resume
- Error rates by stage
- Session lifecycle events
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Dict, List, Optional
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class ResumeProcessingMetrics:
    """Metrics for a single resume processing operation."""
    
    session_id: str
    resume_index: int
    filename: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    stage_timings: Dict[str, float] = field(default_factory=dict)  # stage -> duration in seconds
    success: bool = False
    error_stage: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SessionMetrics:
    """Aggregated metrics for a processing session."""
    
    session_id: str
    job_id: str
    user_id: str
    total_resumes: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    resume_metrics: List[ResumeProcessingMetrics] = field(default_factory=list)
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Total session duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    @property
    def success_count(self) -> int:
        """Number of successfully processed resumes."""
        return sum(1 for m in self.resume_metrics if m.success)
    
    @property
    def error_count(self) -> int:
        """Number of failed resumes."""
        return sum(1 for m in self.resume_metrics if not m.success)
    
    @property
    def error_rate(self) -> float:
        """Error rate as a percentage."""
        if not self.resume_metrics:
            return 0.0
        return (self.error_count / len(self.resume_metrics)) * 100
    
    @property
    def average_processing_time(self) -> Optional[float]:
        """Average processing time per resume in seconds."""
        completed_times = [
            (m.completed_at - m.started_at).total_seconds()
            for m in self.resume_metrics
            if m.completed_at
        ]
        if completed_times:
            return statistics.mean(completed_times)
        return None
    
    @property
    def errors_by_stage(self) -> Dict[str, int]:
        """Count of errors grouped by stage."""
        errors = defaultdict(int)
        for m in self.resume_metrics:
            if not m.success and m.error_stage:
                errors[m.error_stage] += 1
        return dict(errors)


class ResumeMetricsCollector:
    """Collects and aggregates metrics for resume processing."""
    
    _instance: Optional["ResumeMetricsCollector"] = None
    
    def __init__(self):
        """Initialize the metrics collector."""
        self._session_metrics: Dict[str, SessionMetrics] = {}
        self._active_resume_metrics: Dict[str, ResumeProcessingMetrics] = {}  # key: session_id:resume_index
    
    @classmethod
    def get_instance(cls) -> "ResumeMetricsCollector":
        """Get singleton instance of the metrics collector."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def start_session(
        self,
        session_id: str,
        job_id: str,
        user_id: str,
        total_resumes: int
    ) -> None:
        """
        Record the start of a processing session.
        
        Args:
            session_id: Unique session identifier
            job_id: Job UUID
            user_id: User UUID
            total_resumes: Total number of resumes in session
        """
        session_metrics = SessionMetrics(
            session_id=session_id,
            job_id=job_id,
            user_id=user_id,
            total_resumes=total_resumes,
            started_at=datetime.now(UTC)
        )
        self._session_metrics[session_id] = session_metrics
        
        logger.info(
            "session_started",
            extra={
                "session_id": session_id,
                "job_id": job_id,
                "user_id": user_id,
                "total_resumes": total_resumes,
                "timestamp": session_metrics.started_at.isoformat()
            }
        )
    
    def start_resume(
        self,
        session_id: str,
        resume_index: int,
        filename: str
    ) -> None:
        """
        Record the start of resume processing.
        
        Args:
            session_id: Session identifier
            resume_index: Index of resume in session
            filename: Resume filename
        """
        key = f"{session_id}:{resume_index}"
        resume_metrics = ResumeProcessingMetrics(
            session_id=session_id,
            resume_index=resume_index,
            filename=filename,
            started_at=datetime.now(UTC)
        )
        self._active_resume_metrics[key] = resume_metrics
        
        logger.info(
            "resume_started",
            extra={
                "session_id": session_id,
                "resume_index": resume_index,
                "filename": filename,
                "timestamp": resume_metrics.started_at.isoformat()
            }
        )
    
    def record_stage_timing(
        self,
        session_id: str,
        resume_index: int,
        stage: str,
        duration_seconds: float
    ) -> None:
        """
        Record timing for a processing stage.
        
        Args:
            session_id: Session identifier
            resume_index: Index of resume in session
            stage: Stage name (uploading, parsing, evaluating)
            duration_seconds: Duration in seconds
        """
        key = f"{session_id}:{resume_index}"
        if key in self._active_resume_metrics:
            self._active_resume_metrics[key].stage_timings[stage] = duration_seconds
            
            logger.debug(
                "stage_completed",
                extra={
                    "session_id": session_id,
                    "resume_index": resume_index,
                    "stage": stage,
                    "duration_seconds": duration_seconds
                }
            )
    
    def complete_resume(
        self,
        session_id: str,
        resume_index: int,
        success: bool,
        error_stage: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Record the completion of resume processing.
        
        Args:
            session_id: Session identifier
            resume_index: Index of resume in session
            success: Whether processing succeeded
            error_stage: Stage where error occurred (if failed)
            error_message: Error message (if failed)
        """
        key = f"{session_id}:{resume_index}"
        if key not in self._active_resume_metrics:
            return
        
        resume_metrics = self._active_resume_metrics[key]
        resume_metrics.completed_at = datetime.now(UTC)
        resume_metrics.success = success
        resume_metrics.error_stage = error_stage
        resume_metrics.error_message = error_message
        
        # Move to session metrics
        if session_id in self._session_metrics:
            self._session_metrics[session_id].resume_metrics.append(resume_metrics)
        
        # Calculate total processing time
        processing_time = (resume_metrics.completed_at - resume_metrics.started_at).total_seconds()
        
        # Log completion
        log_data = {
            "session_id": session_id,
            "resume_index": resume_index,
            "filename": resume_metrics.filename,
            "success": success,
            "processing_time_seconds": processing_time,
            "stage_timings": resume_metrics.stage_timings,
            "timestamp": resume_metrics.completed_at.isoformat()
        }
        
        if not success:
            log_data["error_stage"] = error_stage
            log_data["error_message"] = error_message
            logger.warning("resume_failed", extra=log_data)
        else:
            logger.info("resume_completed", extra=log_data)
        
        # Clean up active metrics
        del self._active_resume_metrics[key]
    
    def complete_session(self, session_id: str) -> None:
        """
        Record the completion of a processing session.
        
        Args:
            session_id: Session identifier
        """
        if session_id not in self._session_metrics:
            return
        
        session_metrics = self._session_metrics[session_id]
        session_metrics.completed_at = datetime.now(UTC)
        
        # Log session summary
        logger.info(
            "session_completed",
            extra={
                "session_id": session_id,
                "job_id": session_metrics.job_id,
                "user_id": session_metrics.user_id,
                "total_resumes": session_metrics.total_resumes,
                "success_count": session_metrics.success_count,
                "error_count": session_metrics.error_count,
                "error_rate": session_metrics.error_rate,
                "duration_seconds": session_metrics.duration_seconds,
                "average_processing_time": session_metrics.average_processing_time,
                "errors_by_stage": session_metrics.errors_by_stage,
                "timestamp": session_metrics.completed_at.isoformat()
            }
        )
    
    def get_active_sessions_count(self) -> int:
        """
        Get the count of currently active sessions.
        
        Returns:
            Number of active sessions
        """
        active_count = sum(
            1 for session in self._session_metrics.values()
            if session.completed_at is None
        )
        return active_count
    
    def get_session_metrics(self, session_id: str) -> Optional[SessionMetrics]:
        """
        Get metrics for a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionMetrics if found, None otherwise
        """
        return self._session_metrics.get(session_id)
    
    def get_global_metrics(self) -> Dict:
        """
        Get aggregated global metrics across all sessions.
        
        Returns:
            Dictionary containing global metrics
        """
        all_sessions = list(self._session_metrics.values())
        completed_sessions = [s for s in all_sessions if s.completed_at is not None]
        
        if not completed_sessions:
            return {
                "total_sessions": len(all_sessions),
                "active_sessions": self.get_active_sessions_count(),
                "completed_sessions": 0,
                "total_resumes_processed": 0,
                "total_resumes_succeeded": 0,
                "total_resumes_failed": 0,
                "global_error_rate": 0.0,
                "average_session_duration": None,
                "average_resume_processing_time": None,
                "errors_by_stage": {}
            }
        
        total_resumes = sum(len(s.resume_metrics) for s in completed_sessions)
        total_succeeded = sum(s.success_count for s in completed_sessions)
        total_failed = sum(s.error_count for s in completed_sessions)
        
        # Aggregate errors by stage
        all_errors_by_stage = defaultdict(int)
        for session in completed_sessions:
            for stage, count in session.errors_by_stage.items():
                all_errors_by_stage[stage] += count
        
        # Calculate averages
        session_durations = [s.duration_seconds for s in completed_sessions if s.duration_seconds]
        avg_session_duration = statistics.mean(session_durations) if session_durations else None
        
        all_processing_times = []
        for session in completed_sessions:
            for resume in session.resume_metrics:
                if resume.completed_at:
                    all_processing_times.append(
                        (resume.completed_at - resume.started_at).total_seconds()
                    )
        avg_processing_time = statistics.mean(all_processing_times) if all_processing_times else None
        
        return {
            "total_sessions": len(all_sessions),
            "active_sessions": self.get_active_sessions_count(),
            "completed_sessions": len(completed_sessions),
            "total_resumes_processed": total_resumes,
            "total_resumes_succeeded": total_succeeded,
            "total_resumes_failed": total_failed,
            "global_error_rate": (total_failed / total_resumes * 100) if total_resumes > 0 else 0.0,
            "average_session_duration_seconds": avg_session_duration,
            "average_resume_processing_time_seconds": avg_processing_time,
            "errors_by_stage": dict(all_errors_by_stage)
        }
    
    def cleanup_old_sessions(self, max_sessions: int = 1000) -> None:
        """
        Clean up old completed sessions to prevent memory growth.
        
        Args:
            max_sessions: Maximum number of completed sessions to keep
        """
        completed_sessions = [
            (session_id, session)
            for session_id, session in self._session_metrics.items()
            if session.completed_at is not None
        ]
        
        if len(completed_sessions) > max_sessions:
            # Sort by completion time and remove oldest
            completed_sessions.sort(key=lambda x: x[1].completed_at)
            to_remove = completed_sessions[:-max_sessions]
            
            for session_id, _ in to_remove:
                del self._session_metrics[session_id]
            
            logger.info(
                "metrics_cleanup",
                extra={
                    "removed_sessions": len(to_remove),
                    "remaining_sessions": len(self._session_metrics)
                }
            )


def get_metrics_collector() -> ResumeMetricsCollector:
    """Get the singleton instance of ResumeMetricsCollector."""
    return ResumeMetricsCollector.get_instance()
