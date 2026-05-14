"""
Resume Session Manager Service

Manages resume processing sessions and event distribution for Server-Sent Events (SSE).
Provides session lifecycle management, event emission, and subscription capabilities.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import AsyncIterator, Dict, Optional

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    """Represents a single progress event in resume processing."""
    
    event_type: str  # "starting", "uploading", "parsing", "evaluating", "completed", "error", "all_completed", "keepalive"
    session_id: str
    resume_index: int
    total_resumes: int
    filename: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    # Optional fields for completed/error states
    candidate_name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    matching_score: Optional[float] = None
    error_message: Optional[str] = None
    failed_stage: Optional[str] = None
    resume_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert event to dictionary for JSON serialization."""
        data = {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "resume_index": self.resume_index,
            "total_resumes": self.total_resumes,
            "filename": self.filename,
            "timestamp": self.timestamp.isoformat(),
        }
        
        # Add optional fields if present
        if self.candidate_name is not None:
            data["candidate_name"] = self.candidate_name
        if self.email is not None:
            data["email"] = self.email
        if self.phone_number is not None:
            data["phone_number"] = self.phone_number
        if self.matching_score is not None:
            data["matching_score"] = self.matching_score
        if self.error_message is not None:
            data["error_message"] = self.error_message
        if self.failed_stage is not None:
            data["failed_stage"] = self.failed_stage
        if self.resume_id is not None:
            data["resume_id"] = self.resume_id
            
        return data


@dataclass
class ProcessingSession:
    """Represents a resume processing session."""
    
    session_id: str
    job_id: str
    user_id: str
    total_resumes: int
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed: bool = False
    
    # Event queue for this session
    event_queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=settings.RESUME_EVENT_QUEUE_SIZE))
    
    # Track active SSE connections
    active_connections: int = 0


