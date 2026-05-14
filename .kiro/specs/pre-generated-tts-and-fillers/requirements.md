# Requirements Document

## Introduction

This document defines requirements for implementing a pre-generated TTS and filler audio system to reduce live-call latency in the RecruiteAI voice interview platform. The current system synthesizes every recruiter prompt live via Sarvam TTS, creating noticeable latency gaps during calls. This feature introduces a hybrid architecture that pre-generates audio for stable prompts (consent opener, interview questions, reprompts, clarifications, closers) while maintaining dynamic TTS as a fallback for truly dynamic turns. The system will also support optional short filler clips to mask compute gaps, improving the perceived responsiveness of the voice agent without sacrificing conversational flexibility.

## Glossary

- **Audio_Asset**: A pre-generated audio file stored with metadata for reuse during live calls
- **Audio_Prompt_Library**: The database-backed collection of all Audio_Assets with associated metadata
- **Prompt_Audio_Service**: The backend service responsible for synthesizing, persisting, and retrieving Audio_Assets
- **Runtime_Selection_Layer**: The component that classifies assistant turns and routes them to cached audio or live TTS
- **Filler_Audio**: A short pre-generated utterance (e.g., "understood", "got it") used to mask compute gaps
- **Template_Key**: A unique identifier for a reusable prompt template (e.g., "opener_consent", "reprompt_clarify")
- **Sarvam_TTS**: The live text-to-speech synthesis service used for dynamic turns
- **Deepgram_Runtime**: The backend service managing the Exotel websocket, STT, and audio playback
- **Question_Asset**: An Audio_Asset specifically tied to a job's interview question
- **Asset_Hash**: A deterministic hash derived from normalized prompt text and synthesis configuration
- **Prompt_Category**: A classification of prompt type (opener, question, reprompt, clarification, off_topic_redirect, closing, filler, fallback_dynamic)
- **Job_Prompt_Generation**: The process of creating Audio_Assets for all questions in a job
- **Barge_In**: User speech that interrupts agent audio playback
- **Audio_Source_Type**: The origin of played audio (prebuilt_asset, filler_asset, live_tts, live_tts_fallback)

## Requirements

### Requirement 1: Audio Prompt Library Storage

**User Story:** As a system administrator, I want a persistent storage system for pre-generated audio prompts, so that the runtime can retrieve and play them without live synthesis.

#### Acceptance Criteria

1. THE Audio_Prompt_Library SHALL store Audio_Asset metadata in a database table with fields: id, template_key, category, text, job_id (nullable), question_id (nullable), provider, speaker, language_code, sample_rate, codec, pace, file_path, file_hash, duration_ms, version, status, last_generated_at, created_at, updated_at
2. THE Audio_Prompt_Library SHALL enforce a composite unique constraint on (template_key, version) to allow multiple versions of the same template
3. THE Audio_Prompt_Library SHALL store Audio_Asset files using the existing storage abstraction with path pattern `prompt-audio/{category}/{version}/{hash}.pcm`
4. WHEN an Audio_Asset is created, THE Audio_Prompt_Library SHALL compute an Asset_Hash from normalized prompt text and synthesis configuration
5. THE Audio_Prompt_Library SHALL support status values: pending, ready, failed
6. THE Audio_Prompt_Library SHALL allow lookup by template_key, job_id, question_id, and Asset_Hash

### Requirement 2: Prompt Audio Generation Service

**User Story:** As a developer, I want a service that generates and persists prompt audio, so that the system can build a reusable audio library.

#### Acceptance Criteria

1. THE Prompt_Audio_Service SHALL normalize prompt text before synthesis
2. WHEN an Audio_Asset is requested, THE Prompt_Audio_Service SHALL check if a ready asset exists with matching Asset_Hash
3. IF a ready asset exists, THEN THE Prompt_Audio_Service SHALL return the existing asset without regeneration
4. IF no ready asset exists, THEN THE Prompt_Audio_Service SHALL synthesize audio using Sarvam_TTS with configured speaker, language_code, and pace
5. WHEN synthesis completes successfully, THE Prompt_Audio_Service SHALL persist the audio file and update metadata status to ready
6. WHEN synthesis fails, THE Prompt_Audio_Service SHALL update metadata status to failed and log the error
7. THE Prompt_Audio_Service SHALL expose methods: ensure_prompt_audio, ensure_question_audio_for_job, ensure_default_fillers, get_ready_audio_asset

### Requirement 3: Job-Level Question Audio Generation

**User Story:** As a recruiter, I want interview question audio to be pre-generated when I finalize job questions, so that live calls start faster without synthesis delays.

#### Acceptance Criteria

