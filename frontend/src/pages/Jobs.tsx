import { useEffect, useMemo, useState } from "react"
import { Eye, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react"
import { useNavigate } from "react-router-dom"

import { api } from "@/lib/api"
import type { Job, JobStatus } from "@/lib/jobs"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"

type JobFormState = {
  title: string
  description: string
  requirements: string
  status: JobStatus
}

const initialFormState: JobFormState = {
  title: "",
  description: "",
  requirements: "",
  status: "active",
}

const statusClasses: Record<JobStatus, string> = {
  active: "border-emerald-500/20 bg-emerald-500/10 text-emerald-500",
  paused: "border-amber-500/20 bg-amber-500/10 text-amber-500",
  closed: "border-slate-500/20 bg-slate-500/20 text-slate-300",
}

export function Jobs() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [editingJob, setEditingJob] = useState<Job | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<"all" | JobStatus>("all")
  const [form, setForm] = useState<JobFormState>(initialFormState)

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
    return jobs.filter((job) => {
      const matchesQuery =
        job.title.toLowerCase().includes(query.toLowerCase()) ||
        job.description.toLowerCase().includes(query.toLowerCase())
      const matchesStatus =
        statusFilter === "all" ? true : job.status === statusFilter

      return matchesQuery && matchesStatus
    })
  }, [jobs, query, statusFilter])

  const openCreateDialog = () => {
    setForm(initialFormState)
    setEditingJob(null)
    setError("")
    setIsCreateDialogOpen(true)
  }

  const openEditDialog = (job: Job) => {
    setForm({
      title: job.title,
      description: job.description,
      requirements: job.requirements ?? "",
      status: job.status,
    })
    setEditingJob(job)
    setError("")
  }

  const closeDialogs = () => {
    setIsCreateDialogOpen(false)
    setEditingJob(null)
    setSubmitting(false)
    setForm(initialFormState)
  }

  const handleFormChange = <K extends keyof JobFormState>(key: K, value: JobFormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }))
  }

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    try {
      setSubmitting(true)
      setError("")

      const payload = {
        title: form.title,
        description: form.description,
        requirements: form.requirements || null,
        status: form.status,
      }

      if (editingJob) {
        await api.put(`/jobs/${editingJob.id}`, payload)
      } else {
        await api.post("/jobs", payload)
      }

      closeDialogs()
      await fetchJobs()
    } catch (error) {
      console.error("Failed to save job", error)
      setError("Could not save the job. Please try again.")
      setSubmitting(false)
    }
  }

  const handleDelete = async (job: Job) => {
    const confirmed = window.confirm(`Delete "${job.title}"? This cannot be undone.`)
    if (!confirmed) {
      return
    }

    try {
      await api.delete(`/jobs/${job.id}`)
      await fetchJobs()
    } catch (error) {
      console.error("Failed to delete job", error)
      setError("Could not delete the selected job.")
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
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search jobs"
              className="pl-9"
            />
          </div>
          <Select
            value={statusFilter}
            onValueChange={(value: "all" | JobStatus) => setStatusFilter(value)}
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

          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
              <Button className="shadow-lg shadow-primary/20" onClick={openCreateDialog}>
              <Plus className="mr-2 h-4 w-4" /> Create Job
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px] bg-card/95 backdrop-blur-xl border-border/50">
            <DialogHeader>
              <DialogTitle className="text-2xl font-bold">Create Job</DialogTitle>
              <DialogDescription>
                Post a new position to start receiving and screening resumes.
              </DialogDescription>
            </DialogHeader>
            <JobForm
              form={form}
              error={error}
              submitting={submitting}
              submitLabel="Create Job"
              onChange={handleFormChange}
              onSubmit={handleSubmit}
              onCancel={closeDialogs}
            />
          </DialogContent>
        </Dialog>
        </div>
      </div>

      {error && !isCreateDialogOpen && !editingJob ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="rounded-xl border border-border/50 bg-card/30 backdrop-blur-sm overflow-hidden shadow-sm">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
              <TableHead className="font-semibold">Title</TableHead>
              <TableHead className="font-semibold">Status</TableHead>
              <TableHead className="font-semibold">Requirements</TableHead>
              <TableHead className="font-semibold">Created</TableHead>
              <TableHead className="text-right font-semibold">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                  Loading jobs...
                </TableCell>
              </TableRow>
            ) : filteredJobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground">
                  {jobs.length === 0
                    ? "No jobs found. Create your first job to get started."
                    : "No jobs match the current search or filter."}
                </TableCell>
              </TableRow>
            ) : (
              filteredJobs.map((job) => (
                <TableRow key={job.id} className="hover:bg-muted/30 transition-colors">
                  <TableCell className="font-medium">{job.title}</TableCell>
                  <TableCell>
                    <span
                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${statusClasses[job.status]}`}
                    >
                      {job.status}
                    </span>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground">
                    {job.requirements || "No requirements added"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(job.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Manage ${job.title}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => navigate(`/jobs/${job.id}`)}>
                          <Eye className="size-4" />
                          View Detail
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => openEditDialog(job)}>
                          <Pencil className="size-4" />
                          Edit
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          variant="destructive"
                          onClick={() => void handleDelete(job)}
                        >
                          <Trash2 className="size-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={editingJob !== null} onOpenChange={(open) => !open && closeDialogs()}>
        <DialogContent className="sm:max-w-[500px] border-border/50 bg-card/95 backdrop-blur-xl">
          <DialogHeader>
            <DialogTitle className="text-2xl font-bold">Edit Job</DialogTitle>
            <DialogDescription>
              Update the role details and current job status.
            </DialogDescription>
          </DialogHeader>
          <JobForm
            form={form}
            error={error}
            submitting={submitting}
            submitLabel="Save Changes"
            onChange={handleFormChange}
            onSubmit={handleSubmit}
            onCancel={closeDialogs}
            showStatus
          />
        </DialogContent>
      </Dialog>
    </div>
  )
}

type JobFormProps = {
  form: JobFormState
  error: string
  submitting: boolean
  submitLabel: string
  onChange: <K extends keyof JobFormState>(key: K, value: JobFormState[K]) => void
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => Promise<void>
  onCancel: () => void
  showStatus?: boolean
}

function JobForm({
  form,
  error,
  submitting,
  submitLabel,
  onChange,
  onSubmit,
  onCancel,
  showStatus = true,
}: JobFormProps) {
  return (
    <form onSubmit={(event) => void onSubmit(event)}>
      <div className="grid gap-6 py-4">
        <div className="space-y-2">
          <Label htmlFor="title" className="text-sm font-semibold">
            Job Title
          </Label>
          <Input
            id="title"
            placeholder="e.g. Senior Frontend Engineer"
            value={form.title}
            onChange={(event) => onChange("title", event.target.value)}
            required
            className="bg-background/50"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="description" className="text-sm font-semibold">
            Description
          </Label>
          <Textarea
            id="description"
            placeholder="Role overview, team context, and success expectations..."
            value={form.description}
            onChange={(event) => onChange("description", event.target.value)}
            required
            className="bg-background/50"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="requirements" className="text-sm font-semibold">
            Requirements
          </Label>
          <Textarea
            id="requirements"
            placeholder="Core skills, years of experience, and must-haves..."
            value={form.requirements}
            onChange={(event) => onChange("requirements", event.target.value)}
            className="bg-background/50"
          />
        </div>
        {showStatus ? (
          <div className="space-y-2">
            <Label className="text-sm font-semibold">Status</Label>
            <Select value={form.status} onValueChange={(value: JobStatus) => onChange("status", value)}>
              <SelectTrigger className="w-full bg-background/50">
                <SelectValue placeholder="Select status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="paused">Paused</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : null}
        {error ? (
          <div className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </div>
        ) : null}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" className="px-8" disabled={submitting}>
          {submitting ? "Saving..." : submitLabel}
        </Button>
      </DialogFooter>
    </form>
  )
}
