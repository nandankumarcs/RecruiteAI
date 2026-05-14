# Implementation Plan: Pre-Generated TTS and Filler Audio System

## Overview

This implementation plan breaks down the pre-generated TTS and filler audio system into discrete coding tasks. The system introduces a hybrid architecture that pre-generates audio for stable prompts (consent opener, interview questions, reprompts, clarifications, closers) while maintaining dynamic TTS fallback. The implementation follows a layered approach: data models → services → runtime integration → management commands.

## Tasks

- [x] 1. Create database models and migration for audio prompt library
  - [x] 1.1 Create AudioPromptAsset SQLAlchemy model
    - Define model in `backend/app/models/audio_prompt_asset.py`
    - Include all fields: id, template_key, category, text, file_path, file_hash, duration_ms, provider, speaker, language_code, sample_rate, codec, pace, job_id, question_id, version, status, last_generated_at, created_at, updated_at
    - Add composite unique constraint on (template_key, version)
    - Add indexes: template_key, job_question, file_hash, status, category
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 12.1, 12.2, 16.7, 17.5_
  
  - [x] 1.2 Create JobPromptGenerationRun SQLAlchemy model (optional)
    - Define model in `backend/app/models/job_prompt_generation_run.py`
    - Include fields: id, job_id, status, started_at, completed_at, success_count, failure_count, error_summary, created_at
    - _Requirements: 3.5, 14.5_
  
  - [x] 1.3 Create Alembic migration for new tables
    - Generate migration with `alembic revision --autogenerate -m "add_audio_prompt_assets"`
    - Verify migration includes both tables with all constraints and indexes
    - Test migration up and down
    - _Requirements: 1.1, 1.2_

