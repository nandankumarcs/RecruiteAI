import { useEffect, useMemo, useState } from "react"
import { Briefcase, CirclePause, FolderKanban, ShieldCheck } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import type { Job } from "@/lib/jobs"

const cards = [
  {
    key: "total",
    label: "Total Jobs",
    icon: FolderKanban,
    tint: "border-sky-500/20 bg-sky-500/5 text-sky-500",
  },
  {
    key: "active",
    label: "Active Jobs",
    icon: Briefcase,
    tint: "border-emerald-500/20 bg-emerald-500/5 text-emerald-500",
  },
  {
    key: "paused",
    label: "Paused Jobs",
    icon: CirclePause,
    tint: "border-amber-500/20 bg-amber-500/5 text-amber-500",
  },
  {
    key: "closed",
    label: "Closed Jobs",
    icon: ShieldCheck,
    tint: "border-fuchsia-500/20 bg-fuchsia-500/5 text-fuchsia-500",
  },
] as const

export function Dashboard() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    const fetchJobs = async () => {
      try {
        setLoading(true)
        setError("")
        const response = await api.get<Job[]>("/jobs")
        setJobs(response.data)
      } catch (err) {
        console.error("Failed to fetch dashboard jobs", err)
        setError("Could not load dashboard metrics right now.")
      } finally {
        setLoading(false)
      }
    }

    void fetchJobs()
  }, [])

  const stats = useMemo(
    () => ({
      total: jobs.length,
      active: jobs.filter((job) => job.status === "active").length,
      paused: jobs.filter((job) => job.status === "paused").length,
      closed: jobs.filter((job) => job.status === "closed").length,
    }),
    [jobs]
  )

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">
          A quick view of the job pipeline currently managed in RecruiteAI.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ key, label, icon: Icon, tint }) => (
          <Card key={key} className={`overflow-hidden border shadow-lg transition-all duration-300 ${tint}`}>
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
                {loading ? "..." : stats[key]}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {loading ? "Loading from API" : "Live from your jobs API"}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
