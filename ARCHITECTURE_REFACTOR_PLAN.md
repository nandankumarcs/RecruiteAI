# Architecture Refactor Plan: Automated Ranking & Evaluation

This document outlines the phased approach to refactoring RecruiteAI into a Job-centric automated recruitment platform.

## Current vs. New Architecture Mapping

| Feature | Current State | New Architecture | Refactor Strategy |
| :--- | :--- | :--- | :--- |
| **Questions** | Linked to `Resume` | Linked to `Job` | Migrate `JobQuestion` table; update relationship. |
| **Resume Parsing** | Basic extraction | Extraction + JD Matching Score | Extend `ResumeService` with LLM scoring logic. |
| **Job Dashboard** | Flat list of jobs | Job -> Ranked Resume List | Refactor `JobDetail` into a Tab-based dashboard. |
| **Evaluation** | Transcript only | In-depth soft-skill analysis | New `EvaluationService` triggered on call end. |

---

## Phase 1: Database & Model Foundation
**Goal**: Restructure relationships to support Job-level questions and Resume matching scores.

1.  **Database Migration**:
    *   **Jobs Table**: Add `evaluation_criteria` (optional).
    *   **Questions Table**: Change foreign key from `resume_id` to `job_id`.
    *   **Resume Table**: Add `matching_score: Float` (0-100) and `match_explanation: Text`.
    *   **Call Table**: Add `evaluation_score: Float`, `evaluation_summary: Text`, and `behavioral_metrics: JSON`.
2.  **Model Cleanup**:
    *   Remove legacy candidate-specific question methods.
    *   Update SQLAlchemy relationships for `Job.questions` and `Job.resumes`.

## Phase 2: Resume Screening Agent
**Goal**: Implement the automated "one-by-one" parser and JD matching engine.

1.  **Scoring Service**:
    *   Implement LLM-based scoring in `backend/app/services/resume.py`.
    *   Input: `Resume.content` + `Job.description`.
    *   Output: Numerical score + justification.
2.  **Background Processing**:
    *   Trigger scoring immediately after a resume is parsed.
    *   Handle batch uploads by processing resumes sequentially to avoid rate limits.

## Phase 3: Job-Level Question Management
**Goal**: Move question management to the Job Detail page.

1.  **Job Detail Tabbed UI**:
    *   Refactor `JobDetail.tsx` to use Tabs: `Candidates`, `Questions`, `Job Description`.
2.  **Questions Tab**:
    *   Create `QuestionsTab.tsx` for CRUD operations on job-level questions.
3.  **Call Integration**:
    *   Update `RealtimeBridge` to pull questions from the parent `Job` during the interview.

## Phase 4: Post-Interview Evaluation Agent
**Goal**: Intelligent analysis of interview performance after the call ends.

1.  **Evaluation Engine**:
    *   New `EvaluationService` triggered on call completion.
    *   Analyzes: Transcript content + behavioral signals (pauses, hesitation, clarity).
2.  **Decision Support**:
    *   Generate a "Plain English" summary and a recommendation for the recruiter.
3.  **UI Feedback**:
    *   Display these insights prominently in the dashboard and call summary views.

## Phase 5: Consolidation & Cleanup
**Goal**: Final UI polish and removal of all dead code.

1.  **Ranked Dashboard**:
    *   Default the candidate table to sort by `matching_score` descending.
2.  **Dead Code Removal**:
    *   Delete old candidate-specific question logic from both frontend and backend.
3.  **End-to-End Validation**:
    *   Verify the full pipeline: Create Job -> Bulk Upload -> Auto-Rank -> Interview -> Auto-Evaluate.