- [ ] 2. Implement PromptAudioService for audio generation and retrieval
  - [x] 2.1 Create PromptAudioService class with core methods
    - Create `backend/app/services/prompt_audio_service.py`
    - Implement `__init__` with session_factory, storage_provider, tts_provider dependencies
    - Implement `_normalize_text` method (remove extra whitespace, lowercase, strip punctuation)
    - Implement `_compute_asset_hash` method (SHA-256 of normalized_text + speaker + language_code + pace + provider)
    - Implement `_find_by_hash` helper for asset lookup
    - Implement `_create_or_update_asset` helper for asset persistence
    - _Requirements: 2.1, 2.2, 17.1, 17.2, 17.3, 17.4_
  
  - [x] 2.2 Implement ensure_prompt_audio method
    - Check for existing ready asset by hash (unless force_regenerate=True)
    - Create or update asset record with status=pending
    - Call `_synthesize_and_persist` to generate audio
    - Update status to ready or failed based on synthesis result
    - Return AudioPromptAsset instance
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  
  - [x] 2.3 Implement _synthesize_and_persist method
    - Call Sarvam TTS API with configured speaker, language_code, pace (1.2)
    - Ensure audio format is raw linear16 PCM (8kHz, no WAV container)
    - Save audio bytes to storage with path pattern `prompt-audio/{category}/{version}/{hash}.pcm`
    - Calculate duration_ms from audio length
    - Update asset file_path and duration_ms
    - Handle synthesis errors and log failures
    - _Requirements: 2.5, 2.6, 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 20.1_
  
  - [x] 2.4 Implement get_ready_audio_asset method
    - Accept lookup criteria: template_key, job_id, question_id
    - Query database for ready asset matching criteria
    - Return AudioPromptAsset or None
    - _Requirements: 1.6, 2.7_
  
  - [x] 2.5 Implement ensure_question_audio_for_job method
    - Query all questions for the given job_id
    - For each question, generate template_key as `question_{question_id}`
    - Call ensure_prompt_audio for each question with category=question
    - Return list of AudioPromptAsset instances
    - _Requirements: 3.2, 3.3, 3.4_
  
  - [x] 2.6 Implement ensure_default_fillers method
    - Define default filler texts: "understood", "got it", "okay", "thanks", "sure", "one moment"
    - For each filler, generate template_key as `filler_{text_slug}`
    - Call ensure_prompt_audio with category=filler and job_id=None
    - Return list of AudioPromptAsset instances
    - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [x] 3. Checkpoint - Verify audio generation service
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement RuntimeSelectionLayer for audio source routing
  - [x] 4.1 Create PromptCategory enum and AudioSourceSelection dataclass
    - Create `backend/app/services/runtime_selection_layer.py`
    - Define PromptCategory enum: OPENER, QUESTION, REPROMPT, CLARIFICATION, OFF_TOPIC_REDIRECT, CLOSING, FILLER, FALLBACK_DYNAMIC
    - Define AudioSourceSelection dataclass with fields: source_type, template_key, asset, fallback_text, filler_key
    - _Requirements: 5.4_
  
  - [x] 4.2 Implement RuntimeSelectionLayer class with classification logic
    - Implement `__init__` with prompt_audio_service and filler_queue_manager dependencies
    - Implement `_classify_turn` method using conversation state and text patterns
    - Priority order: consent opener → closing → off-topic redirect → reprompt → clarification → question → fallback
    - Implement helper methods: `_is_closing_phrase`, `_is_redirect_phrase`, `_is_reprompt_phrase`, `_is_clarification_phrase`
    - _Requirements: 5.1, 5.4_
  
  - [x] 4.3 Implement template matching logic
    - Implement `_normalize_for_matching` helper (lowercase, strip whitespace)
    - Implement `_match_template` method with category-specific pattern matching
    - Define patterns for opener: return "opener_consent"
    - Define patterns for reprompts: "can you tell me more" → "reprompt_elaborate", "can you elaborate" → "reprompt_elaborate", "can you give me an example" → "reprompt_example", "could you clarify" → "reprompt_clarify"
    - Define patterns for clarifications: "could you repeat" → "clarification_repeat", "can you say that again" → "clarification_repeat", "tell me more about" → "clarification_more"
    - Define patterns for closings: "thank you for your time" → "closing_thank_you", "we'll be in touch" → "closing_next_steps"
    - For questions, return None (resolved by question_id)
    - _Requirements: 5.1, 5.2, 5.5, 9.2, 10.1, 10.3, 11.1, 11.3_
  
  - [x] 4.4 Implement select_audio_source method
    - Classify turn using `_classify_turn`
    - Match template using `_match_template`
    - For questions, generate template_key as `question_{current_question_id}`
    - Lookup asset using prompt_audio_service.get_ready_audio_asset
    - If asset is ready, return AudioSourceSelection with source_type=prebuilt_asset
    - Otherwise, return AudioSourceSelection with source_type=live_tts_fallback or live_tts
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 8.2, 8.3, 8.4_

- [x] 5. Implement FillerQueueManager for filler audio logic
  - [x] 5.1 Create FillerQueueManager class with threshold constants
    - Create `backend/app/services/filler_queue_manager.py`
    - Define FILLER_THRESHOLD_MS = 300
    - Define FILLER_COOLDOWN_MS = 5000
    - Define `_filler_keys` list: ["filler_understood", "filler_got_it", "filler_okay", "filler_thanks", "filler_sure", "filler_one_moment"]
    - Implement `__init__` with prompt_audio_service dependency
    - _Requirements: 6.2, 6.4_
  
  - [x] 5.2 Implement should_play_filler method
    - Rule 1: Return (False, None) if main_prompt_ready=True
    - Rule 2: Return (False, None) if estimated_latency_ms < FILLER_THRESHOLD_MS
    - Rule 3: Check cooldown - return (False, None) if time since last filler < FILLER_COOLDOWN_MS
    - Rule 4: Select filler using `_select_filler_key` and return (True, filler_key)
    - _Requirements: 6.2, 6.3, 6.4_
  
  - [x] 5.3 Implement filler selection and retrieval methods
    - Implement `_select_filler_key` with round-robin logic to avoid repetition
    - Implement `get_filler_asset` to retrieve ready filler by template_key
    - _Requirements: 6.2_

