export type JobStatus = "active" | "paused" | "closed"

export interface Job {
  id: string
  title: string
  description: string
  requirements: string | null
  status: JobStatus
  created_at: string
  updated_at: string
}
