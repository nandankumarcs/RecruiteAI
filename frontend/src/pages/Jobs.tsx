import { useEffect, useMemo, useState } from "react"
import { Eye, MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react"
import { useNavigate, Link } from "react-router-dom"

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
import { DeleteConfirmDialog } from "@/components/ui/DeleteConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { Calendar, Briefcase } from "lucide-react"
import { toast } from "sonner"

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
  active: "bg-emerald-500/15 text-emerald-500 dark:text-emerald-400 border-emerald-500/20",
  paused: "bg-amber-500/15 text-amber-500 dark:text-amber-400 border-amber-500/20",
  closed: "bg-slate-500/15 text-slate-500 dark:text-slate-400 border-slate-500/20",
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
  const [jobToDelete, setJobToDelete] = useState<Job | null>(null)

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

  const handleDelete = async () => {
    if (!jobToDelete) return

    try {
      setSubmitting(true)
      await api.delete(`/jobs/${jobToDelete.id}`)
      toast.success("Job deleted successfully")
      setJobToDelete(null)
      await fetchJobs()
    } catch (error) {
      console.error("Failed to delete job", error)
      toast.error("Could not delete the selected job.")
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
              <Button className="rounded-lg shadow-sm shadow-primary/10" onClick={openCreateDialog}>
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

      <div className="hidden md:block rounded-lg border border-border/40 bg-card/40 backdrop-blur-xl overflow-hidden shadow-md">
        <Table>
          <TableHeader className="bg-muted/50 border-b border-border/40">
            <TableRow className="hover:bg-transparent">
              <TableHead className="font-bold text-foreground py-6 px-6">JOB TITLE</TableHead>
              <TableHead className="font-bold text-foreground py-6">STATUS</TableHead>
              <TableHead className="font-bold text-foreground py-6">REQUIREMENTS</TableHead>
              <TableHead className="font-bold text-foreground py-6">CREATED</TableHead>
              <TableHead className="text-right font-bold text-foreground py-6 px-6">ACTIONS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={5} className="h-64 text-center">
                  <div className="flex flex-col items-center justify-center gap-3">
                    <div className="h-10 w-10 border-4 border-primary/30 border-t-primary rounded-full animate-spin" />
                    <p className="text-muted-foreground font-medium animate-pulse">Loading jobs...</p>
                  </div>
                </TableCell>
              </TableRow>
            ) : filteredJobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-64 text-center">
                  <div className="flex flex-col items-center justify-center gap-4">
                    <div className="p-4 bg-muted/50 rounded-full">
                      <Briefcase className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <div className="space-y-1">
                      <p className="text-xl font-bold">No jobs found</p>
                      <p className="text-muted-foreground">
                        {jobs.length === 0
                          ? "Create your first job to start receiving resumes."
                          : "Try adjusting your search or filters."}
                      </p>
                    </div>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              filteredJobs.map((job) => (
                <TableRow key={job.id} className="hover:bg-primary/5 group border-b border-border/40 last:border-0">
                  <TableCell className="font-black tracking-tight text-lg py-6 px-6">
                    <Link 
                      to={`/jobs/${job.id}`}
                      className="hover:text-primary transition-colors cursor-pointer"
                    >
                      {job.title}
                    </Link>
                  </TableCell>
                  <TableCell className="py-6">
                    <Badge
                      variant="outline"
                      className={`font-black tracking-tight uppercase px-3 py-1 rounded-lg shadow-sm ${statusClasses[job.status]}`}
                    >
                      {job.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-muted-foreground font-medium py-6">
                    {job.requirements || "No requirements added"}
                  </TableCell>
                  <TableCell className="text-muted-foreground font-medium py-6">
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      {new Date(job.created_at).toLocaleDateString()}
                    </div>
                  </TableCell>
                  <TableCell className="text-right py-6 px-6 relative">
                    <div className="flex items-center justify-end">
                      <div className="flex items-center gap-2">
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
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
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
                  className={`font-black tracking-tight uppercase px-3 py-1 rounded-lg shadow-sm ${statusClasses[job.status]}`}
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
