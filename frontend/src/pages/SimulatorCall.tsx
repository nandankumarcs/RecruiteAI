import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useParams, Navigate } from "react-router-dom";
import {
  Grid3x3,
  Loader2,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  Plus,
  Users,
  Video,
  Volume2,
} from "lucide-react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Call sound effects — synthesized entirely with Web Audio API.
// No audio files, no external URLs.
// ---------------------------------------------------------------------------
function useCallSounds() {
  const ctxRef = useRef<AudioContext | null>(null);
  const ringTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const ctx = () => {
    if (!ctxRef.current || ctxRef.current.state === "closed") {
      ctxRef.current = new AudioContext();
    }
    if (ctxRef.current.state === "suspended") {
      ctxRef.current.resume().catch(() => {});
    }
    return ctxRef.current;
  };

  /** Generic tone for connect/disconnect/click sounds (ADSR envelope). */
  const tone = useCallback(
    (freq: number, dur: number, startAt: number, vol = 0.35, type: OscillatorType = "sine") => {
      const ac = ctx();
      const osc = ac.createOscillator();
      const gain = ac.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, startAt);
      gain.gain.setValueAtTime(0, startAt);
      gain.gain.linearRampToValueAtTime(vol, startAt + 0.012);
      gain.gain.setValueAtTime(vol, startAt + dur - 0.015);
      gain.gain.linearRampToValueAtTime(0, startAt + dur);
      osc.connect(gain);
      gain.connect(ac.destination);
      osc.start(startAt);
      osc.stop(startAt + dur);
    },
    [],
  );

  /**
   * Marimba bar hit — the characteristic "woody" percussive sound.
   *
   * Real marimba bars produce a non-harmonic 2nd partial ≈ 3.93× the fundamental
   * (a raised major 10th), which is what separates them from a pure sine tone.
   * We blend the fundamental + that partial at ~14% volume, with an exponential
   * decay envelope (fast attack, 450ms decay), matching the struck-wood character.
   */
  const marimbaNote = useCallback(
    (freq: number, startAt: number, vol = 0.55, decay = 0.45) => {
      const ac = ctx();
      // Fundamental
      const osc1 = ac.createOscillator();
      const g1   = ac.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(freq, startAt);
      g1.gain.setValueAtTime(0, startAt);
      g1.gain.linearRampToValueAtTime(vol, startAt + 0.004);
      g1.gain.exponentialRampToValueAtTime(0.0005, startAt + decay);
      osc1.connect(g1); g1.connect(ac.destination);
      osc1.start(startAt); osc1.stop(startAt + decay + 0.02);

      // Non-harmonic 2nd partial (≈3.93× — raised major 10th, the marimba "woody" overtone)
      const osc2 = ac.createOscillator();
      const g2   = ac.createGain();
      osc2.type = "sine";
      osc2.frequency.setValueAtTime(freq * 3.93, startAt);
      g2.gain.setValueAtTime(0, startAt);
      g2.gain.linearRampToValueAtTime(vol * 0.14, startAt + 0.003);
      g2.gain.exponentialRampToValueAtTime(0.0005, startAt + decay * 0.5);
      osc2.connect(g2); g2.connect(ac.destination);
      osc2.start(startAt); osc2.stop(startAt + decay * 0.55);
    },
    [],
  );

  /**
   * iPhone "Marimba" / "Opening" ringtone pattern.
   *
   * The iconic 4-note phrase: A5 → E5 → D5 → A4, with the rhythm and spacing
   * of the original (2007 iPhone default ringtone).
   * One full phrase is ≈1.4s; the loop fires every 3.2s, matching Apple's cadence.
   */
  const ringBurst = useCallback(() => {
    const ac  = ctx();
    const now = ac.currentTime;
    //       freq   offset  vol   decay
    marimbaNote(880,  now + 0.00, 0.60, 0.50);  // A5 — downbeat, strong
    marimbaNote(659,  now + 0.34, 0.45, 0.35);  // E5 — quick passing note
    marimbaNote(587,  now + 0.54, 0.45, 0.35);  // D5 — quick passing note
    marimbaNote(440,  now + 0.76, 0.52, 0.55);  // A4 — resolution
    // Vibration synced to the phrase start
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate([500, 200, 500]);
    }
  }, [marimbaNote]);

  const startRinging = useCallback(() => {
    ringBurst();
    ringTimerRef.current = setInterval(ringBurst, 3200);
  }, [ringBurst]);

  const stopRinging = useCallback(() => {
    if (ringTimerRef.current) {
      clearInterval(ringTimerRef.current);
      ringTimerRef.current = null;
    }
    // Stop vibration
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate(0);
    }
  }, []);

  /** Two ascending beeps — the "call connected" cue. */
  const playConnect = useCallback(() => {
    const ac = ctx();
    const now = ac.currentTime;
    tone(880,  0.14, now,       0.28);
    tone(1320, 0.16, now + 0.14, 0.28);
  }, [tone]);

  /** Three descending beeps — the "call ended" cue. */
  const playDisconnect = useCallback(() => {
    const ac = ctx();
    const now = ac.currentTime;
    tone(660, 0.12, now,       0.22);
    tone(550, 0.12, now + 0.13, 0.22);
    tone(440, 0.18, now + 0.26, 0.22);
  }, [tone]);

  /** Soft single beep for mute toggle feedback. */
  const playClick = useCallback(() => {
    const ac = ctx();
    tone(1100, 0.06, ac.currentTime, 0.15);
  }, [tone]);

  useEffect(() => {
    return () => stopRinging();
  }, [stopRinging]);

  return { startRinging, stopRinging, playConnect, playDisconnect, playClick };
}

