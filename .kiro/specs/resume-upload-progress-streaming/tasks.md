# Implementation Plan: Resume Upload Progress Streaming

## Overview

This implementation adds real-time progress streaming for resume processing using Server-Sent Events (SSE). The system will process resumes sequentially and emit progress events at each stage (starting, uploading, parsing, evaluating, completed/error), providing users with live visibility into the processing status of each resume.

## Tasks

- [x] 1. Set up backend infrastructure for SSE streaming
  - [x] 1.1 Install sse-starlette dependency
    - Add `sse-starlette` to backend requirements
    - Update requirements.txt or pyproject.toml
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Create Session Manager service
    - Implement `app/services/resume_session_manager.py` with `ProgressEvent` and `ProcessingSession` dataclasses
    - Implement `ResumeSessionManager` class with session creation, retrieval, event emission, and subscription methods
    - Add session cleanup background task with TTL-based expiration
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 9.1, 9.2, 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 1.3 Create Progress Emitter service
    - Implement `app/services/resume_progress_emitter.py` with convenience methods for each event type
    - Add methods: `emit_starting`, `emit_uploading`, `emit_parsing`, `emit_evaluating`, `emit_completed`, `emit_error`, `emit_all_completed`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.4 Add configuration settings
    - Add session TTL, keepalive interval, and queue size settings to `app/config.py`
    - _Requirements: 9.1, 10.5_

- [x] 2. Implement Resume Processor with progress streaming
  - [x] 2.1 Create Resume Processor service
    - Implement `app/services/resume_processor.py` with `ResumeProcessor` class
    - Add `process_resumes` method that processes resumes sequentially
    - Emit progress events at each stage: starting, uploading, parsing, evaluating, completed
    - Handle errors gracefully and emit error events with failed_stage
    - Continue processing next resume after individual failures
    - Emit all_completed event when all resumes are processed
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 2.2 Write unit tests for Resume Processor
    - Test sequential processing order
    - Test progress emission at each stage
    - Test error handling for upload, parsing, and evaluation failures
    - Test continuation after individual resume failure
    - Test all_completed emission
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.1, 6.2, 6.3_

- [x] 3. Modify upload endpoint for async processing
  - [x] 3.1 Update upload endpoint in resumes router
    - Modify `POST /api/jobs/{job_id}/resumes` to return session_id immediately (HTTP 202)
    - Create session using Session Manager
    - Start background task for resume processing
    - Return response with session_id and total_resumes
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 3.2 Write unit tests for modified upload endpoint
    - Test session creation
    - Test background task initiation
    - Test response format (session_id, total_resumes)
    - Test file validation
    - Test authentication and authorization
    - _Requirements: 7.3, 7.4, 7.5, 8.1, 8.2, 8.5_

- [x] 4. Implement SSE streaming endpoint
  - [x] 4.1 Create SSE stream endpoint
    - Add `GET /api/jobs/{job_id}/resumes/stream` endpoint in resumes router
    - Validate job ownership and session existence
    - Subscribe to session events using Session Manager
    - Stream events in SSE format: `event: <type>\ndata: <json>\n\n`
    - Send keepalive comments every 15 seconds
    - Close stream after session_complete event
    - Handle client disconnections gracefully
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4, 7.5, 9.1, 9.2, 9.3_

  - [ ]* 4.2 Write unit tests for SSE endpoint
    - Test SSE connection establishment
    - Test event streaming format
    - Test session validation
    - Test job ownership validation
    - Test keepalive events
    - Test connection cleanup
    - _Requirements: 1.1, 1.2, 1.3, 7.2, 7.3, 7.4, 7.5, 9.1, 9.2_

- [ ] 5. Checkpoint - Backend implementation complete
  - Ensure all backend tests pass
  - Manually test upload endpoint returns session_id
  - Manually test SSE endpoint streams events
  - Ask the user if questions arise

