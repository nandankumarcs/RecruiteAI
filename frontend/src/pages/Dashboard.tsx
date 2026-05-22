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
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { TrendingUp } from "lucide-react";

interface DashboardMetrics {
  total_jobs: number;
  active_jobs: number;
  paused_jobs: number;
  closed_jobs: number;
  total_calls: number;
  active_calls: number;
  completed_calls: number;
  average_score: number | null;
  total_estimated_cost_usd: number | null;
  average_cost_per_call_usd: number | null;
  realtime_calls: number;
  pipeline_calls: number;
  v2_calls: number;
  average_latency_ms: number | null;
}

const jobCards = [
  {
    key: "total_jobs",
    label: "TOTAL JOBS",
    icon: FolderKanban,
    tint: "text-sky-500",
    helper: "Pipeline depth",
  },
  {
    key: "active_jobs",
    label: "ACTIVE ROLES",
    icon: Briefcase,
    tint: "text-emerald-500",
    helper: "Live & hiring",
  },
  {
    key: "paused_jobs",
    label: "PAUSED ROLES",
    icon: CirclePause,
    tint: "text-amber-500",
    helper: "On hold",
  },
  {
    key: "closed_jobs",
    label: "CLOSED ROLES",
    icon: ShieldCheck,
    tint: "text-slate-500",
    helper: "Hiring complete",
  },
] as const;

