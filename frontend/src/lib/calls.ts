export type CallStatus =
  | "pending"
  | "queued"
  | "ringing"
  | "in_progress"
  | "completed"
  | "failed"
  | "no_answer";

export interface CallRecord {
  id: string;
  resume_id: string;
  job_id: string;
  twilio_call_sid: string | null;
  status: CallStatus;
  phone_number: string;
  duration_seconds: number | null;
  recording_url: string | null;
  recording_path: string | null;
  transcript: string | null;
  ai_evaluation: {
    overall_score?: number;
    recommendation?: string;
    [key: string]: unknown;
  } | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export const ACTIVE_CALL_STATUSES: CallStatus[] = [
  "pending",
  "queued",
  "ringing",
  "in_progress",
];