1. WHEN job questions are created or updated, THE system SHALL trigger Job_Prompt_Generation asynchronously
2. THE Job_Prompt_Generation SHALL iterate all questions for the job
3. FOR EACH question, THE Job_Prompt_Generation SHALL generate prompt text and invoke Prompt_Audio_Service to create a Question_Asset
4. WHEN all Question_Assets are ready, THE Job_Prompt_Generation SHALL mark the generation run as complete
5. THE Job_Prompt_Generation SHALL record success_count and failure_count for observability
6. IF generation fails for any question, THEN THE Job_Prompt_Generation SHALL log the error and continue processing remaining questions

### Requirement 4: Default Filler Audio Library

**User Story:** As a system administrator, I want a curated set of short filler utterances, so that the runtime can mask compute gaps without generating fillers on demand.

#### Acceptance Criteria

1. THE system SHALL provide a management command to generate default Filler_Audio assets
2. THE default Filler_Audio set SHALL include: understood, got_it, okay, thanks, sure, one_moment
3. WHEN the generation command runs, THE Prompt_Audio_Service SHALL create Filler_Audio assets with category=filler and job_id=null
4. THE Filler_Audio assets SHALL be reusable across all jobs
5. EACH Filler_Audio SHALL be a single short phrase with duration less than 2 seconds

### Requirement 5: Runtime Prompt Selection and Routing

**User Story:** As a voice agent, I want to automatically select pre-generated audio when available, so that I can respond faster than live synthesis allows.

#### Acceptance Criteria

1. WHEN an assistant turn is ready, THE Runtime_Selection_Layer SHALL classify the turn by Prompt_Category
2. IF the turn matches a Template_Key with a ready Audio_Asset, THEN THE Runtime_Selection_Layer SHALL route to cached audio playback
3. IF no ready Audio_Asset exists, THEN THE Runtime_Selection_Layer SHALL route to Sarvam_TTS fallback
4. THE Runtime_Selection_Layer SHALL support classification for categories: opener, question, reprompt, clarification, off_topic_redirect, closing, filler, fallback_dynamic
5. WHEN a Question_Asset is selected, THE Runtime_Selection_Layer SHALL resolve it by job_id and question_id
6. THE Runtime_Selection_Layer SHALL log the Audio_Source_Type for every turn (prebuilt_asset, filler_asset, live_tts, live_tts_fallback)

### Requirement 6: Filler Audio Queueing Logic

**User Story:** As a voice agent, I want to play short fillers only when necessary, so that I mask awkward silence without creating verbal spam or overlapping speech.

#### Acceptance Criteria

1. WHEN a candidate finishes speaking, THE Runtime_Selection_Layer SHALL estimate the latency until the next agent turn is ready
2. IF estimated latency exceeds 300ms AND no Audio_Asset is ready, THEN THE Runtime_Selection_Layer SHALL select a Filler_Audio to play
3. IF the main prompt becomes ready while Filler_Audio is playing, THEN THE Runtime_Selection_Layer SHALL cancel Filler_Audio playback and immediately play the main prompt
4. IF the main prompt is ready within 300ms, THEN THE Runtime_Selection_Layer SHALL skip Filler_Audio and play the main prompt immediately
5. WHEN Filler_Audio is playing, THE Runtime_Selection_Layer SHALL allow Barge_In interruption
6. THE Runtime_Selection_Layer SHALL log filler_played=true/false and filler_key for observability

### Requirement 7: Cached Audio Playback Integration

**User Story:** As a developer, I want cached audio to stream through the existing Exotel playback path, so that pre-generated audio behaves identically to live TTS from the caller's perspective.

#### Acceptance Criteria

1. WHEN an Audio_Asset is selected for playback, THE Deepgram_Runtime SHALL stream the audio file to Exotel
2. THE Deepgram_Runtime SHALL support the same audio format and sample rate as Sarvam_TTS output
3. THE Deepgram_Runtime SHALL allow Barge_In interruption for cached audio playback
4. THE Deepgram_Runtime SHALL log asset_id and asset_lookup_ms for performance tracking
5. IF audio file streaming fails, THEN THE Deepgram_Runtime SHALL fall back to Sarvam_TTS and log the failure

### Requirement 8: Live TTS Fallback Preservation

**User Story:** As a developer, I want live Sarvam TTS to remain available as a fallback, so that the system handles dynamic turns and missing assets gracefully.

#### Acceptance Criteria

1. THE system SHALL preserve the existing Sarvam_TTS integration
2. WHEN no Audio_Asset matches the assistant turn, THE Runtime_Selection_Layer SHALL route to Sarvam_TTS
3. WHEN an Audio_Asset lookup fails or returns status=failed, THEN THE Runtime_Selection_Layer SHALL route to Sarvam_TTS
4. THE Runtime_Selection_Layer SHALL log Audio_Source_Type=live_tts_fallback when fallback is used
5. THE system SHALL support dynamic turns that incorporate novel transcript content via Sarvam_TTS

### Requirement 9: Opener Audio Generation and Playback

