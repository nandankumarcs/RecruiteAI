import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Loader2,
  PhoneCall,
  Sparkles,
  Timer,
  UserRound,
} from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CallProgressIndicator } from "@/components/calls/CallProgressIndicator";
import type { CallRecord } from "@/lib/calls";

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

type CallDetailData = CallRecord;

const scoreItems = [
  { key: "technical_score", label: "Technical" },
  { key: "communication_score", label: "Communication" },
  { key: "experience_score", label: "Experience" },
] as const;

export function CallDetail() {
  const { callId } = useParams<{ callId: string }>();
  const [call, setCall] = useState<CallDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);

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
      } finally {
        setLoading(false);
      }
    };

    void fetchCall();
  }, [callId]);

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
    } catch (err) {
      console.error("Failed to evaluate call", err);
      setError("Evaluation could not be completed yet. A transcript may still be missing.");
    } finally {
      setIsEvaluating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
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
              Review status, transcript, and AI evaluation for this call.
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

      {["queued", "ringing", "in_progress"].includes(call.status) && (
        <CallProgressIndicator
          callId={call.id}
          initialCall={call}
          onUpdate={(updatedCall) => setCall(updatedCall)}
        />
      )}

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="border-border/50 bg-card/70">
          <CardHeader className="flex flex-row items-center justify-between gap-4">
            <div>
              <CardTitle>Transcript</CardTitle>
            </div>
            <Button
              onClick={evaluateCall}
              disabled={isEvaluating || !call.transcript}
            >
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
            {call.transcript ? (
              <div className="rounded-xl border border-border/50 bg-background/60 p-4 text-sm leading-7 text-muted-foreground whitespace-pre-wrap">
                {call.transcript}
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
                        <span className="font-medium">
                          {evaluation[key]}/10
                        </span>
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
