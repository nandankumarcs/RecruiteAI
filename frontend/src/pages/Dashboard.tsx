import { useEffect, useState } from "react";
import {
  Briefcase,
  CirclePause,
  FolderKanban,
  PhoneCall,
  ShieldCheck,
  Sparkles,
  Waves,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/context/ToastContext";

interface DashboardMetrics {
  total_jobs: number;
  active_jobs: number;
  paused_jobs: number;
  closed_jobs: number;
  total_calls: number;
  active_calls: number;
  completed_calls: number;
  average_score: number | null;
}

const jobCards = [
  {
    key: "total_jobs",
    label: "Total Jobs",
    icon: FolderKanban,
    tint: "border-sky-500/20 bg-sky-500/5 text-sky-500",
    helper: "Tracked roles in the pipeline",
  },
  {
    key: "active_jobs",
    label: "Active Jobs",
    icon: Briefcase,
    tint: "border-emerald-500/20 bg-emerald-500/5 text-emerald-500",
    helper: "Open roles accepting candidates",
  },
  {
    key: "paused_jobs",
    label: "Paused Jobs",
    icon: CirclePause,
    tint: "border-amber-500/20 bg-amber-500/5 text-amber-500",
    helper: "Roles waiting on the next step",
  },
  {
    key: "closed_jobs",
    label: "Closed Jobs",
    icon: ShieldCheck,
    tint: "border-fuchsia-500/20 bg-fuchsia-500/5 text-fuchsia-500",
    helper: "Finished or no longer hiring",
  },
] as const;

const callCards = [
  {
    key: "total_calls",
    label: "Total Calls",
    icon: PhoneCall,
    tint: "border-cyan-500/20 bg-cyan-500/5 text-cyan-500",
    helper: "All interview calls launched so far",
  },
  {
    key: "active_calls",
    label: "Active Calls",
    icon: Waves,
    tint: "border-violet-500/20 bg-violet-500/5 text-violet-500",
    helper: "Calls currently queued or in progress",
  },
  {
    key: "completed_calls",
    label: "Completed Calls",
    icon: ShieldCheck,
    tint: "border-emerald-500/20 bg-emerald-500/5 text-emerald-500",
    helper: "Finished calls with final outcomes",
  },
  {
    key: "average_score",
    label: "Average Score",
    icon: Sparkles,
    tint: "border-rose-500/20 bg-rose-500/5 text-rose-500",
    helper: "Mean AI evaluation score",
  },
] as const;

export function Dashboard() {
  const { toast } = useToast();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setLoading(true);
        setError("");
        const response = await api.get<DashboardMetrics>("/dashboard/metrics");
        setMetrics(response.data);
      } catch (err) {
        console.error("Failed to fetch dashboard metrics", err);
        setError("Could not load dashboard metrics right now.");
        toast({
          variant: "error",
          title: "Dashboard unavailable",
          description: "We couldn't load your latest recruiting metrics.",
        });
      } finally {
        setLoading(false);
      }
    };

    void fetchMetrics();
  }, [toast]);

  const renderMetricValue = (key: keyof DashboardMetrics) => {
    if (loading) {
      return <Skeleton className="h-9 w-16" />;
    }

    if (!metrics) {
      return "—";
    }

    if (key === "average_score") {
      return metrics.average_score === null ? "—" : `${metrics.average_score}/10`;
    }

    return metrics[key];
  };

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">
          A quick view of hiring activity, interview calls, and evaluation health in RecruiteAI.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Job Pipeline</h3>
          <span className="text-xs text-muted-foreground">Live from the backend</span>
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {jobCards.map(({ key, label, icon: Icon, tint, helper }) => (
            <Card
              key={key}
              className={`overflow-hidden border shadow-lg transition-all duration-300 ${tint}`}
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {label}
                </CardTitle>
                <div className="rounded-lg bg-background/40 p-2">
                  <Icon className="h-4 w-4" />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold tracking-tight">
                  {renderMetricValue(key)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Call Activity</h3>
          <span className="text-xs text-muted-foreground">Updated as calls complete</span>
        </div>
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {callCards.map(({ key, label, icon: Icon, tint, helper }) => (
            <Card
              key={key}
              className={`overflow-hidden border shadow-lg transition-all duration-300 ${tint}`}
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {label}
                </CardTitle>
                <div className="rounded-lg bg-background/40 p-2">
                  <Icon className="h-4 w-4" />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold tracking-tight">
                  {renderMetricValue(key)}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
