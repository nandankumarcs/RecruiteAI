/**
 * useAudioPlayer — manages the full WaveSurfer lifecycle, playback state,
 * speaker-region overlays, and transcript-sync cursor tracking.
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";

export interface TranscriptEntry {
  id: string;
  speaker: string;           // "assistant" | "user" / "candidate"
  text: string;
  timestamp?: string;        // ISO 8601 absolute datetime
}

interface UseAudioPlayerOptions {
  audioUrl: string | null;
  callStartedAt?: string | null;   // ISO 8601 — used to compute offsets
  duration?: number | null;        // seconds — from backend; used before decode
  transcript?: TranscriptEntry[];
}

export interface UseAudioPlayerReturn {
  containerRef: React.RefObject<HTMLDivElement | null>;
  isReady: boolean;
  isLoading: boolean;
  isPlaying: boolean;
  currentTime: number;         // seconds
  totalDuration: number;       // seconds
  volume: number;              // 0–1
  isMuted: boolean;
  playbackRate: number;
  activeSegmentId: string | null;
  errorMsg: string | null;

  // Controls
  togglePlay: () => void;
  seek: (seconds: number) => void;    // absolute seek
  skip: (delta: number) => void;      // relative skip (+/-)
  setVolume: (v: number) => void;
  toggleMute: () => void;
  setPlaybackRate: (r: number) => void;
  seekToTranscriptEntry: (entry: TranscriptEntry) => void;
}

const SPEAKER_COLORS: Record<string, string> = {
  assistant: "rgba(99, 102, 241, 0.18)",   // indigo
  ai: "rgba(99, 102, 241, 0.18)",
  user: "rgba(34, 197, 94, 0.18)",          // emerald
  candidate: "rgba(34, 197, 94, 0.18)",
};
const SPEAKER_BORDER: Record<string, string> = {
  assistant: "rgba(99, 102, 241, 0.5)",
  ai: "rgba(99, 102, 241, 0.5)",
  user: "rgba(34, 197, 94, 0.5)",
  candidate: "rgba(34, 197, 94, 0.5)",
};
const DEFAULT_COLOR = "rgba(148, 163, 184, 0.15)";
const DEFAULT_BORDER = "rgba(148, 163, 184, 0.4)";

const SAVED_VOLUME_KEY = "recruiteai_audio_volume";
const SAVED_RATE_KEY = "recruiteai_audio_rate";

function getSavedVolume(): number {
  try { return parseFloat(localStorage.getItem(SAVED_VOLUME_KEY) ?? "1"); } catch { return 1; }
}
function getSavedRate(): number {
  try { return parseFloat(localStorage.getItem(SAVED_RATE_KEY) ?? "1"); } catch { return 1; }
}

export function useAudioPlayer({
  audioUrl,
  callStartedAt,
  duration,
  transcript = [],
}: UseAudioPlayerOptions): UseAudioPlayerReturn {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);

  const [isReady, setIsReady] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [totalDuration, setTotalDuration] = useState(duration ?? 0);
  const [volume, setVolumeState] = useState(getSavedVolume);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRateState] = useState(getSavedRate);
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Compute transcript entries with offset seconds relative to call start
  const entriesWithOffset = useMemo(() => {
    if (!callStartedAt || transcript.length === 0) return transcript.map(e => ({ ...e, offsetSeconds: null as number | null }));
    const startMs = Date.parse(callStartedAt);
    return transcript.map(e => {
      const offsetSeconds = e.timestamp ? (Date.parse(e.timestamp) - startMs) / 1000 : null;
      return { ...e, offsetSeconds };
    });
  }, [transcript, callStartedAt]);

  // Active transcript segment based on currentTime
  useEffect(() => {
    if (!callStartedAt || entriesWithOffset.length === 0) return;
    const valid = entriesWithOffset.filter(e => e.offsetSeconds !== null && e.offsetSeconds <= currentTime);
    const active = valid[valid.length - 1] ?? null;
    setActiveSegmentId(active?.id ?? null);
  }, [currentTime, entriesWithOffset, callStartedAt]);

  // Initialize WaveSurfer
  useLayoutEffect(() => {
    if (!containerRef.current || !audioUrl) return;

    setIsLoading(true);
    setIsReady(false);
    setErrorMsg(null);

    const regions = RegionsPlugin.create();
    regionsRef.current = regions;

    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: "rgba(148, 163, 184, 0.4)",
      progressColor: "rgba(99, 102, 241, 0.85)",
      cursorColor: "rgba(99, 102, 241, 1)",
      cursorWidth: 2,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: 80,
      normalize: true,
      interact: true,
      plugins: [regions],
    });

    wsRef.current = ws;

    ws.setVolume(getSavedVolume());
    ws.setPlaybackRate(getSavedRate());

    ws.load(audioUrl);

    ws.on("loading", (pct) => {
      if (pct < 100) setIsLoading(true);
    });

    ws.on("decode", (dur) => {
      setTotalDuration(dur);
    });

    ws.on("ready", (dur) => {
      setTotalDuration(dur);
      setIsLoading(false);
      setIsReady(true);

      // Add speaker regions
      if (entriesWithOffset.length > 0 && callStartedAt) {
        const sorted = [...entriesWithOffset].filter(e => e.offsetSeconds !== null);
        sorted.forEach((entry, idx) => {
          const start = entry.offsetSeconds!;
          const nextOffset = sorted[idx + 1]?.offsetSeconds ?? dur;
          const end = Math.min(nextOffset, dur);
          if (start >= end) return;

          const role = entry.speaker.toLowerCase();
          const color = SPEAKER_COLORS[role] ?? DEFAULT_COLOR;
          const borderColor = SPEAKER_BORDER[role] ?? DEFAULT_BORDER;

          regions.addRegion({
            id: entry.id,
            start,
            end,
            color,
            drag: false,
            resize: false,
            content: undefined,
          });

          // Apply border styling via the DOM after a tick
          setTimeout(() => {
            const el = containerRef.current?.querySelector(`[data-id="${entry.id}"]`) as HTMLElement | null;
            if (el) {
              el.style.borderLeft = `2px solid ${borderColor}`;
              el.style.borderRadius = "2px";
            }
          }, 50);
        });
      }
    });

    ws.on("timeupdate", (t) => {
      setCurrentTime(t);
    });

    ws.on("play", () => setIsPlaying(true));
    ws.on("pause", () => setIsPlaying(false));
    ws.on("finish", () => {
      setIsPlaying(false);
      setCurrentTime(ws.getDuration());
    });

    ws.on("error", (err) => {
      console.error("[AudioPlayer] WaveSurfer error:", err);
      setIsLoading(false);
      setErrorMsg("Could not load the audio recording.");
    });

    return () => {
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
      setIsReady(false);
      setIsPlaying(false);
    };
    // Intentionally excluding entriesWithOffset from deps — we re-add regions only on mount/url change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl, callStartedAt]);

  // Sync volume/mute/rate to WaveSurfer without reinitializing
  useEffect(() => {
    if (!wsRef.current) return;
    wsRef.current.setVolume(isMuted ? 0 : volume);
  }, [volume, isMuted]);

  useEffect(() => {
    if (!wsRef.current) return;
    wsRef.current.setPlaybackRate(playbackRate);
  }, [playbackRate]);

  // Controls
  const togglePlay = useCallback(() => {
    wsRef.current?.playPause();
  }, []);

  const seek = useCallback((seconds: number) => {
    const ws = wsRef.current;
    if (!ws || !isReady) return;
    const dur = ws.getDuration();
    if (!dur) return;
    ws.seekTo(Math.max(0, Math.min(seconds, dur)) / dur);
  }, [isReady]);

  const skip = useCallback((delta: number) => {
    const ws = wsRef.current;
    if (!ws || !isReady) return;
    const newTime = (ws.getCurrentTime() ?? 0) + delta;
    const dur = ws.getDuration();
    if (!dur) return;
    ws.seekTo(Math.max(0, Math.min(newTime, dur)) / dur);
  }, [isReady]);

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setVolumeState(clamped);
    setIsMuted(false);
    try { localStorage.setItem(SAVED_VOLUME_KEY, String(clamped)); } catch { /* ignore */ }
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted(m => !m);
  }, []);

  const setPlaybackRate = useCallback((r: number) => {
    setPlaybackRateState(r);
    try { localStorage.setItem(SAVED_RATE_KEY, String(r)); } catch { /* ignore */ }
  }, []);

  const seekToTranscriptEntry = useCallback((entry: TranscriptEntry) => {
    if (!callStartedAt || !entry.timestamp) return;
    const offset = (Date.parse(entry.timestamp) - Date.parse(callStartedAt)) / 1000;
    seek(offset);
    // Auto-play if paused
    if (!isPlaying) wsRef.current?.play();
  }, [callStartedAt, seek, isPlaying]);

  return {
    containerRef,
    isReady,
    isLoading,
    isPlaying,
    currentTime,
    totalDuration,
    volume,
    isMuted,
    playbackRate,
    activeSegmentId,
    errorMsg,
    togglePlay,
    seek,
    skip,
    setVolume,
    toggleMute,
    setPlaybackRate,
    seekToTranscriptEntry,
  };
}
