import { useEffect, useMemo, useState } from "react"
import { Briefcase, Calendar, Eye, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react"
import { useNavigate, Link } from "react-router-dom"

import { api } from "@/lib/api"
import type { Job, JobStatus } from "@/lib/jobs"
import { Button } from "@/components/ui/button"
import { DataTable } from "@/components/ui/DataTable"
import type { ColumnDef } from "@/components/ui/DataTable"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { DeleteConfirmDialog } from "@/components/ui/DeleteConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { JobDialog } from "@/components/jobs/JobDialog"
import { useToast } from "@/context/ToastContext"


function jobColumns(
  navigate: (path: string) => void,
  openEditDialog: (job: Job) => void,
  setJobToDelete: (job: Job) => void,
): ColumnDef<Job>[] {
  return [
    {
      key: "title",
      label: "Job Title",
      sortKey: "title",
      className: "py-6 px-6",
      headerClassName: "py-6 px-6",
      cell: (job) => (
        <Link
          to={`/jobs/${job.id}`}
          className="font-black tracking-tight text-lg hover:text-primary transition-colors"
        >
          {job.title}
        </Link>
      ),
    },
    {
      key: "status",
      label: "Status",
      sortKey: "status",
      className: "py-6",
      headerClassName: "py-6",
      cell: (job) => (
        <Badge
          variant="outline"
          className={`font-black tracking-tight uppercase px-3 py-1 rounded-lg shadow-sm ${
            job.status === "active"
              ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/20"
              : job.status === "paused"
              ? "bg-amber-500/15 text-amber-500 border-amber-500/20"
              : "bg-slate-500/15 text-slate-500 border-slate-500/20"
          }`}
        >
          {job.status}
        </Badge>
      ),
    },
    {
      key: "requirements",
      label: "Requirements",
      className: "max-w-xs truncate text-muted-foreground font-medium py-6",
      headerClassName: "py-6",
      cell: (job) => job.requirements || "No requirements added",
    },
    {
      key: "created",
      label: "Created",
      sortKey: "created_at",
      className: "text-muted-foreground font-medium py-6",
      headerClassName: "py-6",
      cell: (job) => (
        <div className="flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          {new Date(job.created_at).toLocaleDateString()}
        </div>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      headerClassName: "text-right py-6 px-6",
      className: "text-right py-6 px-6",
      cell: (job) => (
        <div className="flex items-center justify-end gap-2">
          <Button
            variant="secondary"
            size="icon-sm"
            className="rounded-lg shadow-sm border-border/50"
            onClick={() => navigate(`/jobs/${job.id}`)}
          >
            <Eye className="size-4" />
          </Button>
          <Button
            variant="secondary"
            size="icon-sm"
            className="rounded-lg shadow-sm border-border/50"
            onClick={() => openEditDialog(job)}
          >
            <Pencil className="size-4" />
          </Button>
          <Button
            variant="destructive"
            size="icon-sm"
            className="rounded-lg shadow-sm shadow-destructive/10"
            onClick={() => setJobToDelete(job)}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      ),
    },
  ]
}

export function Jobs() {
  const { toast } = useToast()
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [editingJob, setEditingJob] = useState<Job | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | JobStatus>("all")
  const [jobToDelete, setJobToDelete] = useState<Job | null>(null)
  const [sortBy, setSortBy] = useState("created_at")
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc")
  const [currentPage, setCurrentPage] = useState(1)
  const PAGE_SIZE = 20

  const fetchJobs = async () => {
    try {
      setLoading(true)
      setError("")
      const response = await api.get<Job[]>("/jobs")
      setJobs(response.data)
    } catch (error) {
      console.error("Failed to fetch jobs", error)
      setError("Could not load jobs right now.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchJobs()
  }, [])

  const filteredJobs = useMemo(() => {
    const filtered = jobs.filter((job) => {
      const matchesQuery =
        job.title.toLowerCase().includes(query.toLowerCase()) ||
        job.description.toLowerCase().includes(query.toLowerCase())
      const matchesStatus = statusFilter === "all" || job.status === statusFilter
      return matchesQuery && matchesStatus
    })

    filtered.sort((a, b) => {
      const aVal = a[sortBy as keyof Job] ?? ""
      const bVal = b[sortBy as keyof Job] ?? ""
      const cmp = String(aVal).localeCompare(String(bVal))
      return sortOrder === "asc" ? cmp : -cmp
    })

    return filtered
  }, [jobs, query, statusFilter, sortBy, sortOrder])

  const pagedJobs = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE
    return filteredJobs.slice(start, start + PAGE_SIZE)
  }, [filteredJobs, currentPage])

  const handleSortChange = (newSortBy: string, newSortOrder: "asc" | "desc") => {
    setSortBy(newSortBy)
    setSortOrder(newSortOrder)
    setCurrentPage(1)
  }

  const openCreateDialog = () => {
    setIsCreateDialogOpen(true)
  }

  const openEditDialog = (job: Job) => {
    setEditingJob(job)
  }

  const handleDelete = async () => {
    if (!jobToDelete) return

    try {
      setSubmitting(true)
      await api.delete(`/jobs/${jobToDelete.id}`)
      toast({
        variant: "success",
        title: "Job deleted",
        description: "The job posting has been removed.",
      })
      setJobToDelete(null)
      await fetchJobs()
    } catch (error) {
      console.error("Failed to delete job", error)
      toast({
        variant: "error",
        title: "Delete failed",
        description: "Could not delete the selected job.",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">Jobs</h2>
          <p className="text-muted-foreground">
            Manage your open roles, keep statuses current, and update job briefs in place.
          </p>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="relative min-w-0 sm:w-72">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => { setQuery(event.target.value); setCurrentPage(1) }}
              placeholder="Search jobs"
              className="pl-9"
            />
          </div>
          <Select
            value={statusFilter}
            onValueChange={(value: "all" | JobStatus) => { setStatusFilter(value); setCurrentPage(1) }}
          >
            <SelectTrigger className="w-full sm:w-40">
              <SelectValue placeholder="Filter status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="paused">Paused</SelectItem>
              <SelectItem value="closed">Closed</SelectItem>
            </SelectContent>
          </Select>

          <Button className="rounded-lg shadow-sm shadow-primary/10" onClick={openCreateDialog}>
            <Plus className="mr-2 h-4 w-4" /> Create Job
          </Button>
        </div>
      </div>

      <JobDialog
        isOpen={isCreateDialogOpen}
        onClose={() => setIsCreateDialogOpen(false)}
        onSuccess={fetchJobs}
      />

      {error && !isCreateDialogOpen && !editingJob ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {/* Desktop Table View */}
      <div className="hidden md:block">
        {loading ? (
          <div className="rounded-lg border border-border/40 bg-card/40 h-64 flex flex-col items-center justify-center gap-3">
            <div className="h-10 w-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
            <p className="text-muted-foreground font-medium animate-pulse">Loading jobs...</p>
          </div>
        ) : (
          <DataTable<Job>
            columns={jobColumns(navigate, openEditDialog, setJobToDelete)}
            data={pagedJobs}
            rowKey={(j) => j.id}
            sortBy={sortBy}
            sortOrder={sortOrder}
            onSortChange={handleSortChange}
            currentPage={currentPage}
            pageSize={PAGE_SIZE}
            totalItems={filteredJobs.length}
            onPageChange={setCurrentPage}
            emptyIcon={<Briefcase className="h-8 w-8 text-muted-foreground" />}
            emptyTitle="No jobs found"
            emptyDescription={
              jobs.length === 0
                ? "Create your first job to start receiving resumes."
                : "Try adjusting your search or filters."
            }
          />
        )}
      </div>

      {/* Mobile Grid View */}
      <div className="md:hidden space-y-4">
        {loading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-48 rounded-lg bg-card/40 border border-border/40 animate-pulse" />
          ))
        ) : filteredJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 text-center space-y-4 rounded-lg bg-card/40 border border-border/40">
             <div className="p-4 bg-muted/50 rounded-full">
                <Briefcase className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-lg font-bold">No jobs found</p>
          </div>
        ) : (
          filteredJobs.map((job) => (
            <div 
              key={job.id} 
              className="p-6 rounded-lg bg-card/40 border border-border/40 backdrop-blur-xl shadow-md active:scale-[0.98] transition-all space-y-4"
              onClick={() => navigate(`/jobs/${job.id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="space-y-1">
                  <h3 className="font-black tracking-tight text-xl">{job.title}</h3>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground font-medium">
                    <Calendar className="h-4 w-4" />
                    {new Date(job.created_at).toLocaleDateString()}
                  </div>
                </div>
                <Badge
                  variant="outline"
                  className={`font-black tracking-tight uppercase px-3 py-1 rounded-lg shadow-sm ${
                    job.status === "active" ? "bg-emerald-500/15 text-emerald-500 border-emerald-500/20" :
                    job.status === "paused" ? "bg-amber-500/15 text-amber-500 border-amber-500/20" :
                    "bg-slate-500/15 text-slate-500 border-slate-500/20"
                  }`}
                >
                  {job.status}
                </Badge>
              </div>
              
              <p className="text-sm text-muted-foreground line-clamp-2 font-medium bg-background/30 p-4 rounded-lg">
                {job.requirements || "No requirements added"}
              </p>

              <div className="flex items-center gap-2 pt-2">
                <Button 
                  className="flex-1 h-12 rounded-lg font-bold bg-primary/10 text-primary hover:bg-primary/20 border-0"
                  onClick={(e) => {
                    e.stopPropagation()
                    navigate(`/jobs/${job.id}`)
                  }}
                >
                  VIEW DETAIL
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                    <Button variant="secondary" size="icon" className="h-12 w-12 rounded-lg shadow-sm border-border/50">
                      <MoreHorizontal className="h-5 w-5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-48 rounded-lg p-2 border-border/40 bg-background/95 backdrop-blur-2xl shadow-md">
                    <DropdownMenuItem 
                      className="rounded-lg h-11 font-bold"
                      onClick={() => openEditDialog(job)}
                    >
                      <Pencil className="mr-2 h-4 w-4" /> Edit Job
                    </DropdownMenuItem>
                    <DropdownMenuItem 
                      className="rounded-lg h-11 font-bold text-destructive"
                      onClick={() => setJobToDelete(job)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" /> Delete Job
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
          ))
        )}
      </div>

      <DeleteConfirmDialog
        isOpen={jobToDelete !== null}
        onClose={() => setJobToDelete(null)}
        onConfirm={handleDelete}
        isLoading={submitting}
        title="Delete Job Posting?"
        description={`Are you sure you want to delete "${jobToDelete?.title}"? All associated resumes and interview data will be permanently removed.`}
      />

      <JobDialog
        job={editingJob}
        isOpen={editingJob !== null}
        onClose={() => setEditingJob(null)}
        onSuccess={fetchJobs}
      />
    </div>
  )
}

