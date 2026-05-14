# Post-Call Evaluation Patch Plan

Date: 2026-05-14

## Scope

Review and harden the post-call evaluation pipeline so it does not generate misleading candidate assessments from:

- opener-only calls
- incomplete or low-signal transcripts
- disengaged / aborted interviews
- transcripts degraded by STT or turn-taking failures

This plan is based on manual inspection of the recent calls listed below, including transcript content, stored `ai_evaluation`, and persisted call metadata.

## Non-Goals

This patch is intentionally scoped to the post-call evaluation layer only.

It should not be used to fix or redesign:

- live call turn-taking
- STT provider quality
- TTS timing
- interruption / barge-in behavior
- telephony disconnects
- transcript generation itself

Those runtime issues matter, and they influence evaluation quality, but they should be handled in a separate call-pipeline track. The goal here is narrower:

- make the evaluator respond appropriately to the transcript it receives
- avoid fabricated certainty
- represent uncertainty and incompleteness honestly

## Design Principles

To avoid brittle logic, the patch should follow these principles:

1. Prefer evidence-aware evaluation states over hard-coded transcript pattern matching.
2. Use lightweight readiness and transcript-health signals as guards, not as a giant rule engine.
3. Let the evaluation agent express uncertainty explicitly instead of forcing numeric judgment in every case.
4. Normalize output shape and enums at the schema layer so the frontend and analytics are stable.
5. Keep runtime-quality diagnosis separate from runtime-quality repair.

## Calls Reviewed

The following recent calls were inspected:

- `5931cbe1-d45b-4c67-992f-10adf4a18c9c`
- `38b67742-a6f0-49db-a4b7-be0af8b7f1a6`
- `4157db0d-c250-4853-aa40-a25db007d647`
- `c0e65210-35c3-431e-99b0-9883b6ddfe3d`
- `ba482b83-aeea-4e73-bb5e-ef541834fecc`
- `3de56c50-a528-4d46-8201-fc4c6f307e62`
- `5b95d759-5acc-4907-9832-f9e070f99c1c`
- `6d428e03-224f-4132-8150-7c516a41ceb7`
- `68b6f8be-5cb0-4172-b2ff-8adec215c57c`
- `882c5e48-022d-4700-9cb0-84a62b5984c9`
- `591a6162-e15c-4c3c-8959-77c912cc1fb7`
- `01a770c0-74a3-40d0-9948-77e151b2ca34`
- `ad1616eb-5089-40ac-aea9-0697c3b7787c`

Additional persistence pattern checks were run on the latest 50 evaluated calls.

## Primary Findings

### 1. Opener-only calls are being scored as full interviews

This is the most severe defect.

Examples:

- `5931cbe1-d45b-4c67-992f-10adf4a18c9c`
- `3de56c50-a528-4d46-8201-fc4c6f307e62`
- `882c5e48-022d-4700-9cb0-84a62b5984c9`
- `01a770c0-74a3-40d0-9948-77e151b2ca34`

Observed pattern:

- transcript contains only the assistant opener
- `call_messages` contains only one assistant row
- no candidate answer exists
- evaluation still assigns technical / communication / experience scores
- remarks and strengths/weaknesses are hallucinated from the job title and prompt context

Current root cause:

- `auto_evaluate_call_if_ready()` only checks:
  - `status == completed`
  - `transcript` is non-empty
  - no prior evaluation exists
- it does not verify that the candidate actually spoke

## 2. Auto-evaluation does not backfill summary fields

Recent auto-evaluated calls frequently have:

- `ai_evaluation` populated
- `evaluation_score = null`
- `evaluation_summary = null`

In the latest 50 evaluated calls checked:

- `48` had `evaluation_score = null`

Current root cause:

- manual `/api/calls/{call_id}/evaluate` stores:
  - `call.ai_evaluation`
  - `call.evaluation_score`
  - `call.evaluation_summary`
- automatic evaluation stores only:
  - `call.ai_evaluation`

This creates inconsistent dashboard / detail behavior and breaks downstream summary logic.

## 3. Recommendation values are inconsistent

Observed recommendation values in recent calls:

- `hold`
- `reject`
- `do not proceed`

The frontend styles recommendation as if it were effectively an enum, but the backend schema allows any free-form string.