**User Story:** As a recruiter, I want the consent opener to play instantly at call start, so that candidates experience no delay before the first agent utterance.

#### Acceptance Criteria

1. THE system SHALL provide a standard opener template with Template_Key=opener_consent
2. THE opener template SHALL use static non-personalized text: "Hello! I'm calling from the recruitment team. I'd like to ask you a few questions about your application. This call will be recorded for quality purposes. Do you have a few minutes to talk?"
3. WHEN the opener template is defined, THE Prompt_Audio_Service SHALL generate an Audio_Asset with category=opener
4. WHEN a call starts and consent has not been granted, THE Runtime_Selection_Layer SHALL select the opener Audio_Asset
5. THE Runtime_Selection_Layer SHALL play the opener Audio_Asset without invoking Sarvam_TTS
6. IF the opener Audio_Asset is missing or failed, THEN THE Runtime_Selection_Layer SHALL fall back to Sarvam_TTS
7. IF personalized opener text is required (e.g., including candidate name), THEN THE Runtime_Selection_Layer SHALL use Sarvam_TTS fallback instead of cached audio

**Note:** Phase 1 uses static non-personalized opener for instant playback. Future enhancement may support stitched audio segments for personalized greetings.

### Requirement 10: Reprompt and Clarification Audio

**User Story:** As a voice agent, I want standard reprompts and clarifications to play from cached audio, so that recovery turns are fast and consistent.

#### Acceptance Criteria

1. THE system SHALL define standard reprompt templates with Template_Keys: reprompt_clarify, reprompt_elaborate, reprompt_example, reprompt_off_topic
2. WHEN reprompt templates are defined, THE Prompt_Audio_Service SHALL generate Audio_Assets with category=reprompt
3. WHEN an assistant turn matches a reprompt template, THE Runtime_Selection_Layer SHALL select the corresponding Audio_Asset
4. THE system SHALL define standard clarification templates with Template_Keys: clarification_more, clarification_repeat
5. WHEN clarification templates are defined, THE Prompt_Audio_Service SHALL generate Audio_Assets with category=clarification

### Requirement 11: Closing Audio

**User Story:** As a recruiter, I want the call closing to play from cached audio, so that the final impression is fast and polished.

#### Acceptance Criteria

1. THE system SHALL define standard closing templates with Template_Keys: closing_thank_you, closing_next_steps
2. WHEN closing templates are defined, THE Prompt_Audio_Service SHALL generate Audio_Assets with category=closing
3. WHEN the call reaches the closing phase, THE Runtime_Selection_Layer SHALL select the appropriate closing Audio_Asset
4. THE Runtime_Selection_Layer SHALL play the closing Audio_Asset without invoking Sarvam_TTS
5. IF the closing Audio_Asset is missing or failed, THEN THE Runtime_Selection_Layer SHALL fall back to Sarvam_TTS

### Requirement 12: Audio Asset Versioning

**User Story:** As a developer, I want audio assets to be versioned, so that prompt text changes trigger regeneration without breaking existing calls.

#### Acceptance Criteria

1. THE Audio_Prompt_Library SHALL store a version field for each Audio_Asset
2. WHEN prompt text or synthesis configuration changes, THE Prompt_Audio_Service SHALL increment the version and generate a new Audio_Asset
3. THE Runtime_Selection_Layer SHALL select the highest version Audio_Asset with status=ready for a given template_key
4. WHEN multiple versions exist for the same template_key, THE Runtime_Selection_Layer SHALL use the version field to select the most recent ready asset
5. THE system SHALL retain previous versions for a configurable retention period
6. THE system SHALL provide a management command to purge old versions

### Requirement 13: Observability and Metrics

**User Story:** As a developer, I want detailed logs and metrics for audio source usage, so that I can measure latency improvements and debug routing issues.

#### Acceptance Criteria

1. THE Runtime_Selection_Layer SHALL log structured events with fields: audio_source, template_key, asset_id, asset_lookup_ms, filler_played, filler_key, main_prompt_ready_after_ms
2. THE system SHALL track call-level metrics: prebuilt_turn_count, filler_turn_count, live_tts_turn_count, average_time_to_first_audio_ms, average_user_stop_to_agent_audio_ms
3. THE system SHALL log Audio_Source_Type for every agent turn
4. THE system SHALL expose metrics via the existing observability service
5. THE system SHALL log errors when Audio_Asset lookup fails or streaming fails

### Requirement 14: Asset Generation Management Command

**User Story:** As a system administrator, I want a management command to generate audio assets on demand, so that I can populate the library without manual intervention.

#### Acceptance Criteria

1. THE system SHALL provide a management command: generate_prompt_audio
2. THE generate_prompt_audio command SHALL accept parameters: category, template_key, job_id (optional)
3. WHEN generate_prompt_audio runs with category=filler, THE command SHALL generate all default Filler_Audio assets
4. WHEN generate_prompt_audio runs with job_id, THE command SHALL generate all Question_Assets for that job
5. THE generate_prompt_audio command SHALL report success_count and failure_count