- [x] 6. Integrate cached audio playback into DeepgramRuntime
  - [x] 6.1 Add RuntimeSelectionLayer to DeepgramOpenAIPipelineRuntime
    - Modify `backend/app/services/deepgram_runtime.py`
    - Add runtime_selection, _last_filler_played_at, _last_filler_key instance variables in `__init__`
    - Initialize RuntimeSelectionLayer with PromptAudioService and FillerQueueManager
    - _Requirements: 5.1, 7.1_
  
  - [x] 6.2 Implement _play_cached_audio method
    - Accept websocket, provider, stream_id, asset, call_id parameters
    - Load audio bytes from storage using asset.file_path
    - Stream audio chunks using same logic as live TTS (_audio_frame_settings)
    - Mark first audio chunk with _mark_first_assistant_audio
    - Handle websocket disconnection gracefully
    - Log playback progress and completion
    - _Requirements: 7.1, 7.2, 7.4, 20.3_
  
  - [x] 6.3 Modify assistant turn playback path to use audio source selection
    - Route the existing `_start_tts_task` flow through a dedicated assistant-turn playback helper
    - Call runtime_selection.select_audio_source with assistant_text, conversation_state, job_id, questions
    - Estimate latency based on source_type (800ms for live_tts, 0ms for prebuilt_asset)
    - Call filler_queue.should_play_filler to determine if filler needed
    - If filler needed, play filler using _play_cached_audio and update _last_filler_played_at
    - If source_type is prebuilt_asset, play cached audio using _play_cached_audio
    - Otherwise, fall back to _speak_text with live TTS
    - Log audio_source, template_key, asset_id for every turn
    - _Requirements: 5.1, 5.2, 5.3, 5.6, 6.1, 6.2, 6.5, 6.6, 7.1, 7.4, 7.5, 8.2, 8.3, 8.4, 8.5, 13.1, 13.3_
  
  - [x] 6.4 Ensure barge-in compatibility for cached audio
    - Verify that existing barge-in logic (STT detection → stop playback) works for cached audio
    - Ensure _play_cached_audio checks websocket state before sending each chunk
    - Log barge_in_event when playback is interrupted
    - _Requirements: 7.3, 19.1, 19.2, 19.3, 19.4, 19.5_

- [x] 7. Checkpoint - Verify runtime integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Create management command for audio generation
  - [x] 8.1 Create generate_prompt_audio management command
    - Create `backend/app/management/commands/generate_prompt_audio.py`
    - Accept CLI arguments: --category, --template-key, --job-id, --force-regenerate
    - Implement logic to generate fillers when category=filler
    - Implement logic to generate question audio when job_id is provided
    - Implement logic to generate specific template when template_key is provided
    - Report success_count and failure_count at completion
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  
  - [x] 8.2 Add default template definitions
    - Create `backend/app/services/prompt_templates.py`
    - Define DEFAULT_OPENER_TEXT: "Hello! I'm calling from the recruitment team. I'd like to ask you a few questions about your application. This call will be recorded for quality purposes. Do you have a few minutes to talk?"
    - Define DEFAULT_REPROMPT_TEXTS: {"reprompt_elaborate": "Can you tell me more about that?", "reprompt_example": "Can you give me an example?", "reprompt_clarify": "Could you clarify that?"}
    - Define DEFAULT_CLARIFICATION_TEXTS: {"clarification_repeat": "Could you repeat that?", "clarification_more": "Tell me more about that."}
    - Define DEFAULT_CLOSING_TEXTS: {"closing_thank_you": "Thank you for your time.", "closing_next_steps": "We'll be in touch soon."}
    - Define DEFAULT_FILLER_TEXTS: {"filler_understood": "Understood.", "filler_got_it": "Got it.", "filler_okay": "Okay.", "filler_thanks": "Thanks.", "filler_sure": "Sure.", "filler_one_moment": "One moment."}
    - _Requirements: 9.2, 10.1, 10.2, 11.1, 4.2_