const callCards = [
  {
    key: "total_calls",
    label: "TOTAL CALLS",
    icon: PhoneCall,
    tint: "text-cyan-500",
    helper: "All time activity",
  },
  {
    key: "active_calls",
    label: "LIVE CALLS",
    icon: Waves,
    tint: "text-violet-500",
    helper: "In progress",
  },
  {
    key: "completed_calls",
    label: "SUCCESSFUL",
    icon: ShieldCheck,
    tint: "text-emerald-500",
    helper: "Calls finalized",
  },
  {
    key: "total_estimated_cost_usd",
    label: "EST. TOTAL COST",
    icon: Sparkles,
    tint: "text-rose-500",
    helper: "Observed spend",
  },
] as const;

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

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
      return <Skeleton className="h-10 w-20 rounded-lg" />;
    }

    if (!metrics) {
      return "—";
    }

    if (key === "average_score") {
      return metrics.average_score === null ? "—" : `${metrics.average_score.toFixed(1)}/10`;
    }
    if (key === "total_estimated_cost_usd") {
      return metrics.total_estimated_cost_usd === null
        ? "—"
        : `$${metrics.total_estimated_cost_usd.toFixed(3)}`;
    }

    if (key === "average_latency_ms") {
      return metrics.average_latency_ms === null ? "—" : `${Math.round(metrics.average_latency_ms)}ms`;
    }

    return metrics[key];

  };

  return (
    <div className="space-y-10 pb-12">

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-6 text-destructive font-bold flex items-center gap-4">
          <div className="p-2 bg-destructive/20 rounded-lg">⚠️</div>
          {error}
        </div>
      ) : null}

      <section className="space-y-6">
        <div className="flex items-center justify-between px-2">
          <div className="flex items-center gap-3">
             <h3 className="text-3xl font-black tracking-tighter">JOB PIPELINE</h3>
             <Badge variant="secondary" className="font-bold">LIVE</Badge>
          </div>
          <span className="text-sm text-muted-foreground font-medium flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-emerald-500" />
            REAL-TIME METRICS
          </span>
        </div>
        <motion.div 
          variants={container}
          initial="hidden"
          animate="show"
          className="grid gap-6 md:grid-cols-2 xl:grid-cols-4"
        >
          {jobCards.map(({ key, label, icon: Icon, tint, helper }) => (
            <motion.div key={key} variants={item}>
              <Card className="group relative overflow-hidden rounded-lg border-border/40 bg-card/40 backdrop-blur-xl p-8 shadow-md transition-all duration-500 hover:-translate-y-2 hover:bg-primary/5 active:scale-[0.98]">
                <div className={`absolute top-0 right-0 p-6 opacity-20 group-hover:opacity-100 transition-opacity duration-500 ${tint}`}>
                  <Icon className="h-12 w-12" />
                </div>
                <div className="relative z-10 space-y-6">
                  <div className="space-y-1">
                    <p className="text-xs font-black tracking-widest text-muted-foreground">{label}</p>
                    <div className="text-5xl font-black tracking-tighter">
                      {renderMetricValue(key)}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground font-medium flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full ${tint.replace('text', 'bg')}`} />
                    {helper}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section className="space-y-6">
        <div className="flex items-center justify-between px-2">
           <div className="flex items-center gap-3">
             <h3 className="text-3xl font-black tracking-tighter">CALL ACTIVITY</h3>
             <Badge variant="secondary" className="font-bold">SYSTEM</Badge>
          </div>
          <span className="text-sm text-muted-foreground font-medium">UPDATED MOMENTS AGO</span>
        </div>
        <motion.div 
          variants={container}
          initial="hidden"
          animate="show"
          className="grid gap-6 md:grid-cols-2 xl:grid-cols-4"
        >
          {callCards.map(({ key, label, icon: Icon, tint, helper }) => (
            <motion.div key={key} variants={item}>
              <Card className="group relative overflow-hidden rounded-lg border-border/40 bg-card/40 backdrop-blur-xl p-8 shadow-md transition-all duration-500 hover:-translate-y-2 hover:bg-primary/5 active:scale-[0.98]">
                <div className={`absolute top-0 right-0 p-6 opacity-20 group-hover:opacity-100 transition-opacity duration-500 ${tint}`}>
                  <Icon className="h-12 w-12" />
                </div>
                <div className="relative z-10 space-y-6">
                  <div className="space-y-1">
                    <p className="text-xs font-black tracking-widest text-muted-foreground">{label}</p>
                    <div className="text-5xl font-black tracking-tighter">
                      {renderMetricValue(key)}
                    </div>
                  </div>
                  <p className="text-sm text-muted-foreground font-medium flex items-center gap-2">
                    <span className={`h-1.5 w-1.5 rounded-full ${tint.replace('text', 'bg')}`} />
                    {helper}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </section>

      <section className="grid gap-6 xl:grid-cols-3">
        <Card className="rounded-lg border-border/40 bg-card/40 backdrop-blur-xl p-6 shadow-md">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-black tracking-tight">Runtime Mix</CardTitle>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Call V2</span>
              <span className="text-xl font-black">{metrics?.v2_calls ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">OpenAI Realtime</span>
              <span className="text-xl font-black">{metrics?.realtime_calls ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Deepgram Pipeline</span>
              <span className="text-xl font-black">{metrics?.pipeline_calls ?? 0}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-border/40 bg-card/40 backdrop-blur-xl p-6 shadow-md">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-black tracking-tight">Call Quality</CardTitle>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Average evaluation</span>
              <span className="text-xl font-black">
                {metrics?.average_score === null || metrics?.average_score === undefined
                  ? "—"
                  : `${metrics.average_score.toFixed(1)}/10`}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Completed calls</span>
              <span className="text-xl font-black">{metrics?.completed_calls ?? 0}</span>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-border/40 bg-card/40 backdrop-blur-xl p-6 shadow-md">
          <CardHeader className="p-0 pb-4">
            <CardTitle className="text-base font-black tracking-tight">Efficiency</CardTitle>
          </CardHeader>
          <CardContent className="p-0 space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Average cost / call</span>
              <span className="text-xl font-black">
                {metrics?.average_cost_per_call_usd === null || metrics?.average_cost_per_call_usd === undefined
                  ? "—"
                  : `$${metrics.average_cost_per_call_usd.toFixed(3)}`}
              </span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Live calls</span>
              <span className="text-xl font-black">{metrics?.active_calls ?? 0}</span>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/40 bg-background/40 px-4 py-3">
              <span className="text-sm font-semibold text-muted-foreground">Average Latency</span>
              <span className="text-xl font-black">
                {renderMetricValue("average_latency_ms")}
              </span>
            </div>
          </CardContent>
        </Card>

      </section>
    </div>
  );
}