/**
 * Browser telephony simulator: candidate-side call UI.
 *
 * Speaks the Exotel media-stream protocol exactly so the production bridge runs
 * unchanged:
 *   - Outbound: capture mic → AudioWorklet downsamples to 8 kHz Int16 LE →
 *               base64-encoded {event:"media", stream_sid, media:{payload}} frames.
 *   - Inbound: same envelope coming back → decode Int16 LE → Float32 → schedule
 *              into AudioContext at 8 kHz for playback.
 *   - {event:"clear"} from the server flushes the playback queue (barge-in).
 *
 * Status webhooks: on Accept / Hangup / Decline the page POSTs to the existing
 * /webhooks/exotel/status endpoint so the simulator exercises the same status
 * callback code path as real telephony.
 */

type SimState =
  | { kind: "loading" }
  | { kind: "ringing"; token: SimToken }
  | { kind: "connecting"; token: SimToken }
  | { kind: "in_call"; token: SimToken }
  | { kind: "ended"; reason: string }
  | { kind: "error"; message: string };

interface SimToken {
  token: string;
  ws_url: string;
  call: { id: string; resume_id: string; provider_call_id: string | null; status: string };
}

const PLAYBACK_RATE = 8000;
const JITTER_BUFFER_SECONDS = 0.06; // 60 ms

// ----- base64 helpers (chunked to avoid stack overflow on large buffers) -----
function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  const CHUNK = 0x8000;
  let out = "";
  for (let i = 0; i < bytes.length; i += CHUNK) {
    out += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + CHUNK)) as any);
  }
  return btoa(out);
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const buf = new ArrayBuffer(bin.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < bin.length; i++) view[i] = bin.charCodeAt(i);
  return buf;
}

function int16LEToFloat32(buf: ArrayBuffer): Float32Array {
  const view = new DataView(buf);
  const count = Math.floor(buf.byteLength / 2);
  const out = new Float32Array(count);
  for (let i = 0; i < count; i++) {
    out[i] = view.getInt16(i * 2, true) / 0x8000;
  }
  return out;
}