Problems:

- inconsistent UX labels
- inconsistent badge styling
- harder filtering/reporting
- semantically similar outcomes split across multiple strings

## 4. Low-signal / disengaged calls are being treated as technical failures

Examples:

- `c0e65210-35c3-431e-99b0-9883b6ddfe3d`
- `591a6162-e15c-4c3c-8959-77c912cc1fb7`
- `68b6f8be-5cb0-4172-b2ff-8adec215c57c`

Observed pattern:

- candidate says things like:
  - `Next question`
  - `What is this again?`
  - `Not interested`
  - `Hello?`
- little or no technical content is provided
- evaluation still frames the result as a technical/experience judgment rather than an incomplete or disengaged screening

This is directionally understandable, but the resulting score is too definitive for the evidence available.

What is missing:

- an `insufficient_data` / `abandoned` / `candidate_disengaged` evaluation mode
- explicit separation between:
  - inability to answer
  - refusal to answer
  - call quality failure
  - incomplete screening

## 5. Transcript quality issues are contaminating evaluation

Examples:

- `4157db0d-c250-4853-aa40-a25db007d647`
- `38b67742-a6f0-49db-a4b7-be0af8b7f1a6`
- `ad1616eb-5089-40ac-aea9-0697c3b7787c`

Observed transcript problems:

- user sentences cut off mid-thought
- repeated assistant question due turn-taking issues
- assistant speaks over the user
- duplicated `Assistant:` prefixes in assistant content
- answers that are clearly partial fragments still get scored as candidate inability

This means some low scores are driven partly by runtime quality defects rather than true candidate quality.

The evaluator currently has no guardrails for this.

## 6. Evaluation prompt has no "decline to score" path

The current prompt always asks for:

- `overall_score`
- `technical_score`
- `communication_score`
- `experience_score`
- `behavioral_score`
- `recommendation`

There is no allowed output state for:

- insufficient transcript
- no candidate response
- incomplete interview
- low confidence due transcript corruption

This forces the model to invent certainty.

## 7. Manual and automatic evaluation readiness rules are too weak

Current readiness check for manual evaluation:

- transcript exists

Current readiness check for auto evaluation:

- completed
- transcript exists

Neither path checks:

- candidate turn count
- minimum candidate word count
- substantive answer count
- transcript health

## Proposed Patch

### Phase 1: Add evaluation readiness gating

Add a shared readiness validator used by both:

- `auto_evaluate_call_if_ready()`
- `POST /api/calls/{call_id}/evaluate`

Create a helper such as:

- `get_call_evaluation_readiness(call, messages) -> EvaluationReadiness`

Suggested readiness checks:

1. Call must be in terminal state
2. Transcript must exist
3. At least one candidate message must exist
4. Minimum candidate word count must be met
5. Minimum substantive candidate turn count must be met
6. If transcript appears corrupted or too sparse, return a non-evaluable status

Suggested first-pass thresholds:

- `candidate_turn_count >= 2`
- `substantive_candidate_turn_count >= 1`
- `candidate_word_count >= 12`

These should be treated as coarse safety guards, not as the primary evaluation logic. They exist to block obviously non-evaluable calls, not to classify every edge case by hand.

### Phase 2: Introduce explicit non-scorable outcomes

Extend the evaluation model/schema to support a structured non-scorable state.

Recommended fields:

- `status`: one of:
  - `completed_evaluation`
  - `insufficient_data`
  - `candidate_disengaged`
  - `call_quality_issue`
- `recommendation`: normalized enum
  - `advance`
  - `hold`
  - `reject`
  - `insufficient_data`
- `confidence`: `low | medium | high`

For non-scorable cases:

- do not fabricate technical/experience scores
- allow `null` scores, or define scores as omitted when `status != completed_evaluation`

If the frontend needs stable numeric fields, show a dedicated "Not enough data to evaluate" state instead of synthetic bars.

### Phase 3: Normalize recommendation values

Restrict recommendation output to a fixed enum.

Replace free-form values like:

- `do not proceed`

with canonical values like:

- `reject`

Enforce this at the Pydantic schema layer and in prompt instructions.

### Phase 4: Persist derived evaluation summary fields consistently

When auto evaluation succeeds, also populate:

- `evaluation_score`
- `evaluation_summary`

to match the manual evaluation path.

This patch is small and should land with the readiness work.

### Phase 5: Add transcript quality heuristics

Before scoring, compute lightweight transcript health indicators:

- repeated assistant prompt count
- duplicate prefix artifacts like `Assistant: Assistant:`
- short fragment ratio in candidate turns
- interruption markers such as repeated questions after a partial candidate answer

If these exceed a threshold:

- lower evaluation confidence
- or route to `call_quality_issue`
- or block automatic evaluation and require manual re-evaluation after transcript cleanup

This prevents runtime STT/turn-taking failures from becoming candidate failures.

Important constraint:

- do not build a sprawling brittle ruleset like `if transcript contains X and Y then reject`
- keep these heuristics generic and evidence-oriented
- use them to decide whether the evaluation is trustworthy enough, not to replace the evaluation agent

### Phase 6: Improve the evaluator prompt

Revise the prompt to explicitly instruct:

- never infer experience/technical depth without transcript evidence
- do not score technical ability if the candidate never answered technical questions
- use `insufficient_data` when the interview is too short or incomplete
- use `candidate_disengaged` when the candidate declines to participate
- downgrade confidence when transcript appears fragmented or interrupted

The prompt should also prioritize candidate responses over assistant prompts and avoid deriving skills from job requirements alone.

This is the core of the patch. The main fix should come from making the evaluation agent reason better about evidence quality and incompleteness, not from bolting more call-flow logic into the evaluator path.

### Phase 7: Frontend handling for incomplete evaluations

Update UI rendering so that calls in non-scorable states show:

- `Insufficient data`
- `Candidate disengaged`
- `Call quality issue`

instead of misleading score bars.

UI updates needed in:

- call detail page
- resume detail modal
- any dashboard widgets using `evaluation_score` or `recommendation`

## Data Repair / Backfill Plan

After the patch lands, repair recent bad records.

### Backfill targets

1. Calls with `ai_evaluation` but:
   - zero user turns
   - or opener-only transcript

Action:

- clear current evaluation
- mark as `insufficient_data`
- or leave unevaluated, depending on product preference

2. Calls with `ai_evaluation` but missing:
   - `evaluation_score`
   - `evaluation_summary`

Action:

- backfill from parsed `ai_evaluation`

3. Calls with non-canonical recommendation values

Action:

- normalize to enum values

## Test Plan

### Unit tests

1. Opener-only transcript should not auto-evaluate
2. No-user-message call should not manual-evaluate
3. Candidate-disengaged transcript should return `candidate_disengaged` / `insufficient_data`
4. Valid multi-turn transcript should evaluate normally
5. Auto-evaluation should persist:
   - `ai_evaluation`
   - `evaluation_score`
   - `evaluation_summary`
6. Recommendation should always be in the allowed enum
7. Corrupted transcript artifacts should reduce confidence or block auto-score

### Integration tests

1. Completed call with only assistant opener
2. Completed call with consent + immediate hangup
3. Completed call with `next question` repeated and `not interested`
4. Completed call with real technical answers
5. Re-evaluate endpoint on insufficient transcript should return a clear validation error or structured non-scorable result

### Manual verification set

Re-run and verify behavior on:

- `5931cbe1-d45b-4c67-992f-10adf4a18c9c`
- `3de56c50-a528-4d46-8201-fc4c6f307e62`
- `882c5e48-022d-4700-9cb0-84a62b5984c9`
- `4157db0d-c250-4853-aa40-a25db007d647`
- `c0e65210-35c3-431e-99b0-9883b6ddfe3d`

## Recommended Implementation Order

1. Recommendation/status schema update
2. Prompt update for insufficient-data and low-confidence handling
3. Shared readiness gate
4. Auto-evaluation persistence parity (`evaluation_score`, `evaluation_summary`)
5. Transcript health / confidence signals
6. Frontend non-scorable state support
7. Backfill script for recent bad evaluations

## Expected Outcome

After this patch:

- opener-only calls will not receive fake interview scores
- disengaged calls will be labeled appropriately
- low-quality transcripts will no longer produce overconfident technical judgments
- evaluation metadata will be stored consistently
- recommendation values will be stable across backend and frontend