### Requirement 15: Question Text Stability

**User Story:** As a recruiter, I want question audio to remain synchronized with question text, so that candidates hear exactly what I configured.

#### Acceptance Criteria

1. WHEN a question's text is updated, THE system SHALL mark the existing Question_Asset as stale
2. THE system SHALL trigger regeneration of the Question_Asset with the new text
3. THE Runtime_Selection_Layer SHALL not use a Question_Asset if its text does not match the current question text
4. THE system SHALL log a warning when a Question_Asset is stale
5. THE system SHALL fall back to Sarvam_TTS if the Question_Asset is stale or missing

### Requirement 16: Audio Format Consistency

**User Story:** As a developer, I want all Audio_Assets to use consistent format and quality settings, so that playback is seamless across cached and live audio.

#### Acceptance Criteria

1. THE Prompt_Audio_Service SHALL generate Audio_Assets with sample_rate=8000 Hz (matching Exotel telephony)
2. THE Prompt_Audio_Service SHALL generate Audio_Assets with codec=linear16 (raw PCM format, no WAV container)
3. THE Prompt_Audio_Service SHALL store Audio_Assets as raw linear16 PCM bytes with .pcm file extension
4. THE Prompt_Audio_Service SHALL use speaker=priya and language_code=en-IN for all assets (matching Sarvam_TTS defaults)
5. THE Prompt_Audio_Service SHALL use pace=1.2 (matching SARVAM_TTS_PACE=1.2 from runtime configuration) unless explicitly configured otherwise
6. THE cached Audio_Assets SHALL use the same format as Sarvam TTS output (linear16 PCM) to ensure seamless playback
7. THE Audio_Prompt_Library SHALL store sample_rate, codec, speaker, language_code, and pace in metadata for every Audio_Asset

### Requirement 17: Deterministic Asset Hashing

**User Story:** As a developer, I want asset hashing to be deterministic, so that identical prompts reuse the same audio file without duplication.

#### Acceptance Criteria

1. THE Prompt_Audio_Service SHALL normalize prompt text by removing extra whitespace and converting to lowercase before hashing
2. THE Prompt_Audio_Service SHALL compute Asset_Hash from normalized text, speaker, language_code, pace, and provider
3. THE Prompt_Audio_Service SHALL use a cryptographic hash function (e.g., SHA-256) for Asset_Hash
4. WHEN two prompts have identical normalized text and synthesis configuration, THE Prompt_Audio_Service SHALL generate the same Asset_Hash
5. THE Audio_Prompt_Library SHALL prevent duplicate Audio_Assets with the same Asset_Hash and status=ready

### Requirement 18: Asynchronous Generation

**User Story:** As a recruiter, I want audio generation to happen in the background, so that job setup does not block while assets are being created.

#### Acceptance Criteria

1. WHEN Job_Prompt_Generation is triggered, THE system SHALL execute generation asynchronously after the database commit
2. THE system SHALL not block the HTTP response while generation is in progress
3. THE system SHALL update Audio_Asset status from pending to ready as each asset completes
4. THE system SHALL allow calls to proceed using Sarvam_TTS fallback if Audio_Assets are still pending
5. THE system SHALL log generation progress for monitoring

### Requirement 19: Barge-In Compatibility

**User Story:** As a candidate, I want to interrupt the agent at any time, so that I can correct misunderstandings or provide additional information naturally.

#### Acceptance Criteria

1. WHEN a candidate speaks during Audio_Asset playback, THE Deepgram_Runtime SHALL detect the speech via STT
2. THE Deepgram_Runtime SHALL stop Audio_Asset playback immediately upon detecting candidate speech
3. THE Deepgram_Runtime SHALL stop Filler_Audio playback immediately upon detecting candidate speech
4. THE system SHALL preserve the same Barge_In behavior for cached audio as for Sarvam_TTS
5. THE system SHALL log barge_in_event=true when playback is interrupted

### Requirement 20: Error Handling and Resilience

**User Story:** As a developer, I want the system to handle asset generation and playback failures gracefully, so that calls continue even when the audio library has issues.

#### Acceptance Criteria

1. WHEN Prompt_Audio_Service synthesis fails, THE service SHALL log the error and set Audio_Asset status=failed
2. WHEN Audio_Asset lookup fails, THE Runtime_Selection_Layer SHALL fall back to Sarvam_TTS
3. WHEN Audio_Asset file streaming fails, THE Deepgram_Runtime SHALL fall back to Sarvam_TTS
4. THE system SHALL not crash or hang when the Audio_Prompt_Library is unavailable
5. THE system SHALL log all fallback events with error details for debugging
