import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Cpu,
  DollarSign,
  Headphones,
  Loader2,
  MessageSquare,
  PhoneCall,
  Radio,
  Sparkles,
  Timer,
  UserRound,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Activity,
  Play,
} from "lucide-react";

import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";



import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CallProgressIndicator } from "@/components/calls/CallProgressIndicator";
import type { CallRecord } from "@/lib/calls";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/context/ToastContext";
import { AudioPlayer } from "@/components/audio/AudioPlayer";
import { type TranscriptEntry } from "@/components/audio/useAudioPlayer";

interface CallEvaluation extends Record<string, unknown> {
  schema_version: string;
  status: string;
  confidence: string;
  overall_score: number | null;
  technical_score: number | null;
  communication_score: number | null;
  experience_score: number | null;
  behavioral_score?: number | null;
  behavioral_summary?: string | null;
  remarks: string;
  strengths: string[];
  weaknesses: string[];
  recommendation: string;
}

interface TranscriptLine {
  id: string;
  speaker: string;
  text: string;
  timestamp?: string;
}

interface TurnData {
  turn: number;
  role: string;
  words: number;
  gap_ms: number | null;
  content_preview: string;
}

interface TurnAnalysis {
  turns: TurnData[];
  assistant_turns: number;
  candidate_turns: number;
  avg_assistant_words: number;
  avg_candidate_words: number;
  avg_ai_response_ms: number | null;
  avg_candidate_response_ms: number | null;
}

type CallDetailData = CallRecord;


const scoreItems = [
  { key: "technical_score", label: "Technical" },
  { key: "communication_score", label: "Communication" },
  { key: "experience_score", label: "Experience" },
] as const;

const nonScorableLabels: Record<string, string> = {
  insufficient_data: "Insufficient Data",
  candidate_disengaged: "Candidate Disengaged",
  call_quality_issue: "Call Quality Issue",
  completed_evaluation: "Completed",
};

const recommendationClasses: Record<string, string> = {
  advance: "bg-emerald-500/10 text-emerald-700 border-emerald-500/20",
  hold: "bg-amber-500/10 text-amber-700 border-amber-500/20",
  reject: "bg-rose-500/10 text-rose-700 border-rose-500/20",
  insufficient_data: "bg-slate-500/10 text-slate-700 border-slate-500/20",
};

function parseTranscript(transcript: string | null): TranscriptLine[] {
  if (!transcript) return [];

  return transcript
    .split("\n")
    .map((line, index) => {
      const [speakerPart, ...textParts] = line.split(":");
      const normalizedSpeaker = speakerPart?.trim() || "Speaker";
      const text = textParts.join(":").trim();
      return {
        id: `${normalizedSpeaker}-${index}`,
        speaker: normalizedSpeaker,
        text: text || line.trim(),
      };
    })
    .filter((line) => line.text.length > 0);
}

// ---- Latency helpers ----
const LATENCY_LABEL_MAP: Record<string, string> = {
  call_requested_at: "Call requested",
  call_answered_at: "Call answered",
  stream_connected_at: "Stream connected",
  first_assistant_audio_at: "First assistant audio",
  first_user_transcript_at: "First user transcript",
};

interface LatencyDelta {
  key: string;
  label: string;
  absoluteTime: string;
  deltaFromStartMs: number | null;
  deltaFromPreviousMs: number | null;
}

const MARKER_ORDER = [
  "call_requested_at",
  "call_answered_at",
  "stream_connected_at",
  "first_assistant_audio_at",
  "first_user_transcript_at",
];

function computeLatencyDeltas(metrics: Record<string, string>): LatencyDelta[] {
  const origin = metrics["call_requested_at"];
  const originMs = origin ? Date.parse(origin) : null;

  const orderedKeys = [
    ...MARKER_ORDER.filter((k) => k in metrics),
    ...Object.keys(metrics).filter((k) => !MARKER_ORDER.includes(k)),
  ];

  let prevMs: number | null = originMs;

  return orderedKeys.map((key) => {
    const value = metrics[key];
    const ts = Date.parse(value);
    const deltaFromStartMs = originMs !== null && !isNaN(ts) ? ts - originMs : null;
    const deltaFromPreviousMs = prevMs !== null && !isNaN(ts) ? ts - prevMs : null;
    prevMs = isNaN(ts) ? prevMs : ts;
    return {
      key,
      label: LATENCY_LABEL_MAP[key] ?? key.replace(/_/g, " "),
      absoluteTime: value,
      deltaFromStartMs,
      deltaFromPreviousMs,
    };
  });
}

