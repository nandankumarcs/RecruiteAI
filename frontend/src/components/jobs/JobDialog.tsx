import { useState, useEffect } from "react"
import { api } from "@/lib/api"
import type { Job, JobStatus } from "@/lib/jobs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
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
import { useToast } from "@/context/ToastContext"

type JobFormState = {
  title: string
  description: string
  requirements: string
  status: JobStatus
}

interface JobDialogProps {
  job?: Job | null
  isOpen: boolean
  onClose: () => void
  onSuccess: (job: Job) => void
}

export function JobDialog({ job, isOpen, onClose, onSuccess }: JobDialogProps) {
  const { toast } = useToast()
  const [form, setForm] = useState<JobFormState>({
    title: "",
    description: "",
    requirements: "",
    status: "active",
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    if (job) {
      setForm({
        title: job.title,
        description: job.description,
        requirements: job.requirements ?? "",
        status: job.status,
      })
    } else {
      setForm({
        title: "",
        description: "",
        requirements: "",
        status: "active",
      })
    }
    setError("")
  }, [job, isOpen])

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

      let response;
      if (job) {
        response = await api.put<Job>(`/jobs/${job.id}`, payload)
        toast({
          variant: "success",
          title: "Job updated",
          description: "Changes have been saved successfully.",
        })
      } else {
        response = await api.post<Job>("/jobs", payload)
        toast({
          variant: "success",
          title: "Job created",
          description: "New job posting has been added.",
        })
      }

      onSuccess(response.data)
      onClose()
    } catch (error) {
      console.error("Failed to save job", error)
      setError("Could not save the job. Please try again.")
      toast({
        variant: "error",
        title: "Save failed",
        description: "There was an error saving the job details.",
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[500px] border-border/50 bg-card/95 backdrop-blur-xl">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold">{job ? "Edit Job" : "Create Job"}</DialogTitle>
          <DialogDescription>
            {job ? "Update the role details and current job status." : "Post a new position to start receiving and screening resumes."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void handleSubmit(event)}>
          <div className="grid gap-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="title" className="text-sm font-semibold">
                Job Title
              </Label>
              <Input
                id="title"
                placeholder="e.g. Senior Frontend Engineer"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
                className="bg-background/50"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="description" className="text-sm font-semibold">
                  Description
                </Label>
                <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-tighter">Markdown supported</span>
              </div>
              <Textarea
                id="description"
                placeholder="Role overview, team context, and success expectations..."
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                required
                className="bg-background/50 h-32"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="requirements" className="text-sm font-semibold">
                  Requirements
                </Label>
                <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-tighter">Markdown supported</span>
              </div>
              <Textarea
                id="requirements"
                placeholder="Core skills, years of experience, and must-haves..."
                value={form.requirements}
                onChange={(e) => setForm({ ...form, requirements: e.target.value })}
                className="bg-background/50 h-32"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-semibold">Status</Label>
              <Select value={form.status} onValueChange={(value: JobStatus) => setForm({ ...form, status: value })}>
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
            {error ? (
              <div className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            ) : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
              Cancel
            </Button>
            <Button type="submit" className="px-8 font-bold" disabled={submitting}>
              {submitting ? "Saving..." : job ? "Save Changes" : "Create Job"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