- [x] 9. Add async job question audio generation trigger
  - [x] 9.1 Create background task for question audio generation
    - Create `backend/app/tasks/audio_generation.py`
    - Implement `generate_question_audio_for_job_task` as async background task
    - Accept job_id parameter
    - Call prompt_audio_service.ensure_question_audio_for_job
    - Create JobPromptGenerationRun record to track progress
    - Update success_count and failure_count
    - Mark run as completed when finished
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 18.1, 18.2, 18.3, 18.5_
  
  - [x] 9.2 Add trigger on question save/update
    - Modify `backend/app/routers/jobs.py` question creation/update endpoints
    - After database commit, coalesce and trigger generate_question_audio_for_job_task asynchronously
    - Do not block HTTP response
    - _Requirements: 3.1, 18.1, 18.2_
  
  - [x] 9.3 Implement question text staleness detection
    - Modify RuntimeSelectionLayer.select_audio_source to compare asset.text with current question.text
    - If texts don't match, log warning and fall back to live TTS
    - Mark asset as stale in logs
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

- [x] 10. Add observability and metrics logging
  - [x] 10.1 Extend observability service for audio source tracking
    - Modify `backend/app/services/observability.py`
    - Add structured logging for audio_source, template_key, asset_id, asset_lookup_ms, filler_played, filler_key, main_prompt_ready_after_ms
    - Add call-level metrics: prebuilt_turn_count, filler_turn_count, live_tts_turn_count, average_time_to_first_audio_ms, average_user_stop_to_agent_audio_ms
    - _Requirements: 13.1, 13.2, 13.3, 13.4_
  
  - [x] 10.2 Add error logging for asset failures
    - Log errors when asset lookup fails
    - Log errors when audio file streaming fails
    - Log fallback events with error details
    - _Requirements: 13.5, 20.1, 20.2, 20.3, 20.4, 20.5_

- [x] 11. Add asset versioning and cleanup
  - [x] 11.1 Implement version increment logic
    - Modify PromptAudioService.ensure_prompt_audio to check for existing template_key
    - If text or synthesis config changes, increment version and create new asset
    - Update RuntimeSelectionLayer to select highest version with status=ready
    - _Requirements: 12.1, 12.2, 12.3, 12.4_
  
  - [x] 11.2 Create management command for version cleanup
    - Create `backend/app/management/commands/purge_old_audio_versions.py`
    - Accept --retention-days parameter (default 30)
    - Query assets older than retention period with version < max_version
    - Delete old asset records and files
    - Report purged count
    - _Requirements: 12.5, 12.6_

- [x] 12. Final checkpoint - Integration testing and validation
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The implementation uses Python with async/await patterns throughout
- Audio format is raw linear16 PCM (8kHz, no WAV container) with .pcm extension
- Pace is set to 1.2 to match current runtime configuration (SARVAM_TTS_PACE=1.2)
- Composite unique constraint (template_key, version) allows versioning without breaking existing calls
- All audio source routing decisions are logged for observability
- Graceful degradation: always fall back to live TTS on errors

## Task Dependency Graph

```json
{
  "waves": [
    {
      "id": 0,
      "tasks": ["1.1", "1.2"]
    },
    {
      "id": 1,
      "tasks": ["1.3"]
    },
    {
      "id": 2,
      "tasks": ["2.1", "4.1", "5.1", "8.2"]
    },
    {
      "id": 3,
      "tasks": ["2.2", "2.4", "4.2", "5.2"]
    },
    {
      "id": 4,
      "tasks": ["2.3", "2.5", "2.6", "4.3", "5.3"]
    },
    {
      "id": 5,
      "tasks": ["4.4"]
    },
    {
      "id": 6,
      "tasks": ["6.1", "8.1"]
    },
    {
      "id": 7,
      "tasks": ["6.2"]
    },
    {
      "id": 8,
      "tasks": ["6.3", "6.4"]
    },
    {
      "id": 9,
      "tasks": ["9.1", "10.1"]
    },
    {
      "id": 10,
      "tasks": ["9.2", "9.3", "10.2", "11.1"]
    },
    {
      "id": 11,
      "tasks": ["11.2"]
    }
  ]
}
```