function fmtMs(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function CallDetail() {
  const { toast } = useToast();
  const { callId } = useParams<{ callId: string }>();
  const [call, setCall] = useState<CallDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
  const seekToTranscriptRef = useRef<((entry: TranscriptEntry) => void) | null>(null);


  useEffect(() => {
    if (!callId) return;

    const fetchCall = async () => {
      try {
        setLoading(true);
        setError("");
        const response = await api.get<CallDetailData>(`/calls/${callId}`);
        setCall(response.data);
      } catch (err) {
        console.error("Failed to fetch call detail", err);
        setError("Could not load call details right now.");
        toast({
          variant: "error",
          title: "Call detail unavailable",
          description: "We couldn't load this interview call right now.",
        });
      } finally {
        setLoading(false);
      }
    };

    void fetchCall();
  }, [callId, toast]);

  const turnAnalysis = useMemo((): TurnAnalysis | null => {
    if (!call?.messages || call.messages.length < 2) return null;

    const sorted = [...call.messages].sort((a, b) => a.sequence_number - b.sequence_number);
    const wordCount = (text: string) => text.trim().split(/\s+/).filter(Boolean).length;

    const turns: TurnData[] = sorted.map((msg, i) => {
      const prev = sorted[i - 1];
      const gap_ms = prev
        ? Date.parse(msg.created_at) - Date.parse(prev.created_at)
        : null;
      const role = msg.role === "assistant" ? "assistant" : "candidate";
      return {
        turn: i + 1,
        role,
        words: wordCount(msg.content),
        gap_ms: gap_ms !== null && gap_ms >= 0 ? gap_ms : null,
        content_preview: msg.content.slice(0, 60),
      };
    });

    const assistantTurns = turns.filter((t) => t.role === "assistant");
    const candidateTurns = turns.filter((t) => t.role === "candidate");

    const avg = (nums: number[]) =>
      nums.length ? Math.round(nums.reduce((a, b) => a + b, 0) / nums.length) : 0;

    // AI response time: gap on assistant turns that follow a candidate turn
    const aiResponseGaps = assistantTurns
      .filter((t) => t.gap_ms !== null && sorted[t.turn - 2]?.role !== "assistant")
      .map((t) => t.gap_ms!);

    // Candidate response time: gap on candidate turns that follow an assistant turn
    const candidateResponseGaps = candidateTurns
      .filter((t) => t.gap_ms !== null && sorted[t.turn - 2]?.role === "assistant")
      .map((t) => t.gap_ms!);

    return {
      turns,
      assistant_turns: assistantTurns.length,
      candidate_turns: candidateTurns.length,
      avg_assistant_words: avg(assistantTurns.map((t) => t.words)),
      avg_candidate_words: avg(candidateTurns.map((t) => t.words)),
      avg_ai_response_ms: aiResponseGaps.length ? avg(aiResponseGaps) : null,
      avg_candidate_response_ms: candidateResponseGaps.length ? avg(candidateResponseGaps) : null,
    };
  }, [call?.messages]);


  useEffect(() => {
    if (!callId || !call?.recording_url) {
      setRecordingUrl((currentUrl) => {
        if (currentUrl) {
          URL.revokeObjectURL(currentUrl);
        }
        return null;
      });
      return;
    }

    let revoked = false;
    let nextObjectUrl: string | null = null;

    const fetchRecording = async () => {
      try {
        setRecordingLoading(true);
        const token = localStorage.getItem("accessToken");
        const response = await fetch(`${api.defaults.baseURL}/calls/${callId}/recording`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!response.ok) {
          throw new Error(`Recording fetch failed with status ${response.status}`);
        }

        const blob = await response.blob();
        nextObjectUrl = URL.createObjectURL(blob);
        if (!revoked) {
          setRecordingUrl((currentUrl) => {
            if (currentUrl) {
              URL.revokeObjectURL(currentUrl);
            }
            return nextObjectUrl;
          });
        }
      } catch (err) {
        console.error("Failed to fetch recording", err);
        toast({
          variant: "error",
          title: "Recording unavailable",
          description: "We couldn't load the call audio for playback.",
        });
      } finally {
        if (!revoked) {
          setRecordingLoading(false);
        }
      }
    };

    void fetchRecording();

    return () => {
      revoked = true;
      if (nextObjectUrl) {
        URL.revokeObjectURL(nextObjectUrl);
      }
    };
  }, [call?.recording_url, callId, toast]);

  const evaluateCall = async () => {
    if (!callId) return;

    try {
      setIsEvaluating(true);
      setError("");
      const evaluationResponse = await api.post<CallEvaluation>(`/calls/${callId}/evaluate`);
      setCall((current) =>
        current
          ? {
              ...current,
              status: current.status === "queued" ? "completed" : current.status,
              ai_evaluation: evaluationResponse.data,
            }
          : current
      );
      toast({
        variant: "success",
        title: "Evaluation updated",
        description: "The interview has been scored successfully.",
      });
    } catch (err) {
      console.error("Failed to evaluate call", err);
      setError("Evaluation could not be completed yet. A transcript may still be missing.");
      toast({
        variant: "error",
        title: "Evaluation unavailable",
        description: "This call needs a usable transcript before it can be scored.",
      });
    } finally {
      setIsEvaluating(false);
    }
  };

  const transcriptLines = useMemo(() => {
    if (call?.messages && call.messages.length > 0) {
      return [...call.messages].sort((a, b) => a.sequence_number - b.sequence_number).map((m) => ({
        id: m.id,
        speaker: m.role === "assistant" ? "Assistant" : "Candidate",
        text: m.content,
        timestamp: m.created_at,
      }));
    }
    return parseTranscript(call?.transcript ?? null);
  }, [call?.transcript, call?.messages]);

  const transcriptBottomRef = useRef<HTMLDivElement>(null);
  const isLive = ["queued", "ringing", "in_progress"].includes(call?.status ?? "");

  // Auto-scroll transcript to bottom whenever new messages arrive during a live call
  useEffect(() => {
    if (isLive && transcriptBottomRef.current) {
      transcriptBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [transcriptLines, isLive]);

  // Auto-scroll the active playing segment into view
  useEffect(() => {
    if (activeSegmentId) {
      const element = document.getElementById(`transcript-line-${activeSegmentId}`);
      if (element) {
        element.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      }
    }
  }, [activeSegmentId]);

  if (loading) {
    return (
      <div className="space-y-6 pb-12">
        <Skeleton className="h-6 w-28" />
        <div className="space-y-2">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="h-5 w-72" />
        </div>
        <div className="grid gap-6 md:grid-cols-3">
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  if (!call) {
    return (
      <div className="space-y-4 py-12 text-center">
        <h2 className="text-2xl font-bold">Call not found</h2>
        <Link to="/jobs">
          <Button variant="link">Back to jobs</Button>
        </Link>
      </div>
    );
  }

  const evaluation = call.ai_evaluation as CallEvaluation | null;
  const isScorableEvaluation = evaluation?.status === "completed_evaluation";

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col gap-3">
        <Link
          to={`/jobs/${call.job_id}`}
          className="flex items-center text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back to Job
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-3xl font-bold tracking-tight">Interview Call</h2>
            <p className="text-muted-foreground">
              Review the transcript, recording, and evaluation for this interview.
            </p>
          </div>
          <Badge variant="outline" className="px-3 py-1 text-sm capitalize">
            {call.status.replace("_", " ")}
          </Badge>
        </div>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <PhoneCall className="h-4 w-4 text-primary" />
              Phone Number
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tracking-tight">
            {call.phone_number}
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Timer className="h-4 w-4 text-primary" />
              Duration
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tracking-tight">
            {call.duration_seconds ? `${call.duration_seconds}s` : "—"}
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <UserRound className="h-4 w-4 text-primary" />
              Overall Score
            </CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold tracking-tight">
            {typeof evaluation?.overall_score === "number" ? `${evaluation.overall_score}/10` : "N/A"}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <PhoneCall className="h-4 w-4 text-primary" />
              Provider
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold tracking-tight uppercase">
            {call.provider}
          </CardContent>
        </Card>
        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Cpu className="h-4 w-4 text-primary" />
              Runtime
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold tracking-tight capitalize">
            {call.voice_runtime.replace(/_/g, " ")}
          </CardContent>
        </Card>
        <Card className="border-border/50 bg-card/70">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <DollarSign className="h-4 w-4 text-primary" />
              Estimated Cost
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xl font-semibold tracking-tight">
            {typeof call.cost_breakdown?.estimated_total_usd === "number"
              ? `$${call.cost_breakdown.estimated_total_usd.toFixed(4)}`
              : "—"}
          </CardContent>
        </Card>
      </div>

      {["queued", "ringing", "in_progress"].includes(call.status) && (
        <CallProgressIndicator
          callId={call.id}
          initialCall={call}
          onUpdate={(updatedCall) => setCall(updatedCall)}
        />
      )}

      {/* Browser-simulator shortcut — lets devs (re)open the iPhone simulator popup
          for any active browser-provider call directly from the call detail page. */}
      {call.provider === "browser" &&
        ["queued", "ringing", "in_progress"].includes(call.status) && (
        <div className="flex items-center gap-3 rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-5 py-4">
          <PhoneCall className="h-5 w-5 text-indigo-400 shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-indigo-300">
              Browser Simulator active
            </p>
            <p className="text-xs text-indigo-400/70">
              Open the candidate-side call window to speak or listen.
            </p>
          </div>
          <Button
            size="sm"
            className="shrink-0 bg-indigo-600 hover:bg-indigo-500 text-white"
            onClick={() => {
              const url = `${window.location.origin}/sim/call/${call.id}`;
              const W = 480, H = 960;
              const left = Math.round((screen.width  - W) / 2);
              const top  = Math.round((screen.height - H) / 2);
              const popup = window.open(
                url,
                "recruiteai_simulator",
                `width=${W},height=${H},left=${left},top=${top},resizable=no,scrollbars=no,toolbar=no,menubar=no,location=no,status=no`,
              );
              if (popup) popup.focus();
              else window.open(url, "_blank", "noopener");
            }}
          >
            Open Simulator ↗
          </Button>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          {/* Call Recording — feature-rich WaveSurfer player */}
          <AudioPlayer
            audioUrl={recordingUrl}
            audioLoading={recordingLoading}
            callStartedAt={call.started_at?.toString()}
            durationSeconds={call.duration_seconds}
            transcript={transcriptLines as TranscriptEntry[]}
            onActiveSegmentChange={setActiveSegmentId}
            onSeekToTranscriptEntry={(seekFn) => {
              seekToTranscriptRef.current = seekFn;
            }}
          />

          {/* Transcript — below recording */}
          <Card className="border-border/50 bg-card/70">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <CardTitle>Transcript</CardTitle>
                {isLive && (
                  <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-600">
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse inline-block" />
                    Live
                  </span>
                )}
              </div>
              <Button onClick={evaluateCall} disabled={isEvaluating || !call.transcript}>
                {isEvaluating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Evaluating
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    {evaluation ? "Re-evaluate" : "Run Evaluation"}
                  </>
                )}
              </Button>
            </CardHeader>
            <CardContent>
              {transcriptLines.length > 0 ? (
                <div className="relative group">
                  {/* Fading Edge Effects */}
                  <div className="absolute top-0 left-0 right-0 h-10 bg-gradient-to-b from-card to-transparent z-10 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-card to-transparent z-10 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                  
                  <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar py-2">
                    {transcriptLines.map((line) => {
                      const isAssistant = /^ai|assistant$/i.test(line.speaker);
                      const isActive = activeSegmentId === line.id;
                      
                      return (
                        <div
                          key={line.id}
                          id={`transcript-line-${line.id}`}
                          onClick={() => {
                            if (seekToTranscriptRef.current) {
                              seekToTranscriptRef.current(line as TranscriptEntry);
                            }
                          }}
                          className={`group/line relative rounded-xl border p-4 text-sm leading-7 transition-all cursor-pointer hover:shadow-md ${
                            isActive
                              ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/20 scale-[1.01] z-20"
                              : isAssistant
                              ? "border-primary/20 bg-primary/5 hover:bg-primary/8"
                              : "border-border/50 bg-background/60 hover:bg-background/80"
                          }`}
                        >
                          <div className="mb-1 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className={`text-xs font-bold uppercase tracking-wide ${
                                isActive ? "text-primary" : "text-muted-foreground"
                              }`}>
                                {line.speaker}
                              </span>
                              {isActive && (
                                <span className="flex h-1.5 w-1.5">
                                  <span className="animate-ping absolute inline-flex h-1.5 w-1.5 rounded-full bg-primary opacity-75"></span>
                                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary"></span>
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3">
                              {line.timestamp && (
                                <span className="text-[10px] font-medium text-muted-foreground/60 tabular-nums">
                                  {new Date(line.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                </span>
                              )}
                              <Play className={`h-3 w-3 transition-opacity ${
                                isActive ? "text-primary opacity-100" : "text-muted-foreground opacity-0 group-hover/line:opacity-100"
                              }`} />
                            </div>
                          </div>
                          <div className={`transition-colors ${isActive ? "text-foreground font-medium" : "text-foreground/90"}`}>
                            {line.text}
                          </div>
                        </div>
                      );
                    })}
                    <div ref={transcriptBottomRef} />
                  </div>

                  <div className="absolute bottom-0 left-0 right-0 h-6 bg-gradient-to-t from-card to-transparent z-10 pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-6 text-sm text-muted-foreground">
                  Transcript is not available yet for this call.
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/70">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PieChartIcon className="h-4 w-4 text-primary" />
                Cost Analytics
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[240px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={[
                        { name: "LLM", value: call.cost_breakdown?.costs?.llm_usd || 0 },
                        { name: "STT", value: call.cost_breakdown?.costs?.stt_usd || 0 },
                        { name: "TTS", value: call.cost_breakdown?.costs?.tts_usd || 0 },
                        { name: "Telephony", value: call.cost_breakdown?.costs?.telephony_usd || 0 },
                      ].filter(d => d.value > 0)}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {[
                        "#8884d8", // LLM - Purple
                        "#82ca9d", // STT - Green
                        "#ffc658", // TTS - Yellow
                        "#ff8042", // Telephony - Orange
                      ].map((color, index) => (
                        <Cell key={`cell-${index}`} fill={color} stroke="none" />
                      ))}
                    </Pie>
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}
                      formatter={(value: any) => [`$${Number(value).toFixed(6)}`, 'Cost']}
                    />
                    <Legend verticalAlign="bottom" height={36} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/70">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChartIcon className="h-4 w-4 text-primary" />
                Turn Analysis
              </CardTitle>
            </CardHeader>

            <CardContent>
              {!turnAnalysis ? (
                <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-6 text-sm text-muted-foreground text-center">
                  <MessageSquare className="mx-auto h-8 w-8 mb-2 opacity-20" />
                  No conversation messages recorded for this call.
                </div>
              ) : (
                <div className="space-y-8">
                  {/* Summary stat cards */}
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {[
                      { label: "AI Turns", value: turnAnalysis.assistant_turns, icon: <Cpu className="h-3.5 w-3.5" /> },
                      { label: "Candidate Turns", value: turnAnalysis.candidate_turns, icon: <UserRound className="h-3.5 w-3.5" /> },
                      { label: "Avg AI Words", value: turnAnalysis.avg_assistant_words, icon: <Activity className="h-3.5 w-3.5" /> },
                      { label: "Avg Candidate Words", value: turnAnalysis.avg_candidate_words, icon: <MessageSquare className="h-3.5 w-3.5" /> },
                    ].map(({ label, value, icon }) => (
                      <div key={label} className="rounded-lg border border-border/40 bg-background/40 p-3 space-y-1">
                        <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                          {icon}{label}
                        </div>
                        <div className="text-xl font-black tracking-tight">{value}</div>
                      </div>
                    ))}
                  </div>

                  {/* Response time stats */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-lg border border-border/40 bg-background/40 p-3 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                        <Timer className="h-3.5 w-3.5" />Avg AI Response Time
                      </div>
                      <div className="text-xl font-black tracking-tight">
                        {turnAnalysis.avg_ai_response_ms !== null ? fmtMs(turnAnalysis.avg_ai_response_ms) : "—"}
                      </div>
                    </div>
                    <div className="rounded-lg border border-border/40 bg-background/40 p-3 space-y-1">
                      <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                        <Timer className="h-3.5 w-3.5" />Avg Candidate Response Time
                      </div>
                      <div className="text-xl font-black tracking-tight">
                        {turnAnalysis.avg_candidate_response_ms !== null ? fmtMs(turnAnalysis.avg_candidate_response_ms) : "—"}
                      </div>
                    </div>
                  </div>

                  {/* Words per turn chart */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <MessageSquare className="h-4 w-4" />
                      Words per Turn
                    </div>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={turnAnalysis.turns}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                          <XAxis dataKey="turn" tick={{ fontSize: 11 }} label={{ value: "Turn", position: "insideBottom", offset: -5 }} />
                          <YAxis fontSize={12} />
                          <Tooltip
                            contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                            formatter={(value: number, _: string, entry: any) => [
                              `${value} words`,
                              entry.payload.role === "assistant" ? "AI" : "Candidate",
                            ]}
                            labelFormatter={(label) => `Turn ${label}`}
                          />
                          <Bar
                            dataKey="words"
                            radius={[4, 4, 0, 0]}
                            fill="#8884d8"
                          >
                            {turnAnalysis.turns.map((t, i) => (
                              <Cell key={i} fill={t.role === "assistant" ? "#8884d8" : "#82ca9d"} />
                            ))}
                          </Bar>
                          <Legend
                            verticalAlign="top"
                            height={28}
                            content={() => (
                              <div className="flex items-center gap-4 justify-end text-xs text-muted-foreground pb-1">
                                <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#8884d8]" />AI</span>
                                <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#82ca9d]" />Candidate</span>
                              </div>
                            )}
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  {/* Response gap chart */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Activity className="h-4 w-4" />
                      Response Time per Turn (ms)
                    </div>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={turnAnalysis.turns.filter((t) => t.gap_ms !== null)}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                          <XAxis dataKey="turn" tick={{ fontSize: 11 }} label={{ value: "Turn", position: "insideBottom", offset: -5 }} />
                          <YAxis fontSize={12} tickFormatter={(v) => `${v}ms`} />
                          <Tooltip
                            contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }}
                            formatter={(value: number, _: string, entry: any) => [
                              fmtMs(value),
                              entry.payload.role === "assistant" ? "AI response time" : "Candidate response time",
                            ]}
                            labelFormatter={(label) => `Turn ${label}`}
                          />
                          <Bar dataKey="gap_ms" radius={[4, 4, 0, 0]}>
                            {turnAnalysis.turns
                              .filter((t) => t.gap_ms !== null)
                              .map((t, i) => (
                                <Cell key={i} fill={t.role === "assistant" ? "#8884d8" : "#82ca9d"} />
                              ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/70">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Radio className="h-4 w-4 text-primary" />
                Runtime Breakdown
              </CardTitle>
            </CardHeader>


            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-4 py-3">
                <span className="text-muted-foreground">LLM</span>
                <span>
                  {typeof call.cost_breakdown?.costs?.llm_usd === "number"
                    ? `$${call.cost_breakdown.costs.llm_usd.toFixed(4)}`
                    : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-4 py-3">
                <span className="text-muted-foreground">STT</span>
                <span>
                  {typeof call.cost_breakdown?.costs?.stt_usd === "number"
                    ? `$${call.cost_breakdown.costs.stt_usd.toFixed(4)}`
                    : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-4 py-3">
                <span className="text-muted-foreground">TTS</span>
                <span>
                  {typeof call.cost_breakdown?.costs?.tts_usd === "number"
                    ? `$${call.cost_breakdown.costs.tts_usd.toFixed(4)}`
                    : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border/50 bg-background/50 px-4 py-3">
                <span className="text-muted-foreground">Telephony</span>
                <span>
                  {typeof call.cost_breakdown?.costs?.telephony_usd === "number"
                    ? `$${call.cost_breakdown.costs.telephony_usd.toFixed(4)}`
                    : "—"}
                </span>
              </div>
            </CardContent>
          </Card>

          {call.latency_metrics && Object.keys(call.latency_metrics).length > 0 && (() => {
            const deltas = computeLatencyDeltas(call.latency_metrics as Record<string, string>);
            return (
              <Card className="border-border/50 bg-card/70">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Timer className="h-4 w-4 text-primary" />
                    Latency Benchmarks
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {deltas.map(({ key, label, absoluteTime, deltaFromStartMs, deltaFromPreviousMs }) => (
                    <div key={key} className="rounded-lg border border-border/50 bg-background/50 px-4 py-3">
                      <div className="flex items-center justify-between">
                        <span className="capitalize text-muted-foreground">{label}</span>
                        <span className="font-mono text-xs tabular-nums">
                          {fmtMs(deltaFromStartMs)}
                          {deltaFromPreviousMs !== null && deltaFromStartMs !== null && deltaFromPreviousMs !== deltaFromStartMs && (
                            <span className="ml-2 text-[10px] text-muted-foreground">
                              (+{fmtMs(deltaFromPreviousMs)})
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="mt-1 text-[10px] text-muted-foreground font-mono">
                        {new Date(absoluteTime).toLocaleTimeString(undefined, { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit", fractionalSecondDigits: 3 })}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            );
          })()}
        </div>


        <Card className="border-border/50 bg-card/70">
          <CardHeader>
            <CardTitle>AI Evaluation</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {evaluation ? (
              <>
                <div className="rounded-xl border border-primary/20 bg-primary/5 p-4">
                  <div className="text-sm text-muted-foreground">Recommendation</div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge
                      variant="outline"
                      className={`whitespace-nowrap capitalize ${recommendationClasses[evaluation.recommendation] ?? recommendationClasses.insufficient_data}`}
                    >
                      {evaluation.recommendation?.replaceAll("_", " ")}
                    </Badge>
                    <Badge variant="outline" className="whitespace-nowrap border-border/60 text-muted-foreground">
                      {nonScorableLabels[evaluation.status] ?? evaluation.status?.replaceAll("_", " ")}
                    </Badge>
                    <Badge variant="outline" className="whitespace-nowrap border-border/60 text-muted-foreground capitalize">
                      {evaluation.confidence} confidence
                    </Badge>
                  </div>
                </div>

                {isScorableEvaluation ? (
                  <div className="space-y-3">
                    {scoreItems.map(({ key, label }) => {
                      const score = evaluation[key];
                      if (typeof score !== "number") return null;
                      return (
                        <div key={key} className="space-y-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className="text-muted-foreground">{label}</span>
                            <span className="font-medium">{score}/10</span>
                          </div>
                          <div className="h-2 rounded-full bg-muted">
                            <div
                              className="h-2 rounded-full bg-primary"
                              style={{ width: `${score * 10}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-4 text-sm text-muted-foreground">
                    This call did not produce enough reliable evidence for a full scored evaluation.
                  </div>
                )}

                {!isScorableEvaluation && evaluation.behavioral_summary ? (
                  <div className="space-y-2">
                    <div className="text-sm font-medium">Why It Was Not Scored</div>
                    <p className="text-sm leading-6 text-muted-foreground">
                      {evaluation.behavioral_summary}
                    </p>
                  </div>
                ) : null}

                <div className="space-y-2">
                  <div className="text-sm font-medium">Remarks</div>
                  <p className="text-sm leading-6 text-muted-foreground">
                    {evaluation.remarks}
                  </p>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Strengths</div>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {evaluation.strengths.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>

                <div className="space-y-2">
                  <div className="text-sm font-medium">Areas to Improve</div>
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {evaluation.weaknesses.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-6 text-sm text-muted-foreground">
                No evaluation has been generated for this call yet.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