- [x] 6. Implement frontend SSE client hook
  - [x] 6.1 Create useResumeProgressStream hook
    - Implement `frontend/src/hooks/useResumeProgressStream.ts`
    - Establish EventSource connection with session_id
    - Handle connection open, error, and close events
    - Listen for event types: starting, uploading, parsing, evaluating, completed, error, session_complete
    - Update resume state array based on received events
    - Track connection status (isConnected, isComplete, error)
    - Implement automatic reconnection on connection loss
    - Clean up EventSource on unmount
    - _Requirements: 1.1, 1.4, 5.1, 5.2, 5.3, 5.4, 9.4, 9.5_

  - [ ]* 6.2 Write unit tests for SSE hook
    - Test connection establishment
    - Test event handling for each event type
    - Test state updates on events
    - Test reconnection logic
    - Test cleanup on unmount
    - Mock EventSource API
    - _Requirements: 1.1, 1.4, 5.2, 9.4_

- [x] 7. Update ResumeUploader component
  - [x] 7.1 Modify ResumeUploader to use SSE streaming
    - Update `frontend/src/components/resumes/ResumeUploader.tsx`
    - Add sessionId state and useResumeProgressStream hook
    - Modify uploadResumes to receive session_id from API response
    - Display real-time progress for each resume using hook state
    - Show status icons (pending, processing, completed, error)
    - Display stage name for processing resumes
    - Show candidate details for completed resumes
    - Display error messages for failed resumes
    - Show completion summary when isComplete is true
    - Handle connection errors with retry option
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.4, 6.5_

  - [ ]* 7.2 Write unit tests for ResumeUploader component
    - Test file selection and validation
    - Test upload initiation
    - Test session_id reception
    - Test progress display for each resume
    - Test completion summary display
    - Test error display for failed resumes
    - Mock API and SSE hook
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.4, 6.5_

- [x] 8. Checkpoint - Frontend implementation complete
  - Ensure all frontend tests pass
  - Manually test file upload and progress display
  - Manually test error handling
  - Ask the user if questions arise

- [x] 9. Integration testing and bug fixes
  - [ ]* 9.1 Write end-to-end integration tests
    - Test complete upload flow with multiple resumes
    - Test SSE connection and event reception
    - Test sequential processing order
    - Test error recovery (mix of valid and invalid resumes)
    - Test reconnection after disconnection
    - Test concurrent sessions isolation
    - _Requirements: 2.1, 2.2, 2.3, 6.1, 6.2, 6.3, 9.3, 9.4, 9.5, 10.1, 10.2, 10.3, 10.4_

  - [x] 9.2 Manual testing and bug fixes
    - Test with single resume upload
    - Test with multiple resumes (10+)
    - Test with invalid files (corrupted PDF, wrong format)
    - Test network disconnection during processing
    - Test browser refresh during processing
    - Test concurrent uploads for different jobs
    - Fix any bugs discovered during testing
    - _Requirements: All_

- [x] 10. Deployment configuration
  - [x] 10.1 Configure reverse proxy for SSE
    - Update Nginx configuration to disable buffering for SSE endpoint
    - Set appropriate connection timeout (> 1 hour)
    - Add proxy headers for SSE
    - _Requirements: 9.1, 9.2_

  - [x] 10.2 Add environment variables
    - Add RESUME_SESSION_TTL_HOURS to environment configuration
    - Add RESUME_SESSION_CLEANUP_INTERVAL_MINUTES
    - Add SSE_KEEPALIVE_INTERVAL_SECONDS
    - Document environment variables in README
    - _Requirements: 9.1, 10.5_

  - [x] 10.3 Add monitoring and logging
    - Add structured logging for session lifecycle events
    - Add metrics for active sessions count
    - Add metrics for average processing time per resume
    - Add error rate tracking by stage
    - Add health check endpoint for resume processing
    - _Requirements: All_

- [x] 11. Final checkpoint - Ready for deployment
  - Ensure all tests pass (unit, integration)
  - Verify deployment configuration is correct
  - Verify environment variables are set
  - Verify monitoring is working
  - Ask the user if questions arise

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The design uses Python (FastAPI) for backend and TypeScript (React) for frontend
- This feature is infrastructure-heavy and uses integration tests rather than property-based tests
- Session management is in-memory for MVP; can be migrated to Redis for horizontal scaling
- SSE is chosen over WebSocket for simplicity and automatic reconnection
- Background processing uses FastAPI's BackgroundTasks for MVP; can be migrated to Celery for better resource management

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["2.1", "3.1"] },
    { "id": 3, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 4, "tasks": ["4.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "9.1"] },
    { "id": 7, "tasks": ["9.2"] },
    { "id": 8, "tasks": ["10.1", "10.2", "10.3"] }
  ]
}
```
