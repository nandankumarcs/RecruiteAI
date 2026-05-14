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
  provider: string;
  voice_runtime: string;
  provider_call_id: string | null;
  twilio_call_sid: string | null;
  status: CallStatus;
  phone_number: string;
  duration_seconds: number | null;
  recording_url: string | null;
  recording_path: string | null;
  transcript: string | null;
  ai_evaluation: {
    schema_version?: string;
    status?: string;
    confidence?: string;
    overall_score?: number | null;
    technical_score?: number | null;
    communication_score?: number | null;
    experience_score?: number | null;
    behavioral_score?: number | null;
    behavioral_summary?: string | null;
    remarks?: string;
    strengths?: string[];
    weaknesses?: string[];
    recommendation?: string;
    [key: string]: unknown;
  } | null;
  cost_breakdown: {
    estimated_total_usd?: number;
    costs?: Record<string, number>;
    [key: string]: unknown;
  } | null;
  latency_metrics: Record<string, unknown> | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  messages?: Array<{
    id: string;
    role: string;
    content: string;
    sequence_number: number;
    created_at: string;
  }>;
}

export const ACTIVE_CALL_STATUSES: CallStatus[] = [
  "pending",
  "queued",
  "ringing",
  "in_progress",
];
