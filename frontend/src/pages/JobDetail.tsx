import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { Briefcase, Calendar, ChevronLeft, Loader2, MapPin, PhoneCall, UploadCloud } from "lucide-react";

import { api } from "@/lib/api";
import type { CallRecord } from "@/lib/calls";
import { ACTIVE_CALL_STATUSES } from "@/lib/calls";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ResumeUploader } from "@/components/resumes/ResumeUploader";
import { ResumeTable, type Resume } from "@/components/resumes/ResumeTable";
import { ResumeDetailModal } from "@/components/resumes/ResumeDetailModal";
import { DeleteConfirmDialog } from "@/components/ui/DeleteConfirmDialog";
import { CallsTable } from "@/components/calls/CallsTable";
import { CallProgressIndicator } from "@/components/calls/CallProgressIndicator";

interface Job {
  id: string;
  title: string;
  description: string;
  requirements: string | null;
  status: string;
  created_at: string;
}

type DetailTab = "resumes" | "calls" | "details";

const tabs: Array<{ key: DetailTab; label: string }> = [
  { key: "resumes", label: "Resumes" },
  { key: "calls", label: "Calls" },
  { key: "details", label: "Details" },
];

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [activeTab, setActiveTab] = useState<DetailTab>("resumes");
  const [isLoading, setIsLoading] = useState(true);

  const [viewingResume, setViewingResume] = useState<Resume | null>(null);
  const [resumeToDelete, setResumeToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchJobData = useCallback(async () => {
    if (!jobId) return;
    try {
      const [jobRes, resumesRes, callsRes] = await Promise.all([
        api.get(`/jobs/${jobId}`),
        api.get(`/jobs/${jobId}/resumes`),
        api.get(`/jobs/${jobId}/calls`),
      ]);
      setJob(jobRes.data);
      setResumes(resumesRes.data);
      setCalls(callsRes.data);
    } catch (error) {
      console.error("Failed to fetch job data", error);
    } finally {
      setIsLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void fetchJobData();
  }, [fetchJobData]);

  const activeCalls = useMemo(
    () => calls.filter((call) => ACTIVE_CALL_STATUSES.includes(call.status)),
    [calls]
  );

  const activeCallsByResumeId = useMemo(
    () =>
      activeCalls.reduce<Record<string, CallRecord>>((acc, call) => {
        acc[call.resume_id] = call;
        return acc;
      }, {}),
    [activeCalls]
  );

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

  const handleStartCall = (resume: Resume) => {
    setViewingResume(resume);
  };

  const handleCallUpdate = (updatedCall: CallRecord) => {
    setCalls((previous) => {
      const existing = previous.find((call) => call.id === updatedCall.id);
      if (!existing) return [updatedCall, ...previous];
      return previous.map((call) => (call.id === updatedCall.id ? updatedCall : call));
    });
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
      <div className="py-12 text-center">
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
        <Link to="/jobs" className="flex items-center text-sm text-muted-foreground transition-colors hover:text-primary">
          <ChevronLeft className="mr-1 h-4 w-4" /> Back to Jobs
        </Link>
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <h2 className="text-4xl font-extrabold tracking-tight">{job.title}</h2>
            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Posted {new Date(job.created_at).toLocaleDateString()}
              </span>
              <span className="flex items-center gap-2">
                <MapPin className="h-4 w-4" />
                Remote
              </span>
              <span className="flex items-center gap-2 capitalize">
                <Briefcase className="h-4 w-4" />
                {job.status}
              </span>
            </div>
          </div>
          <Button variant="outline" className="border-primary/20 hover:bg-primary/5">
            Edit Job
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 rounded-xl border border-border/50 bg-card/50 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeCalls.length > 0 && (
        <CallProgressIndicator
          callId={activeCalls[0].id}
          initialCall={activeCalls[0]}
          onUpdate={handleCallUpdate}
        />
      )}

      <div className="grid gap-8 lg:grid-cols-3">
        <div className="space-y-8 lg:col-span-2">
          {activeTab === "resumes" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-2xl font-bold">Candidates</h3>
                <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
                  {resumes.length} Total
                </span>
              </div>
              <ResumeTable
                resumes={resumes}
                activeCallsByResumeId={activeCallsByResumeId}
                onDelete={(id) => setResumeToDelete(id)}
                onView={setViewingResume}
                onStartCall={handleStartCall}
              />
            </div>
          )}

          {activeTab === "calls" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-2xl font-bold">Call History</h3>
                <span className="rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
                  {calls.length} Calls
                </span>
              </div>
              <CallsTable calls={calls} />
            </div>
          )}

          {activeTab === "details" && (
            <Card className="border-none bg-card/60 shadow-xl backdrop-blur-xl">
              <CardHeader>
                <CardTitle className="text-xl">Job Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h4 className="mb-2 font-semibold">Description</h4>
                  <p className="whitespace-pre-wrap leading-relaxed text-foreground">
                    {job.description}
                  </p>
                </div>
                <div>
                  <h4 className="mb-2 font-semibold">Requirements</h4>
                  <p className="whitespace-pre-wrap text-muted-foreground">
                    {job.requirements || "No specific requirements provided."}
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-8">
          <Card className="border-none bg-gradient-to-br from-primary/10 via-background to-background shadow-xl">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <UploadCloud className="h-5 w-5 text-primary" />
                Add Candidates
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResumeUploader jobId={job.id} onUploadSuccess={fetchJobData} />
            </CardContent>
          </Card>

          <Card className="border-border/50 bg-card/60 shadow-lg">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <PhoneCall className="h-4 w-4 text-primary" />
                Call Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <div className="flex items-center justify-between">
                <span>Active calls</span>
                <span className="font-medium text-foreground">{activeCalls.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Total calls</span>
                <span className="font-medium text-foreground">{calls.length}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Completed calls</span>
                <span className="font-medium text-foreground">
                  {calls.filter((call) => call.status === "completed").length}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <ResumeDetailModal
        resume={viewingResume}
        activeCall={viewingResume ? activeCallsByResumeId[viewingResume.id] ?? null : null}
        isOpen={!!viewingResume}
        onCallUpdate={handleCallUpdate}
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
