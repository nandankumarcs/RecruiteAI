import { useCallback, useEffect, useRef, useState } from "react";
import { getWebSocketBaseUrl } from "@/lib/api";
import type { CallRecord } from "@/lib/calls";

const TERMINAL_STATUSES = new Set(["completed", "failed", "no_answer"]);
const MAX_RETRIES = 8;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

function backoffDelay(attempt: number): number {
  // Exponential backoff with full jitter: random(0, min(cap, base * 2^attempt))
  const exponential = Math.min(MAX_DELAY_MS, BASE_DELAY_MS * Math.pow(2, attempt));
  return Math.random() * exponential;
}

export function useCallWebSocket(callId: string | undefined, onUpdate?: (call: CallRecord) => void) {
  const [connectionState, setConnectionState] = useState<"connecting" | "live" | "closed">("closed");
  const [lastCall, setLastCall] = useState<CallRecord | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onUpdateRef = useRef(onUpdate);
  const retryCountRef = useRef(0);
  const isTerminalRef = useRef(false);

  useEffect(() => {
    onUpdateRef.current = onUpdate;
  }, [onUpdate]);

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (socketRef.current) {
      socketRef.current.onclose = null; // Prevent reconnect logic from firing
      socketRef.current.close();
      socketRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!callId) return;

    retryCountRef.current = 0;
    isTerminalRef.current = false;

    function connect() {
      cleanup();

      if (isTerminalRef.current) return;

      setConnectionState("connecting");
      const socket = new WebSocket(`${getWebSocketBaseUrl()}/ws/calls/${callId}`);
      socketRef.current = socket;

      socket.onopen = () => {
        retryCountRef.current = 0; // Reset on successful connection
        setConnectionState("live");
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data as string);
          if (payload.type === "call_update" && payload.call) {
            const call = payload.call as CallRecord;
            setLastCall(call);
            onUpdateRef.current?.(call);

            // Gracefully close when the call reaches a terminal status
            if (TERMINAL_STATUSES.has(call.status)) {
              isTerminalRef.current = true;
              socket.close(1000, "call_complete");
            }
          } else if (payload.type === "not_found") {
            isTerminalRef.current = true;
            socket.close(4404, "not_found");
          }
        } catch (err) {
          console.error("Failed to parse websocket message", err);
        }
      };

      socket.onclose = (event) => {
        socketRef.current = null;

        // Clean close or terminal call — do not reconnect
        if (event.code === 1000 || event.code === 1001 || isTerminalRef.current) {
          setConnectionState("closed");
          return;
        }

        // Exceeded retry budget — give up
        if (retryCountRef.current >= MAX_RETRIES) {
          setConnectionState("closed");
          return;
        }

        // Schedule a reconnect with backoff
        setConnectionState("connecting");
        const delay = backoffDelay(retryCountRef.current);
        retryCountRef.current += 1;
        reconnectTimeoutRef.current = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        // onclose fires immediately after onerror; let it handle retry logic
        socket.close();
      };
    }

    connect();

    return cleanup;
  }, [callId, cleanup]);

  return { connectionState, lastCall };
}
