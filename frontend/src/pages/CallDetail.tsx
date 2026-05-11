import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Cpu,
  DollarSign,
  Headphones,
  Loader2,
  PhoneCall,
  Radio,
  Sparkles,
  Timer,
  UserRound,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Activity,
  ExternalLink,
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

interface CallEvaluation extends Record<string, unknown> {
  schema_version: string;
  overall_score: number;
  technical_score: number;
  communication_score: number;
  experience_score: number;
  remarks: string;
  strengths: string[];
  weaknesses: string[];
  recommendation: string;
}

interface TranscriptLine {
  id: string;
  speaker: string;
  text: string;
}

interface CallAnalytics {
  turns: Array<{
    start_time: string;
    end_time: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
    name: string;
    run_url: string | null;
  }>;

  summary: {
    total_latency_ms: number;
    total_tokens: number;
    total_cost_usd: number;
    turn_count: number;
  };
}

type CallDetailData = CallRecord;


const scoreItems = [
  { key: "technical_score", label: "Technical" },
  { key: "communication_score", label: "Communication" },
  { key: "experience_score", label: "Experience" },
] as const;

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
  const [analytics, setAnalytics] = useState<CallAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);


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

  useEffect(() => {
    if (!callId || call?.status !== "completed") return;

    const fetchAnalytics = async () => {
      try {
        setAnalyticsLoading(true);
        const response = await api.get<CallAnalytics>(`/calls/${callId}/analytics`);
        setAnalytics(response.data);
      } catch (err) {
        console.error("Failed to fetch call analytics", err);
      } finally {
        setAnalyticsLoading(false);
      }
    };

    void fetchAnalytics();
  }, [callId, call?.status]);


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

  const transcriptLines = useMemo(
    () => parseTranscript(call?.transcript ?? null),
    [call?.transcript]
  );

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
            {evaluation ? `${evaluation.overall_score}/10` : "Pending"}
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

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <Card className="border-border/50 bg-card/70">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <div>
                <CardTitle>Transcript</CardTitle>
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
                <div className="space-y-3">
                  {transcriptLines.map((line) => {
                    const isAssistant = /^ai|assistant$/i.test(line.speaker);
                    return (
                      <div
                        key={line.id}
                        className={`rounded-xl border p-4 text-sm leading-7 ${
                          isAssistant
                            ? "border-primary/20 bg-primary/5"
                            : "border-border/50 bg-background/60"
                        }`}
                      >
                        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                          {line.speaker}
                        </div>
                        <div className="text-foreground">{line.text}</div>
                      </div>
                    );
                  })}
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
                <Headphones className="h-4 w-4 text-primary" />
                Call Recording
              </CardTitle>
            </CardHeader>
            <CardContent>
              {recordingLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-10 w-full rounded-lg" />
                  <Skeleton className="h-4 w-40" />
                </div>
              ) : recordingUrl ? (
                <div className="space-y-3">
                  <audio controls className="w-full">
                    <source src={recordingUrl} />
                  </audio>
                  <p className="text-xs text-muted-foreground">
                    Playback is loaded through the authenticated backend proxy.
                  </p>
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-6 text-sm text-muted-foreground">
                  No recording is available for this call yet.
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
                      formatter={(value: number) => [`$${value.toFixed(6)}`, 'Cost']}
                    />
                    <Legend verticalAlign="bottom" height={36} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/70">
            <CardHeader className="flex flex-row items-center justify-between gap-4">
              <CardTitle className="flex items-center gap-2">
                <BarChartIcon className="h-4 w-4 text-primary" />
                Turn Analysis
              </CardTitle>
              {analytics?.turns?.[0]?.run_url && (
                <a 
                  href={analytics.turns[0].run_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="inline-flex items-center text-xs text-muted-foreground hover:text-primary transition-colors"
                >
                  <ExternalLink className="mr-1 h-3 w-3" />
                  View Full Trace
                </a>
              )}
            </CardHeader>

            <CardContent>
              {analyticsLoading ? (
                <div className="flex h-48 items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : analytics && analytics.turns.length > 0 ? (
                <div className="space-y-8">
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Activity className="h-4 w-4" />
                      Latency per Turn (ms)
                    </div>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analytics.turns}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                          <XAxis 
                            dataKey="start_time" 
                            tick={false}
                            label={{ value: 'Turn Sequence', position: 'insideBottom', offset: -5 }}
                          />
                          <YAxis fontSize={12} tickFormatter={(value) => `${value}ms`} />
                          <Tooltip
                            contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}
                            labelFormatter={(label) => new Date(label).toLocaleTimeString()}
                          />
                          <Bar dataKey="latency_ms" fill="#8884d8" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <DollarSign className="h-4 w-4" />
                      Cost per Turn (USD)
                    </div>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analytics.turns}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                          <XAxis 
                            dataKey="start_time" 
                            tick={false}
                            label={{ value: 'Turn Sequence', position: 'insideBottom', offset: -5 }}
                          />
                          <YAxis fontSize={12} tickFormatter={(value) => `$${value.toFixed(4)}`} />
                          <Tooltip
                            contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}
                            labelFormatter={(label) => new Date(label).toLocaleTimeString()}
                            formatter={(value: number) => [`$${value.toFixed(6)}`, 'Cost']}
                          />
                          <Bar dataKey="cost_usd" fill="#82ca9d" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                      <Cpu className="h-4 w-4" />
                      Tokens per Turn
                    </div>
                    <div className="h-[200px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analytics.turns}>
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                          <XAxis 
                            dataKey="start_time" 
                            tick={false}
                            label={{ value: 'Turn Sequence', position: 'insideBottom', offset: -5 }}
                          />
                          <YAxis fontSize={12} />
                          <Tooltip
                            contentStyle={{ backgroundColor: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: '8px' }}
                            labelFormatter={(label) => new Date(label).toLocaleTimeString()}
                          />
                          <Bar dataKey="input_tokens" name="Input" fill="#8884d8" stackId="a" />
                          <Bar dataKey="output_tokens" name="Output" fill="#82ca9d" stackId="a" />
                          <Legend verticalAlign="top" height={36}/>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              ) : (

                <div className="rounded-xl border border-dashed border-border/50 bg-background/40 p-6 text-sm text-muted-foreground text-center">
                  <Sparkles className="mx-auto h-8 w-8 mb-2 opacity-20" />
                  Detailed turn analytics are being aggregated from LangSmith. 
                  Check back in a few moments for the granular breakdown.
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
                  <div className="text-xl font-semibold capitalize">
                    {evaluation.recommendation}
                  </div>
                </div>

                <div className="space-y-3">
                  {scoreItems.map(({ key, label }) => (
                    <div key={key} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-muted-foreground">{label}</span>
                        <span className="font-medium">{evaluation[key]}/10</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div
                          className="h-2 rounded-full bg-primary"
                          style={{ width: `${evaluation[key] * 10}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>

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