export function SimulatorCall() {
  const { callId } = useParams<{ callId: string }>();
  const [state, setState] = useState<SimState>({ kind: "loading" });

  // iOS CallKit-style UI extras.
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true); // visual only — browser audio is always to speakers
  const [elapsedMs, setElapsedMs] = useState(0);
  // AI speaking indicator — true while the server is sending media frames.
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const aiSpeakTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const sounds = useCallSounds();

  // Refs persist across renders without triggering re-renders.
  const wsRef = useRef<WebSocket | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const streamSidRef = useRef<string>("");
  const callStartTimeRef = useRef<number>(0);
  const playbackCursorRef = useRef<number>(0);
  const scheduledSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  // Mirror of muted state for the AudioWorklet message handler (closes over
  // stale state otherwise). When true, the worklet's output is replaced with
  // silent frames before being sent — keeps the wire cadence at 20 ms and
  // signals "user not speaking" to OpenAI's VAD.
  const mutedRef = useRef(false);
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  // Ringtone — starts on "ringing", stops on any other state.
  useEffect(() => {
    if (state.kind === "ringing") {
      sounds.startRinging();
    } else {
      sounds.stopRinging();
    }
  }, [state.kind, sounds.startRinging, sounds.stopRinging]);

  // Screen wake lock — prevents screen dimming during active call.
  useEffect(() => {
    if (state.kind !== "in_call") return;
    let lock: WakeLockSentinel | null = null;
    (async () => {
      try {
        lock = await (navigator as any).wakeLock?.request("screen");
      } catch {
        // WakeLock not supported — silently ignore.
      }
    })();
    return () => {
      lock?.release().catch(() => {});
    };
  }, [state.kind]);

  // Browser tab title reflects call state (durationLabel updated via elapsedMs).
  useEffect(() => {
    const totalSec = Math.floor(elapsedMs / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    const label = `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    if (state.kind === "in_call") {
      document.title = `📞 ${label} — AI Interviewer | RecruiteAI`;
    } else if (state.kind === "ringing") {
      document.title = "📲 Incoming call — AI Interviewer | RecruiteAI";
    } else if (state.kind === "ended") {
      document.title = "Call ended | RecruiteAI";
    } else {
      document.title = "Simulator | RecruiteAI";
    }
    return () => { document.title = "RecruiteAI"; };
  }, [state.kind, elapsedMs]);

  // Tick a 1-Hz timer while the call is active.
  useEffect(() => {
    if (state.kind !== "in_call") {
      setElapsedMs(0);
      return;
    }
    const start = callStartTimeRef.current || Date.now();
    setElapsedMs(Date.now() - start);
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - start);
    }, 1000);
    return () => window.clearInterval(id);
  }, [state.kind]);

  const durationLabel = useMemo(() => {
    const totalSec = Math.floor(elapsedMs / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  }, [elapsedMs]);

  // ---------- Phase 1: fetch token ----------
  useEffect(() => {
    if (!callId) return;
    let cancelled = false;
    (async () => {
      try {
        const response = await api.get<SimToken>(`/sim/token/${callId}`);
        if (!cancelled) {
          setState({ kind: "ringing", token: response.data });
        }
      } catch (err: any) {
        if (cancelled) return;
        const detail =
          err?.response?.data?.detail ||
          err?.message ||
          "Could not load simulator session.";
        setState({ kind: "error", message: String(detail) });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [callId]);

  // ---------- Status transitions ----------
  // The realtime bridge handles status transitions itself:
  //   - start frame   -> _update_call_started sets status='in_progress'
  //   - WS close      -> _update_call_finished sets status='completed' + triggers eval
  // We deliberately do NOT post to /webhooks/exotel/status because that handler
  // unconditionally overwrites call.provider to 'exotel' — which would mangle
  // the simulator's `provider='browser'` value and corrupt downstream pricing
  // and recording lookups. The bridge is the single source of truth here.

  // ---------- Teardown ----------
  const teardown = useCallback(() => {
    // Stop scheduled playback first to avoid clicks.
    for (const src of scheduledSourcesRef.current) {
      try {
        src.stop();
      } catch {}
    }
    scheduledSourcesRef.current = [];
    playbackCursorRef.current = 0;

    if (workletNodeRef.current) {
      try {
        workletNodeRef.current.disconnect();
      } catch {}
      workletNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {}
      sourceNodeRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (captureCtxRef.current) {
      try {
        void captureCtxRef.current.close();
      } catch {}
      captureCtxRef.current = null;
    }
    if (playbackCtxRef.current) {
      try {
        void playbackCtxRef.current.close();
      } catch {}
      playbackCtxRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.send(JSON.stringify({ event: "stop" }));
      } catch {}
      try {
        wsRef.current.close();
      } catch {}
      wsRef.current = null;
    }
  }, []);

  // Cleanup on unmount.
  useEffect(() => {
    return () => {
      teardown();
    };
  }, [teardown]);

  // ---------- Playback scheduling ----------
  const handleMediaFrame = useCallback((b64: string) => {
    const ctx = playbackCtxRef.current;
    if (!ctx) return;
    // Mark AI as speaking; reset the idle timer every incoming frame.
    setAiSpeaking(true);
    if (aiSpeakTimeoutRef.current) clearTimeout(aiSpeakTimeoutRef.current);
    // If no new frame arrives within 400ms, AI has paused/finished.
    aiSpeakTimeoutRef.current = setTimeout(() => setAiSpeaking(false), 400);
    const bytes = base64ToArrayBuffer(b64);
    const samples = int16LEToFloat32(bytes);
    if (samples.length === 0) return;

    const audioBuf = ctx.createBuffer(1, samples.length, PLAYBACK_RATE);
    audioBuf.getChannelData(0).set(samples);

    let startAt = playbackCursorRef.current;
    if (startAt < ctx.currentTime + 0.005) {
      // Behind real time — re-seed the jitter buffer.
      startAt = ctx.currentTime + JITTER_BUFFER_SECONDS;
    }

    const src = ctx.createBufferSource();
    src.buffer = audioBuf;
    src.connect(ctx.destination);
    src.onended = () => {
      const idx = scheduledSourcesRef.current.indexOf(src);
      if (idx >= 0) scheduledSourcesRef.current.splice(idx, 1);
    };
    src.start(startAt);
    scheduledSourcesRef.current.push(src);
    playbackCursorRef.current = startAt + samples.length / PLAYBACK_RATE;
  }, []);

  const flushPlayback = useCallback(() => {
    for (const src of scheduledSourcesRef.current) {
      try {
        src.stop();
      } catch {}
    }
    scheduledSourcesRef.current = [];
    playbackCursorRef.current = 0;
    // AI stopped speaking (barge-in or end of response).
    setAiSpeaking(false);
    if (aiSpeakTimeoutRef.current) clearTimeout(aiSpeakTimeoutRef.current);
  }, []);

  // ---------- Accept call ----------
  const onAccept = useCallback(async () => {
    if (state.kind !== "ringing") return;
    const { token } = state;
    setState({ kind: "connecting", token });
    sounds.stopRinging();        // ringtone stops the instant they tap Accept
    sounds.playConnect();        // satisfying two-note connect cue
    callStartTimeRef.current = Date.now();
    const providerCallSid = token.call.provider_call_id || "";

    try {
      // 1. Get mic
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // 2. AudioContexts (created inside click handler to satisfy autoplay policies).
      // Separate contexts for capture and playback simplify cleanup and avoid loopback.
      const captureCtx = new AudioContext();
      captureCtxRef.current = captureCtx;
      const playbackCtx = new AudioContext({ sampleRate: PLAYBACK_RATE });
      playbackCtxRef.current = playbackCtx;
      playbackCursorRef.current = 0;

      await captureCtx.audioWorklet.addModule("/sim-audio-worklet.js");

      const source = captureCtx.createMediaStreamSource(stream);
      sourceNodeRef.current = source;
      const worklet = new AudioWorkletNode(captureCtx, "sim-downsampler");
      workletNodeRef.current = worklet;
      source.connect(worklet);
      // Don't connect worklet to destination — we only consume via messageport.

      // 3. WebSocket
      const ws = new WebSocket(token.ws_url);
      wsRef.current = ws;
      const streamSid = `SIM-${crypto.randomUUID()}`;
      streamSidRef.current = streamSid;

      ws.onopen = () => {
        // Exotel-protocol handshake.
        ws.send(JSON.stringify({ event: "connected" }));
        ws.send(
          JSON.stringify({
            event: "start",
            start: {
              call_sid: providerCallSid,
              stream_sid: streamSid,
              account_sid: "browser",
              custom_parameters: { resume_id: token.call.resume_id },
              media_format: {
                encoding: "audio/L16",
                sample_rate: 8000,
                channels: 1,
              },
            },
          }),
        );
        setState({ kind: "in_call", token });
      };

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          if (data?.event === "media") {
            const payload = data?.media?.payload;
            if (payload) handleMediaFrame(payload);
          } else if (data?.event === "clear") {
            flushPlayback();
          }
        } catch (e) {
          console.warn("Failed to parse WS message:", e);
        }
      };

      ws.onclose = () => {
        wsRef.current = null;
        sounds.playDisconnect();
        // Status transition is handled server-side by the bridge's finally block
        // (_update_call_finished → status='completed' + auto_evaluate_call_if_ready).
        teardown();
        setState({ kind: "ended", reason: "Call ended." });
      };

      ws.onerror = (e) => {
        console.error("Simulator WebSocket error:", e);
      };

      // 4. Pump mic audio.
      // Pre-encode a silent frame once and reuse while muted — keeps the wire
      // cadence at 20 ms (matching what real telephony does on a mute) and
      // signals "user silent" cleanly to upstream VAD.
      const silentFrame = arrayBufferToBase64(new ArrayBuffer(320));
      worklet.port.onmessage = ({ data }) => {
        const liveWs = wsRef.current;
        if (!liveWs || liveWs.readyState !== WebSocket.OPEN) return;
        const payload = mutedRef.current
          ? silentFrame
          : arrayBufferToBase64(data as ArrayBuffer);
        liveWs.send(
          JSON.stringify({
            event: "media",
            stream_sid: streamSid,
            media: { payload },
          }),
        );
      };
    } catch (err: any) {
      console.error("Failed to start simulator call:", err);
      teardown();
      const msg =
        err?.name === "NotAllowedError"
          ? "Microphone permission was denied. Please allow microphone access and click Retry."
          : err?.message || "Could not start the call.";
      setState({ kind: "error", message: msg });
    }
  }, [state, handleMediaFrame, flushPlayback, teardown, sounds]);

  // ---------- Decline ----------
  const onDecline = useCallback(() => {
    if (state.kind !== "ringing") return;
    sounds.stopRinging();
    sounds.playDisconnect();
    // No backend mutation needed: the call simply remains in 'queued' state.
    // Declining is a UX-only signal; cleanup happens via the queued-call expiry
    // (and won't block future calls because new calls for the same resume
    // refuse when an active call exists, which is the desired safety net).
    setState({ kind: "ended", reason: "Call declined." });
  }, [state, sounds]);

  // ---------- Hangup ----------
  const onHangup = useCallback(() => {
    // onclose fires playDisconnect — no need to call it here too.
    teardown();
    setState({ kind: "ended", reason: "Call ended." });
  }, [teardown]);

  // ---------- Retry on error ----------
  const onRetry = useCallback(() => {
    setState({ kind: "loading" });
    // Re-trigger the token-fetch effect by remounting via a key bump — but for
    // simplicity just reload the page (acceptable for an error path).
    window.location.reload();
  }, []);

  // ---------- Render ----------
  if (!callId) return <Navigate to="/dashboard" replace />;

  const callerName = "AI Interviewer";
  const callerLabel =
    state.kind === "ringing"
      ? "RecruiteAI · mobile"
      : state.kind === "connecting"
      ? "Connecting…"
      : state.kind === "in_call"
      ? durationLabel
      : state.kind === "ended"
      ? "Call ended"
      : "";

  const statusBadge =
    state.kind === "ringing"
      ? "Incoming call…"
      : state.kind === "connecting"
      ? "Connecting…"
      : state.kind === "in_call"
      ? "RecruiteAI"
      : "";

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center font-sans antialiased select-none"
      style={{ background: "radial-gradient(ellipse at 50% 30%, #1a1520 0%, #0a080d 60%, #050406 100%)" }}
    >
      <IPhoneFrame>
      {/* Content sits inside the IPhoneFrame's screen div.
          Top padding clears the Dynamic Island (34px pill + 13px top gap = 58px),
          bottom padding clears the home indicator (8px pill + some breathing room). */}
      <div
        className="relative w-full h-full flex flex-col px-8 select-none"
        style={{ paddingTop: 64, paddingBottom: 28 }}
      >
        {/* Loading */}
        {state.kind === "loading" && (
          <div className="flex-1 flex items-center justify-center gap-3 text-white/60">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading session…
          </div>
        )}

        {/* Error */}
        {state.kind === "error" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
            <p className="text-red-400 text-sm leading-relaxed">{state.message}</p>
            <button
              onClick={onRetry}
              className="px-6 py-2 rounded-full bg-white/10 hover:bg-white/15 transition text-sm"
            >
              Retry
            </button>
          </div>
        )}

        {/* Active call layouts (ringing / connecting / in_call / ended) */}
        {(state.kind === "ringing" ||
          state.kind === "connecting" ||
          state.kind === "in_call" ||
          state.kind === "ended") && (
          <>
            {/* Top: status badge + caller block */}
            <div className="flex flex-col items-center gap-1 mt-2">
              {statusBadge && (
                <p className="text-[13px] tracking-wide text-white/55">
                  {statusBadge}
                </p>
              )}
              <h1 className="text-[34px] font-medium tracking-tight leading-tight mt-2">
                {callerName}
              </h1>
              <p className="text-[15px] text-white/55 tabular-nums">{callerLabel}</p>
            </div>

            {/* Big circular avatar with pulse rings while ringing / AI-speaking glow */}
            <div className="flex-1 flex items-center justify-center">
              <div className="relative">
                {/* Ringing pulse rings */}
                {state.kind === "ringing" && (
                  <>
                    <span className="absolute inset-0 rounded-full bg-white/10 animate-ping" />
                    <span
                      className="absolute -inset-3 rounded-full border border-white/10"
                      style={{ animation: "sim-pulse 2s ease-out infinite" }}
                    />
                  </>
                )}
                {/* AI-speaking glow ring — soft indigo halo that pulses while frames arrive */}
                {state.kind === "in_call" && (
                  <span
                    className="absolute -inset-2 rounded-full transition-all duration-150"
                    style={{
                      boxShadow: aiSpeaking
                        ? "0 0 0 3px rgba(99,102,241,0.7), 0 0 28px 6px rgba(139,92,246,0.45)"
                        : "0 0 0 1.5px rgba(99,102,241,0.18)",
                      borderRadius: "50%",
                    }}
                  />
                )}
                <div
                  className="relative h-44 w-44 rounded-full overflow-hidden shadow-2xl"
                  style={{ background: "linear-gradient(160deg, #0d1117 0%, #1a1f2e 60%, #0f1420 100%)" }}
                >
                  <AgentSmithAvatar />
                </div>
              </div>
            </div>

            {/* Bottom controls */}
            <div className="mt-auto pb-2">
              {/* Ringing: Decline (red) + Accept (green) circular buttons */}
              {state.kind === "ringing" && (
                <div className="flex items-center justify-between px-4">
                  <CircleAction
                    color="#ef4444"
                    label="Decline"
                    onClick={onDecline}
                    Icon={PhoneOff}
                    big
                  />
                  <CircleAction
                    color="#22c55e"
                    label="Accept"
                    onClick={onAccept}
                    Icon={Phone}
                    big
                    pulse
                  />
                </div>
              )}

              {/* Connecting: spinner + cancel */}
              {state.kind === "connecting" && (
                <div className="flex items-center justify-center">
                  <CircleAction
                    color="#ef4444"
                    label="Cancel"
                    onClick={onHangup}
                    Icon={PhoneOff}
                    big
                  />
                </div>
              )}

              {/* In-call: 2x3 control grid + end-call */}
              {state.kind === "in_call" && (
                <div className="space-y-7">
                  <div className="grid grid-cols-3 gap-y-6 place-items-center">
                    <ToggleAction
                      label="mute"
                      active={muted}
                      activeLabel="muted"
                      onClick={() => { setMuted((m) => !m); sounds.playClick(); }}
                      Icon={muted ? MicOff : Mic}
                    />
                    <DisabledAction label="keypad" Icon={Grid3x3} />
                    <ToggleAction
                      label="speaker"
                      active={speakerOn}
                      onClick={() => setSpeakerOn((s) => !s)}
                      Icon={Volume2}
                    />
                    <DisabledAction label="add" Icon={Plus} />
                    <DisabledAction label="FaceTime" Icon={Video} />
                    <DisabledAction label="contacts" Icon={Users} />
                  </div>
                  <div className="flex items-center justify-center">
                    <CircleAction
                      color="#ef4444"
                      label="End"
                      onClick={onHangup}
                      Icon={PhoneOff}
                      big
                    />
                  </div>
                </div>
              )}

              {/* Ended: just a label */}
              {state.kind === "ended" && (
                <div className="flex flex-col items-center gap-3 pb-4">
                  <p className="text-white/60 text-sm">{state.reason}</p>
                  <p className="text-white/30 text-xs">You can close this tab.</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>{/* end inner content div */}
      </IPhoneFrame>

      {/* Pulse keyframes — must live in the outer wrapper, not inside the frame */}
      <style>{`
        @keyframes sim-pulse {
          0%   { transform: scale(1);    opacity: 0.45; }
          70%  { transform: scale(1.25); opacity: 0; }
          100% { transform: scale(1.25); opacity: 0; }
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Agent Smith avatar — SVG portrait illustration
// ---------------------------------------------------------------------------
function AgentSmithAvatar() {
  return (
    <svg
      viewBox="0 0 100 100"
      xmlns="http://www.w3.org/2000/svg"
      style={{ width: "100%", height: "100%", display: "block" }}
    >
      {/* ── Suit / jacket ────────────────────────────────── */}
      <path
        d="M0 100 L0 68 Q5 55 26 50 L50 60 L74 50 Q95 55 100 68 L100 100 Z"
        fill="#11131a"
      />
      {/* Lapels */}
      <path d="M43 51 L20 68 L36 57 Z" fill="#1e2030" />
      <path d="M57 51 L80 68 L64 57 Z" fill="#1e2030" />
      {/* White shirt */}
      <path d="M43 51 L50 60 L57 51 L55 67 L50 73 L45 67 Z" fill="#d8d8d0" />
      {/* Black tie */}
      <path d="M47.5 55 L52.5 55 L54 69 L50 75 L46 69 Z" fill="#080808" />
      {/* Tie knot */}
      <path d="M47.5 55 L50 58 L52.5 55 L51 52 L49 52 Z" fill="#141414" />

      {/* ── Neck ─────────────────────────────────────────── */}
      <rect x="43" y="46" width="14" height="9" rx="2" fill="#c8976b" />

      {/* ── Head / face ──────────────────────────────────── */}
      <ellipse cx="50" cy="32" rx="21" ry="23" fill="#c8976b" />

      {/* ── Hair (slicked back, very neat) ───────────────── */}
      <path
        d="M29 27 Q29 9 50 9 Q71 9 71 27 Q68 16 50 17 Q32 16 29 27 Z"
        fill="#181818"
      />
      {/* Side parting hint */}
      <path d="M39 13 Q42 17 42 21" fill="none" stroke="#2a2a2a" strokeWidth="0.8" />

      {/* ── Ears ─────────────────────────────────────────── */}
      <ellipse cx="29" cy="33" rx="3" ry="4.5" fill="#b8865b" />
      <ellipse cx="71" cy="33" rx="3" ry="4.5" fill="#b8865b" />

      {/* ── Earpiece (right ear) ─────────────────────────── */}
      <circle cx="73.5" cy="30" r="2.2" fill="#8a8a8a" />
      <line x1="73" y1="32" x2="74" y2="40" stroke="#7a7a7a" strokeWidth="1" />
      <circle cx="74" cy="40" r="1.2" fill="#6a6a6a" />

      {/* ── Sunglasses (rectangular, Agent Smith) ────────── */}
      {/* Left lens */}
      <rect x="31" y="30" width="15.5" height="8.5" rx="1.2" fill="#060606" />
      {/* Right lens */}
      <rect x="53.5" y="30" width="15.5" height="8.5" rx="1.2" fill="#060606" />
      {/* Bridge */}
      <rect x="46.5" y="33" width="7" height="1.8" rx="0.9" fill="#2a2a2a" />
      {/* Frame top edge highlight */}
      <rect x="31" y="30" width="15.5" height="1.2" rx="1" fill="#2a2a2a" opacity="0.9" />
      <rect x="53.5" y="30" width="15.5" height="1.2" rx="1" fill="#2a2a2a" opacity="0.9" />
      {/* Temple arms */}
      <line x1="31" y1="34.5" x2="29" y2="35" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="69" y1="34.5" x2="71" y2="35" stroke="#2a2a2a" strokeWidth="1.2" />
      {/* Subtle lens glare */}
      <line x1="34" y1="31.5" x2="38" y2="31.5" stroke="#1a1a1a" strokeWidth="0.6" opacity="0.6" />
      <line x1="56.5" y1="31.5" x2="60.5" y2="31.5" stroke="#1a1a1a" strokeWidth="0.6" opacity="0.6" />

      {/* ── Stern mouth ──────────────────────────────────── */}
      <path
        d="M42 46 Q50 47.5 58 46"
        fill="none"
        stroke="#9a6a40"
        strokeWidth="1.4"
        strokeLinecap="round"
      />

      {/* ── Subtle shadow under jaw ───────────────────────── */}
      <ellipse cx="50" cy="55" rx="14" ry="3" fill="#000" opacity="0.18" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// iPhone 17 Pro Max physical shell
// ---------------------------------------------------------------------------
function IPhoneFrame({ children }: { children: React.ReactNode }) {
  // Black Titanium palette
  const FRAME   = "linear-gradient(160deg,#2e2e30 0%,#1c1c1e 35%,#28282a 65%,#1c1c1e 100%)";
  const BTN_L   = "linear-gradient(to right, #141416, #232325)";
  const BTN_R   = "linear-gradient(to left,  #141416, #232325)";
  const SCREEN_BG = "#000";

  // Physical proportions: 163 × 77.6 mm → height:width ≈ 2.1
  // At our popup width (430 px content area) we use 415 × 870 px.
  const W = 415;
  const H = 870;
  const RADIUS      = 52;   // outer frame corner radius
  const SCREEN_RAD  = 47;   // screen/glass corner radius
  const FRAME_W     = 10;   // titanium band width (all sides)
  const SCREEN_W    = W - FRAME_W * 2;
  const SCREEN_H    = H - FRAME_W * 2;

  const btn = (
    side: "left" | "right",
    top: number,
    height: number,
    label: string
  ) => (
    <div
      aria-label={label}
      style={{
        position: "absolute",
        [side]: -5,
        top,
        width: 5,
        height,
        background: side === "left" ? BTN_L : BTN_R,
        borderRadius: side === "left" ? "4px 0 0 4px" : "0 4px 4px 0",
        boxShadow:
          side === "left"
            ? "inset 1px 0 0 rgba(255,255,255,0.06)"
            : "inset -1px 0 0 rgba(255,255,255,0.06)",
      }}
    />
  );

  return (
    <div
      style={{
        position: "relative",
        width: W,
        height: H,
        borderRadius: RADIUS,
        background: FRAME,
        boxShadow: [
          "inset 0 0 0 0.5px rgba(255,255,255,0.10)",   // inner highlight
          "0 0 0 1px rgba(0,0,0,0.7)",                    // outer edge
          "0 40px 100px rgba(0,0,0,0.85)",                // ambient shadow
          "0 4px 8px rgba(255,255,255,0.03)",             // top glint
        ].join(","),
        flexShrink: 0,
      }}
    >
      {/* ── Side buttons ─────────────────────────────── */}
      {/* Left: Action button */}
      {btn("left", 128,  38, "action-button")}
      {/* Left: Volume up */}
      {btn("left", 200,  62, "volume-up")}
      {/* Left: Volume down */}
      {btn("left", 278,  62, "volume-down")}
      {/* Right: Power / sleep */}
      {btn("right", 196, 80, "power-button")}
      {/* Right: Camera Control (iPhone 16+ feature) */}
      {btn("right", 316, 40, "camera-control")}

      {/* ── Screen glass ─────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          inset: FRAME_W,
          borderRadius: SCREEN_RAD,
          background: SCREEN_BG,
          overflow: "hidden",
          // subtle inner-edge highlight that mimics the glass edge
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.05)",
        }}
      >
        {/* ── Dynamic Island ─────────────────────── */}
        <div
          style={{
            position: "absolute",
            top: 13,
            left: "50%",
            transform: "translateX(-50%)",
            width: 120,
            height: 34,
            background: "#000",
            borderRadius: 20,
            zIndex: 200,
            // tiny pill shadow so it reads on dark backgrounds
            boxShadow: "0 0 0 2px #000, 0 2px 8px rgba(0,0,0,0.9)",
          }}
        />

        {/* ── Content ────────────────────────────── */}
        <div style={{ width: SCREEN_W, height: SCREEN_H, overflow: "hidden" }}>
          {children}
        </div>

        {/* ── Home indicator ─────────────────────── */}
        <div
          style={{
            position: "absolute",
            bottom: 8,
            left: "50%",
            transform: "translateX(-50%)",
            width: 130,
            height: 5,
            background: "rgba(255,255,255,0.32)",
            borderRadius: 3,
            zIndex: 200,
          }}
        />
      </div>

      {/* ── Titanium surface sheen (top-left catch-light) ── */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: RADIUS,
          pointerEvents: "none",
          background:
            "linear-gradient(135deg, rgba(255,255,255,0.06) 0%, transparent 40%)",
        }}
      />
    </div>
  );
}

// --- iOS-style circular action button --------------------------------------
function CircleAction({
  color,
  label,
  onClick,
  Icon,
  big,
  pulse,
}: {
  color: string;
  label: string;
  onClick: () => void;
  Icon: typeof Phone;
  big?: boolean;
  pulse?: boolean;
}) {
  const size = big ? "h-[72px] w-[72px]" : "h-14 w-14";
  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={onClick}
        aria-label={label}
        className={`${size} rounded-full flex items-center justify-center active:scale-95 transition-transform shadow-lg`}
        style={{
          backgroundColor: color,
          boxShadow: `0 10px 30px ${color}40`,
        }}
      >
        {pulse && (
          <span
            className="absolute h-[72px] w-[72px] rounded-full"
            style={{ background: color, opacity: 0.35, animation: "sim-pulse 1.5s ease-out infinite" }}
          />
        )}
        <Icon className="h-7 w-7 text-white relative" strokeWidth={2.2} />
      </button>
      <span className="text-[13px] text-white/70">{label}</span>
    </div>
  );
}

// --- iOS-style toggle action (mute, speaker) -------------------------------
function ToggleAction({
  label,
  active,
  activeLabel,
  onClick,
  Icon,
}: {
  label: string;
  active: boolean;
  activeLabel?: string;
  onClick: () => void;
  Icon: typeof Mic;
}) {
  return (
    <div className="flex flex-col items-center gap-2">
      <button
        onClick={onClick}
        aria-pressed={active}
        aria-label={label}
        className="h-16 w-16 rounded-full flex items-center justify-center transition active:scale-95"
        style={{
          backgroundColor: active ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.10)",
          color: active ? "#111" : "#fff",
        }}
      >
        <Icon className="h-6 w-6" strokeWidth={2} />
      </button>
      <span className="text-[13px] text-white/70">{active && activeLabel ? activeLabel : label}</span>
    </div>
  );
}

// --- iOS-style disabled (decorative) action --------------------------------
function DisabledAction({
  label,
  Icon,
}: {
  label: string;
  Icon: typeof Mic;
}) {
  return (
    <div className="flex flex-col items-center gap-2 opacity-40">
      <div className="h-16 w-16 rounded-full flex items-center justify-center bg-white/5">
        <Icon className="h-6 w-6 text-white/70" strokeWidth={2} />
      </div>
      <span className="text-[13px] text-white/50">{label}</span>
    </div>
  );
}
