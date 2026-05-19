/**
 * AudioPlayer — premium interview recording player.
 *
 * Features:
 *  - Wavesurfer.js waveform with speaker-colored regions
 *  - Play/pause, ±10s / ±30s skip
 *  - Playback speed (0.5×–2×)
 *  - Volume slider + mute toggle
 *  - Keyboard shortcuts (Space, ←/→, ↑/↓, M, [/])
 *  - Transcript-synced highlighting (active segment highlighted by caller)
 *  - Download button
 *  - Loading skeleton + error state
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download,
  Headphones,
  Mic,
  Pause,
  Play,
  RotateCcw,
  RotateCw,
  Volume2,
  VolumeX,
  Volume1,
  Loader2,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAudioPlayer, type TranscriptEntry } from "./useAudioPlayer";

// ── helpers ────────────────────────────────────────────────────────────────

function formatTime(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const SPEED_OPTIONS = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
type SpeedOption = (typeof SPEED_OPTIONS)[number];

// ── sub-components ─────────────────────────────────────────────────────────

function SpeakerLegend() {
  return (
    <div className="flex items-center gap-4 text-[10px] font-medium uppercase tracking-wider text-muted-foreground/70">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 rounded-sm bg-indigo-500/70" />
        AI Interviewer
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2 w-2 rounded-sm bg-emerald-500/70" />
        Candidate
      </span>
    </div>
  );
}

interface SpeedMenuProps {
  rate: number;
  onChange: (r: number) => void;
}
function SpeedMenu({ rate, onChange }: SpeedMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center justify-center rounded-lg border border-border/40 bg-background/50 px-2.5 py-1.5 text-xs font-semibold tabular-nums text-foreground transition-colors hover:bg-accent hover:border-border/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        aria-label={`Playback speed: ${rate}×`}
      >
        {rate}×
      </button>
      {open && (
        <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2 z-50 min-w-[72px] rounded-xl border border-border/50 bg-card/95 backdrop-blur-sm shadow-xl overflow-hidden py-1">
          {SPEED_OPTIONS.map(s => (
            <button
              key={s}
              onClick={() => { onChange(s); setOpen(false); }}
              className={`w-full px-4 py-1.5 text-center text-xs font-medium transition-colors hover:bg-accent ${
                s === rate
                  ? "text-primary bg-primary/8 font-semibold"
                  : "text-foreground/80"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

interface VolumeControlProps {
  volume: number;
  isMuted: boolean;
  onVolumeChange: (v: number) => void;
  onToggleMute: () => void;
}
function VolumeControl({ volume, isMuted, onVolumeChange, onToggleMute }: VolumeControlProps) {
  const displayVolume = isMuted ? 0 : volume;
  const Icon = isMuted || volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={onToggleMute}
        className="flex items-center justify-center rounded-lg p-1.5 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
        aria-label={isMuted ? "Unmute" : "Mute"}
      >
        <Icon className="h-4 w-4" />
      </button>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={displayVolume}
        onChange={e => onVolumeChange(parseFloat(e.target.value))}
        className="volume-slider h-1 w-20 cursor-pointer appearance-none rounded-full bg-border/60 accent-primary"
        aria-label="Volume"
      />
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────

export interface AudioPlayerProps {
  audioUrl: string | null;
  audioLoading?: boolean;
  callStartedAt?: string | null;
  durationSeconds?: number | null;
  transcript?: TranscriptEntry[];
  onActiveSegmentChange?: (id: string | null) => void;
  onSeekToTranscriptEntry?: (seekFn: (entry: TranscriptEntry) => void) => void;
}

export function AudioPlayer({
  audioUrl,
  audioLoading = false,
  callStartedAt,
  durationSeconds,
  transcript = [],
  onActiveSegmentChange,
  onSeekToTranscriptEntry,
}: AudioPlayerProps) {
  const player = useAudioPlayer({
    audioUrl,
    callStartedAt,
    duration: durationSeconds,
    transcript,
  });

  const {
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
    skip,
    setVolume,
    toggleMute,
    setPlaybackRate,
    seekToTranscriptEntry,
  } = player;

  // Expose seekToTranscriptEntry to parent (for transcript pane)
  useEffect(() => {
    onSeekToTranscriptEntry?.(seekToTranscriptEntry);
  }, [seekToTranscriptEntry, onSeekToTranscriptEntry]);

  // Propagate active segment to parent
  useEffect(() => {
    onActiveSegmentChange?.(activeSegmentId);
  }, [activeSegmentId, onActiveSegmentChange]);

  // ── Keyboard shortcuts ──────────────────────────────────────────────────
  const playerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Only fire when not focused in an input
      if (
        document.activeElement instanceof HTMLInputElement ||
        document.activeElement instanceof HTMLTextAreaElement
      ) return;
      if (!audioUrl) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          togglePlay();
          break;
        case "ArrowRight":
          e.preventDefault();
          skip(e.shiftKey ? 30 : 10);
          break;
        case "ArrowLeft":
          e.preventDefault();
          skip(e.shiftKey ? -30 : -10);
          break;
        case "ArrowUp":
          e.preventDefault();
          setVolume(Math.min(1, volume + 0.1));
          break;
        case "ArrowDown":
          e.preventDefault();
          setVolume(Math.max(0, volume - 0.1));
          break;
        case "m":
        case "M":
          toggleMute();
          break;
        case "[":
          { const idx = SPEED_OPTIONS.indexOf(playbackRate as SpeedOption);
            if (idx > 0) setPlaybackRate(SPEED_OPTIONS[idx - 1]); }
          break;
        case "]":
          { const idx = SPEED_OPTIONS.indexOf(playbackRate as SpeedOption);
            if (idx < SPEED_OPTIONS.length - 1) setPlaybackRate(SPEED_OPTIONS[idx + 1]); }
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [audioUrl, togglePlay, skip, setVolume, toggleMute, setPlaybackRate, volume, playbackRate]);

  // ── Download ────────────────────────────────────────────────────────────
  const handleDownload = () => {
    if (!audioUrl) return;
    const a = document.createElement("a");
    a.href = audioUrl;
    a.download = "call-recording.mp3";
    a.click();
  };

  // ── Progress ────────────────────────────────────────────────────────────
  const progressPct = totalDuration > 0 ? (currentTime / totalDuration) * 100 : 0;

  // ── Speaker talk-time ratio ─────────────────────────────────────────────
  const talkTime = (() => {
    if (!callStartedAt || transcript.length < 2) return null;
    const startMs = Date.parse(callStartedAt);
    const entries = transcript
      .map(e => ({
        role: e.speaker.toLowerCase(),
        offsetSeconds: e.timestamp ? (Date.parse(e.timestamp) - startMs) / 1000 : null,
      }))
      .filter(e => e.offsetSeconds !== null);

    if (entries.length < 2) return null;
    const dur = totalDuration || durationSeconds || 0;
    if (dur === 0) return null;

    let aiTime = 0, candidateTime = 0;
    entries.forEach((e, i) => {
      const nextOffset = entries[i + 1]?.offsetSeconds ?? dur;
      const span = Math.max(0, (nextOffset - e.offsetSeconds!));
      const isAI = e.role === "assistant" || e.role === "ai";
      if (isAI) aiTime += span;
      else candidateTime += span;
    });

    const total = aiTime + candidateTime;
    if (total === 0) return null;
    return {
      ai: Math.round((aiTime / total) * 100),
      candidate: Math.round((candidateTime / total) * 100),
    };
  })();

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <Card className="border-border/50 bg-card/70 overflow-hidden" ref={playerRef}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Headphones className="h-4 w-4 text-primary" />
            Call Recording
          </CardTitle>
          <div className="flex items-center gap-2">
            {talkTime && (
              <span className="text-[10px] text-muted-foreground/60 tabular-nums hidden sm:block">
                AI {talkTime.ai}% · Candidate {talkTime.candidate}%
              </span>
            )}
            {audioUrl && isReady && (
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
                onClick={handleDownload}
                aria-label="Download recording"
              >
                <Download className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* ── Loading skeleton (blob fetch) ─────────────────────────── */}
        {audioLoading && (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full rounded-xl" />
            <div className="flex justify-between">
              <Skeleton className="h-4 w-10" />
              <Skeleton className="h-4 w-10" />
            </div>
            <Skeleton className="h-10 w-full rounded-xl" />
          </div>
        )}

        {/* ── No recording ─────────────────────────────────────────── */}
        {!audioLoading && !audioUrl && (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border/50 bg-background/40 py-10 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted/30">
              <Mic className="h-5 w-5 text-muted-foreground/50" />
            </div>
            <p className="text-sm text-muted-foreground">
              No recording available for this call yet.
            </p>
          </div>
        )}

        {/* ── Error ────────────────────────────────────────────────── */}
        {errorMsg && (
          <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {errorMsg}
          </div>
        )}

        {/* ── Player UI ────────────────────────────────────────────── */}
        {!audioLoading && audioUrl && !errorMsg && (
          <>
            {/* Speaker legend */}
            {transcript.length > 0 && callStartedAt && (
              <SpeakerLegend />
            )}

            {/* Waveform container */}
            <div className="relative">
              {/* Waveform decode loading overlay */}
              {isLoading && (
                <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-background/60 backdrop-blur-[2px]">
                  <Loader2 className="h-5 w-5 animate-spin text-primary/60" />
                </div>
              )}
              <div
                ref={containerRef}
                className={`w-full rounded-xl overflow-hidden transition-opacity duration-300 ${
                  isReady ? "opacity-100" : "opacity-0"
                }`}
              />
              {/* Skeleton while decoding */}
              {!isReady && !isLoading && (
                <Skeleton className="h-20 w-full rounded-xl" />
              )}
            </div>

            {/* Time display */}
            <div className="flex items-center justify-between text-[11px] font-medium tabular-nums text-muted-foreground/70 px-0.5">
              <span>{formatTime(currentTime)}</span>
              {/* Thin seekbar fallback (also works as a visual progress cue) */}
              <div className="relative mx-3 flex-1 h-1 rounded-full bg-border/40 overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 bg-primary/60 rounded-full transition-all duration-100"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <span>{formatTime(totalDuration)}</span>
            </div>

            {/* Controls row */}
            <div className="flex items-center justify-between gap-3">
              {/* Speed */}
              <SpeedMenu rate={playbackRate} onChange={setPlaybackRate} />

              {/* Transport */}
              <div className="flex items-center gap-1">
                <button
                  onClick={() => skip(-10)}
                  disabled={!isReady}
                  className="flex items-center justify-center rounded-xl p-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                  aria-label="Skip back 10 seconds"
                >
                  <RotateCcw className="h-4 w-4" />
                  <span className="ml-0.5 text-[9px] font-bold">10</span>
                </button>

                {/* Play / Pause */}
                <button
                  onClick={togglePlay}
                  disabled={!isReady}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md shadow-primary/30 transition-all hover:scale-105 hover:shadow-lg hover:shadow-primary/40 active:scale-95 disabled:opacity-50 disabled:shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
                  aria-label={isPlaying ? "Pause" : "Play"}
                >
                  {isPlaying ? (
                    <Pause className="h-4 w-4" fill="currentColor" />
                  ) : (
                    <Play className="h-4 w-4 translate-x-0.5" fill="currentColor" />
                  )}
                </button>

                <button
                  onClick={() => skip(10)}
                  disabled={!isReady}
                  className="flex items-center justify-center rounded-xl p-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
                  aria-label="Skip forward 10 seconds"
                >
                  <RotateCw className="h-4 w-4" />
                  <span className="ml-0.5 text-[9px] font-bold">10</span>
                </button>
              </div>

              {/* Volume */}
              <VolumeControl
                volume={volume}
                isMuted={isMuted}
                onVolumeChange={setVolume}
                onToggleMute={toggleMute}
              />
            </div>

            {/* Keyboard hint */}
            <p className="text-center text-[10px] text-muted-foreground/40 select-none">
              Space · ← → to seek · [ ] speed · M mute
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
