import { useCallback, useEffect, useRef, useState } from "react";
import { getApiOrigin } from "@/lib/api";

/**
 * Progress event received from the SSE stream
 */
export interface ProgressEvent {
  event_type: string;
  session_id: string;
  resume_index: number;
  total_resumes: number;
  filename: string;
  timestamp: string;
  candidate_name?: string;
  email?: string;
  phone_number?: string;
  matching_score?: number;
  error_message?: string;
  failed_stage?: string;
  resume_id?: string;
}

/**
 * Resume progress state tracked by the hook
 */
export interface ResumeProgress {
  filename: string;
  status: "pending" | "starting" | "uploading" | "parsing" | "evaluating" | "completed" | "error";
  candidateName?: string;
  email?: string;
  phoneNumber?: string;
  matchingScore?: number;
  errorMessage?: string;
  resumeId?: string;
}

/**
 * Return type for the useResumeProgressStream hook
 */
interface UseResumeProgressStreamResult {
  resumes: ResumeProgress[];
  isConnected: boolean;
  isComplete: boolean;
  error: string | null;
}

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

/**
 * Calculate exponential backoff delay with jitter
 */
function backoffDelay(attempt: number): number {
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * Math.pow(2, attempt));
  return Math.random() * exponential;
}

/**
 * Custom React hook for managing SSE connection to resume processing progress stream.
 * 
 * Features:
 * - Establishes EventSource connection with session_id
 * - Handles connection open, error, and close events
 * - Listens for event types: starting, uploading, parsing, evaluating, completed, error, all_completed
 * - Updates resume state array based on received events
 * - Tracks connection status (isConnected, isComplete, error)
 * - Implements automatic reconnection on connection loss with exponential backoff
 * - Cleans up EventSource on unmount
 * 
 * @param jobId - The job ID for which resumes are being processed
 * @param sessionId - The session ID returned from the upload endpoint
 * @returns Object containing resumes array, connection state, completion state, and error
 */
export function useResumeProgressStream(
  jobId: string | undefined,
  sessionId: string | null
): UseResumeProgressStreamResult {
  const [resumes, setResumes] = useState<ResumeProgress[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const isCompleteRef = useRef(false);

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.onopen = null;
      eventSourceRef.current.onerror = null;
      eventSourceRef.current.onmessage = null;
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId || !sessionId) {
      return;
    }

    retryCountRef.current = 0;
    isCompleteRef.current = false;

    function connect() {
      cleanup();

      if (isCompleteRef.current) {
        return;
      }

      setIsConnected(false);
      setError(null);

      const token = localStorage.getItem("accessToken");
      const apiOrigin = getApiOrigin();
      
      // EventSource doesn't support custom headers, so we pass token as query param
      const url = `${apiOrigin}/api/jobs/${jobId}/resumes/stream?session_id=${sessionId}&token=${token}`;
      
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        retryCountRef.current = 0; // Reset on successful connection
        setIsConnected(true);
        setError(null);
      };

      eventSource.onerror = () => {
        setIsConnected(false);
        
        // If already complete, don't reconnect
        if (isCompleteRef.current) {
          eventSource.close();
          return;
        }

        // Exceeded retry budget — give up
        if (retryCountRef.current >= MAX_RETRIES) {
          setError("Connection failed after multiple retries");
          eventSource.close();
          return;
        }

        // Schedule a reconnect with backoff
        setError("Connection lost. Retrying...");
        const delay = backoffDelay(retryCountRef.current);
        retryCountRef.current += 1;
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, delay);
      };

      // Handle different event types
      const eventTypes = [
        "starting",
        "uploading",
        "parsing",
        "evaluating",
        "completed",
        "error",
        "all_completed",
      ];

      eventTypes.forEach((eventType) => {
        eventSource.addEventListener(eventType, (e: Event) => {
          const messageEvent = e as MessageEvent;
          const data: ProgressEvent = JSON.parse(messageEvent.data);

          if (eventType === "all_completed") {
            isCompleteRef.current = true;
            setIsComplete(true);
            setIsConnected(false);
            eventSource.close();
            return;
          }

          setResumes((prev) => {
            const updated = [...prev];
            const index = data.resume_index;

            // Initialize if needed
            if (!updated[index]) {
              updated[index] = {
                filename: data.filename,
                status: "pending",
              };
            }

            // Update status
            updated[index].status = eventType as ResumeProgress["status"];
            updated[index].filename = data.filename;

            // Add completion data
            if (eventType === "completed") {
              updated[index].candidateName = data.candidate_name;
              updated[index].email = data.email;
              updated[index].phoneNumber = data.phone_number;
              updated[index].matchingScore = data.matching_score;
              updated[index].resumeId = data.resume_id;
            }

            // Add error data
            if (eventType === "error") {
              updated[index].errorMessage = data.error_message;
            }

            return updated;
          });
        });
      });
    }

    connect();

    return cleanup;
  }, [jobId, sessionId, cleanup]);

  return {
    resumes,
    isConnected,
    isComplete,
    error,
  };
}