class ResumeSessionManager:
    """Manages resume processing sessions and event distribution."""
    
    _instance: Optional["ResumeSessionManager"] = None
    
    def __init__(self, session_ttl_seconds: Optional[int] = None):
        """
        Initialize the session manager.
        
        Args:
            session_ttl_seconds: Time-to-live for sessions in seconds. 
                                Defaults to RESUME_SESSION_TTL_HOURS from settings (converted to seconds).
        """
        self._sessions: Dict[str, ProcessingSession] = {}
        # Use new RESUME_SESSION_TTL_HOURS config, fallback to old RESUME_SESSION_TTL_SECONDS for backward compatibility
        if session_ttl_seconds is None:
            session_ttl_seconds = settings.RESUME_SESSION_TTL_HOURS * 3600
        self._session_ttl = timedelta(seconds=session_ttl_seconds)
        self._cleanup_interval_seconds = settings.RESUME_SESSION_CLEANUP_INTERVAL_MINUTES * 60
        self._cleanup_task: Optional[asyncio.Task] = None
        self._keepalive_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
    
    @classmethod
    def get_instance(cls) -> "ResumeSessionManager":
        """Get singleton instance of the session manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def create_session(
        self, 
        job_id: str, 
        user_id: str, 
        total_resumes: int
    ) -> str:
        """
        Create a new processing session and return session_id.
        
        Args:
            job_id: UUID of the job
            user_id: UUID of the user
            total_resumes: Total number of resumes in this session
            
        Returns:
            session_id: Unique identifier for this session
        """
        session_id = str(uuid.uuid4())
        
        session = ProcessingSession(
            session_id=session_id,
            job_id=str(job_id),
            user_id=str(user_id),
            total_resumes=total_resumes
        )
        
        self._sessions[session_id] = session
        
        # Log session creation
        logger.info(
            "Session created",
            extra={
                "event": "session_created",
                "session_id": session_id,
                "job_id": job_id,
                "user_id": user_id,
                "total_resumes": total_resumes,
                "timestamp": session.created_at.isoformat()
            }
        )
        
        # Start cleanup task if not already running (only if event loop is running)
        try:
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running (e.g., in sync tests), skip task creation
            pass
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[ProcessingSession]:
        """
        Retrieve a session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ProcessingSession if found, None otherwise
        """
        return self._sessions.get(session_id)
    
    async def emit_progress(self, session_id: str, event: ProgressEvent) -> None:
        """
        Emit a progress event to all subscribers of this session.
        
        Args:
            session_id: Session identifier
            event: Progress event to emit
        """
        session = self.get_session(session_id)
        if not session:
            return
        
        # Update last activity timestamp
        session.last_activity = datetime.now(UTC)
        
        # Put event in queue (non-blocking)
        try:
            await session.event_queue.put(event)
        except asyncio.QueueFull:
            # Queue is full, skip this event (should rarely happen)
            pass
    
    async def subscribe(self, session_id: str) -> AsyncIterator[ProgressEvent]:
        """
        Subscribe to progress events for a session (SSE stream).
        
        This is an async generator that yields progress events as they occur.
        It also sends keepalive events to prevent connection timeout.
        
        Args:
            session_id: Session identifier
            
        Yields:
            ProgressEvent objects as they are emitted
        """
        session = self.get_session(session_id)
        if not session:
            return
        
        # Increment active connections
        async with self._lock:
            session.active_connections += 1
        
        # Start keepalive task for this connection
        keepalive_task = asyncio.create_task(
            self._send_keepalives(session_id, session.event_queue)
        )
        connection_id = f"{session_id}_{id(keepalive_task)}"
        self._keepalive_tasks[connection_id] = keepalive_task
        
        try:
            while True:
                # Wait for next event with timeout
                try:
                    event = await asyncio.wait_for(
                        session.event_queue.get(),
                        timeout=1.0  # Check every second for cleanup
                    )
                    
                    yield event
                    
                    # If this is the completion event, stop streaming
                    if event.event_type == "all_completed":
                        break
                        
                except asyncio.TimeoutError:
                    # No event received, check if session is still valid
                    if session_id not in self._sessions:
                        break
                    continue
                    
        finally:
            # Cleanup: decrement active connections
            async with self._lock:
                if session_id in self._sessions:
                    session.active_connections = max(0, session.active_connections - 1)
            
            # Cancel keepalive task
            if connection_id in self._keepalive_tasks:
                self._keepalive_tasks[connection_id].cancel()
                try:
                    await self._keepalive_tasks[connection_id]
                except asyncio.CancelledError:
                    pass
                del self._keepalive_tasks[connection_id]
    
    async def _send_keepalives(self, session_id: str, event_queue: asyncio.Queue) -> None:
        """
        Send periodic keepalive events to prevent connection timeout.
        
        Args:
            session_id: Session identifier
            event_queue: Queue to send keepalive events to
        """
        try:
            while session_id in self._sessions:
                await asyncio.sleep(settings.SSE_KEEPALIVE_INTERVAL_SECONDS)
                
                # Create keepalive event
                session = self.get_session(session_id)
                if session:
                    keepalive_event = ProgressEvent(
                        event_type="keepalive",
                        session_id=session_id,
                        resume_index=-1,
                        total_resumes=session.total_resumes,
                        filename=""
                    )
                    
                    try:
                        await asyncio.wait_for(
                            event_queue.put(keepalive_event),
                            timeout=1.0
                        )
                    except (asyncio.QueueFull, asyncio.TimeoutError):
                        # Skip keepalive if queue is full or timeout
                        pass
                        
        except asyncio.CancelledError:
            # Task was cancelled, exit gracefully
            pass
    
    def mark_completed(self, session_id: str) -> None:
        """
        Mark a session as completed.
        
        Args:
            session_id: Session identifier
        """
        session = self.get_session(session_id)
        if session:
            session.completed = True
            session.last_activity = datetime.now(UTC)
            
            # Log session completion
            logger.info(
                "Session completed",
                extra={
                    "event": "session_completed",
                    "session_id": session_id,
                    "job_id": session.job_id,
                    "user_id": session.user_id,
                    "total_resumes": session.total_resumes,
                    "duration_seconds": (session.last_activity - session.created_at).total_seconds(),
                    "timestamp": session.last_activity.isoformat()
                }
            )
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                await self.cleanup_stale_sessions()
            except asyncio.CancelledError:
                break
            except Exception:
                # Continue cleanup loop even if an error occurs
                pass
    
    async def cleanup_stale_sessions(self) -> None:
        """Remove sessions that have exceeded their TTL."""
        now = datetime.now(UTC)
        sessions_to_remove = []
        
        async with self._lock:
            for session_id, session in self._sessions.items():
                # Remove if:
                # 1. Session is completed and has no active connections
                # 2. Session has exceeded TTL since last activity
                time_since_activity = now - session.last_activity
                
                if (session.completed and session.active_connections == 0) or \
                   (time_since_activity > self._session_ttl):
                    sessions_to_remove.append(session_id)
            
            # Remove stale sessions
            for session_id in sessions_to_remove:
                session = self._sessions[session_id]
                
                # Log session cleanup
                logger.info(
                    "Session cleaned up",
                    extra={
                        "event": "session_cleanup",
                        "session_id": session_id,
                        "reason": "completed" if session.completed else "ttl_exceeded",
                        "age_seconds": (now - session.created_at).total_seconds(),
                        "timestamp": now.isoformat()
                    }
                )
                
                # Cancel keepalive tasks if exist
                tasks_to_cancel = [
                    task_id for task_id in self._keepalive_tasks.keys()
                    if task_id.startswith(session_id)
                ]
                for task_id in tasks_to_cancel:
                    self._keepalive_tasks[task_id].cancel()
                    del self._keepalive_tasks[task_id]
                
                del self._sessions[session_id]
    
    def get_active_sessions_count(self) -> int:
        """
        Get the count of currently active (not completed) sessions.
        
        Returns:
            Number of active sessions
        """
        return sum(1 for session in self._sessions.values() if not session.completed)
    
    def get_total_sessions_count(self) -> int:
        """
        Get the total count of all sessions (active and completed).
        
        Returns:
            Total number of sessions
        """
        return len(self._sessions)
    
    def get_sessions_with_connections(self) -> int:
        """
        Get the count of sessions with active SSE connections.
        
        Returns:
            Number of sessions with active connections
        """
        return sum(1 for session in self._sessions.values() if session.active_connections > 0)


# Singleton instance getter
def get_session_manager() -> ResumeSessionManager:
    """Get the singleton instance of ResumeSessionManager."""
    return ResumeSessionManager.get_instance()
