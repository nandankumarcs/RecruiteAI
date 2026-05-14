# Requirements Document

## Introduction

This feature implements real-time progress streaming for resume processing using Server-Sent Events (SSE). Currently, users upload resumes and see only a fake progress bar while the backend processes all resumes synchronously. This feature will provide real-time visibility into which resume is being processed, what stage it's in, and whether any errors occur during processing.

## Glossary

- **Resume_Processor**: The backend service that handles resume upload, parsing, and evaluation
- **Progress_Stream**: The Server-Sent Events (SSE) connection that transmits real-time progress updates
- **Frontend_Client**: The React TypeScript application that displays resume upload progress
- **Resume_Stage**: A distinct phase in resume processing (uploading, parsing, evaluating, completed, error)
- **Job_Description**: The job posting against which resumes are evaluated
- **Processing_Session**: A single batch upload operation containing one or more resumes

## Requirements

### Requirement 1: Server-Sent Events Connection

**User Story:** As a user, I want a real-time connection to the backend, so that I can receive live progress updates during resume processing.

#### Acceptance Criteria

1. WHEN a user initiates resume upload, THE Frontend_Client SHALL establish an SSE connection to the Resume_Processor
2. THE Progress_Stream SHALL remain open until all resumes in the Processing_Session are completed or an unrecoverable error occurs
3. WHEN the Progress_Stream is established, THE Resume_Processor SHALL send a connection confirmation event
4. IF the Progress_Stream connection fails, THEN THE Frontend_Client SHALL display an error message and allow retry
5. WHEN all resumes are processed, THE Resume_Processor SHALL close the Progress_Stream with a completion event

### Requirement 2: Sequential Resume Processing

**User Story:** As a system, I want to process resumes one at a time, so that progress updates are clear and resource usage is controlled.

#### Acceptance Criteria

1. THE Resume_Processor SHALL process resumes sequentially in the order they were uploaded
2. WHEN a resume is being processed, THE Resume_Processor SHALL not start processing the next resume
3. WHEN a resume completes processing, THE Resume_Processor SHALL immediately begin processing the next resume in the queue
4. THE Resume_Processor SHALL maintain the processing order regardless of individual resume processing time

### Requirement 3: Resume Processing Stages

**User Story:** As a user, I want to see which stage each resume is in, so that I understand what is happening during processing.

#### Acceptance Criteria

1. WHEN resume processing begins, THE Resume_Processor SHALL emit a "starting" stage event containing the resume filename
2. WHEN file upload begins, THE Resume_Processor SHALL emit an "uploading" stage event
3. WHEN resume parsing begins, THE Resume_Processor SHALL emit a "parsing" stage event
4. WHEN evaluation against Job_Description begins, THE Resume_Processor SHALL emit an "evaluating" stage event
5. WHEN resume processing completes successfully, THE Resume_Processor SHALL emit a "completed" stage event with matching score and candidate details
6. IF an error occurs at any stage, THEN THE Resume_Processor SHALL emit an "error" stage event with error details

### Requirement 4: Progress Event Structure

**User Story:** As a developer, I want consistent event structure, so that the frontend can reliably parse and display progress updates.

#### Acceptance Criteria

1. THE Resume_Processor SHALL send progress events in SSE format with event type and JSON data
2. WHEN sending a progress event, THE Resume_Processor SHALL include resume identifier, filename, current stage, and timestamp
3. WHERE a resume completes successfully, THE Resume_Processor SHALL include matching_score, candidate_name, email, and phone_number in the event data
4. WHERE an error occurs, THE Resume_Processor SHALL include error_message and failed_stage in the event data
5. THE Resume_Processor SHALL include total_resumes and current_resume_index in every progress event

### Requirement 5: Frontend Progress Display

**User Story:** As a user, I want to see which resume is currently being processed and its progress, so that I know the system is working.

#### Acceptance Criteria

1. THE Frontend_Client SHALL display a list of all uploaded resumes with their current processing stage
2. WHEN a progress event is received, THE Frontend_Client SHALL update the corresponding resume's status in real-time
3. THE Frontend_Client SHALL visually distinguish between resumes that are pending, processing, completed, and errored
4. THE Frontend_Client SHALL display the current stage name for the resume being processed
5. WHEN all resumes are processed, THE Frontend_Client SHALL display a summary showing successful and failed counts

### Requirement 6: Error Handling and Recovery

**User Story:** As a user, I want processing to continue even if one resume fails, so that I don't lose progress on other resumes.

#### Acceptance Criteria

1. IF a resume fails during any processing stage, THEN THE Resume_Processor SHALL emit an error event for that resume
2. WHEN a resume fails, THE Resume_Processor SHALL continue processing the next resume in the queue
3. THE Resume_Processor SHALL not terminate the Progress_Stream due to individual resume errors
4. THE Frontend_Client SHALL display error details for failed resumes while showing progress for remaining resumes
5. WHEN the Processing_Session completes, THE Frontend_Client SHALL show which resumes succeeded and which failed

### Requirement 7: Backend API Endpoint

**User Story:** As a developer, I want a dedicated SSE endpoint, so that the frontend can establish progress streaming connections.

#### Acceptance Criteria

1. THE Resume_Processor SHALL expose an SSE endpoint at `/api/jobs/{job_id}/resumes/stream`
2. WHEN the SSE endpoint is called, THE Resume_Processor SHALL accept a session_id parameter to identify the Processing_Session
3. THE Resume_Processor SHALL validate that the job_id belongs to the authenticated user before streaming progress
4. THE Resume_Processor SHALL return HTTP 401 if the user is not authenticated
5. THE Resume_Processor SHALL return HTTP 404 if the job_id does not exist or does not belong to the user

### Requirement 8: Upload Endpoint Modification

**User Story:** As a developer, I want the upload endpoint to initiate async processing, so that it can return immediately with a session identifier.

#### Acceptance Criteria

1. WHEN resumes are uploaded to `/api/jobs/{job_id}/resumes`, THE Resume_Processor SHALL generate a unique session_id
2. THE Resume_Processor SHALL return the session_id immediately without waiting for processing to complete
3. THE Resume_Processor SHALL initiate background processing for the uploaded resumes
4. THE Resume_Processor SHALL associate all progress events with the session_id
5. THE Resume_Processor SHALL validate file types and sizes before accepting uploads

### Requirement 9: Connection Timeout and Cleanup

**User Story:** As a system, I want to clean up stale connections, so that server resources are not exhausted.

#### Acceptance Criteria

1. THE Resume_Processor SHALL send keepalive events every 15 seconds while processing is active
2. IF the Frontend_Client disconnects, THEN THE Resume_Processor SHALL detect the disconnection and stop sending events
3. THE Resume_Processor SHALL continue background processing even if the Frontend_Client disconnects
4. THE Frontend_Client SHALL automatically reconnect if the Progress_Stream connection is lost during active processing
5. WHEN reconnecting, THE Frontend_Client SHALL use the same session_id to resume receiving progress updates

### Requirement 10: Concurrent Session Handling

**User Story:** As a user, I want to upload multiple batches of resumes, so that I can process different sets independently.

#### Acceptance Criteria

1. THE Resume_Processor SHALL support multiple concurrent Processing_Sessions for the same user
2. THE Resume_Processor SHALL isolate progress events by session_id
3. WHEN a Frontend_Client connects with a session_id, THE Resume_Processor SHALL only send events for that session
4. THE Resume_Processor SHALL process resumes sequentially within each session but allow parallel processing across different sessions
5. THE Resume_Processor SHALL clean up session data after processing completes or after 1 hour of inactivity
