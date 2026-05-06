import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { ChevronLeft, Briefcase, Calendar, MapPin, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { ResumeUploader } from "@/components/resumes/ResumeUploader";
import { ResumeTable, type Resume } from "@/components/resumes/ResumeTable";
import { ResumeDetailModal } from "@/components/resumes/ResumeDetailModal";
import { DeleteConfirmDialog } from "@/components/ui/DeleteConfirmDialog";

interface Job {
  id: string;
  title: string;
  description: string;
  requirements: string | null;
  status: string;
  created_at: string;
}

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // Modal states
  const [viewingResume, setViewingResume] = useState<Resume | null>(null);
  const [resumeToDelete, setResumeToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchJobData = useCallback(async () => {
    if (!jobId) return;
    try {
      const [jobRes, resumesRes] = await Promise.all([
        api.get(`/jobs/${jobId}`),
        api.get(`/jobs/${jobId}/resumes`),
      ]);
      setJob(jobRes.data);
      setResumes(resumesRes.data);
    } catch (error) {
      console.error("Failed to fetch job data", error);
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    fetchJobData();
  }, [fetchJobData]);

  const handleDeleteResume = async () => {
    if (!resumeToDelete) return;
    setIsDeleting(true);
    try {
      await api.delete(`/resumes/${resumeToDelete}`);
      setResumes((prev) => prev.filter((r) => r.id !== resumeToDelete));
      setResumeToDelete(null);
    } catch (error) {
      console.error("Failed to delete resume", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleViewResume = (resume: Resume) => {
    setViewingResume(resume);
  };

  if (isLoading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold">Job not found</h2>
        <Link to="/jobs">
          <Button variant="link">Back to jobs</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-8 pb-12">
      <div className="flex flex-col gap-4">
        <Link to="/jobs" className="flex items-center text-sm text-muted-foreground hover:text-primary transition-colors">
          <ChevronLeft className="h-4 w-4 mr-1" /> Back to Jobs
        </Link>
        <div className="flex items-center justify-between">
          <h2 className="text-4xl font-extrabold tracking-tight">{job.title}</h2>
          <Button variant="outline" className="border-primary/20 hover:bg-primary/5">
            Edit Job
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* Left Column: Job Details */}
        <div className="lg:col-span-2 space-y-8">
          <Card className="border-none bg-card/60 backdrop-blur-xl shadow-xl">
            <CardHeader>
              <CardTitle className="text-xl">Job Description</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <p className="text-foreground leading-relaxed whitespace-pre-wrap">{job.description}</p>
              </div>
              {job.requirements && (
                <div>
                  <h4 className="font-semibold mb-2">Requirements</h4>
                  <p className="text-muted-foreground whitespace-pre-wrap">{job.requirements}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-4 pt-4 border-t border-border/50">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Calendar className="h-4 w-4" /> Posted {new Date(job.created_at).toLocaleDateString()}
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <MapPin className="h-4 w-4" /> Remote
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Briefcase className="h-4 w-4 capitalize" /> {job.status}
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-2xl font-bold">Candidates</h3>
              <span className="px-2.5 py-0.5 rounded-full bg-primary/10 text-primary text-xs font-bold border border-primary/20">
                {resumes.length} Total
              </span>
            </div>
            <ResumeTable 
              resumes={resumes} 
              onDelete={(id) => setResumeToDelete(id)} 
              onView={handleViewResume}
            />
          </div>
        </div>

        {/* Right Column: Resume Upload */}
        <div className="space-y-8">
          <Card className="border-none bg-gradient-to-br from-primary/10 via-background to-background shadow-xl">
            <CardHeader>
              <CardTitle className="text-xl">Add Candidates</CardTitle>
            </CardHeader>
            <CardContent>
              <ResumeUploader jobId={job.id} onUploadSuccess={fetchJobData} />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Modals */}
      <ResumeDetailModal 
        resume={viewingResume} 
        isOpen={!!viewingResume} 
        onClose={() => setViewingResume(null)} 
      />

      <DeleteConfirmDialog 
        isOpen={!!resumeToDelete}
        onClose={() => setResumeToDelete(null)}
        onConfirm={handleDeleteResume}
        isLoading={isDeleting}
        title="Delete Resume"
        description="Are you sure you want to delete this resume? This candidate will be removed from the job and all parsed data will be lost."
      />
    </div>
  );
}
