import { useState, useEffect, useCallback, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { Calendar, ChevronLeft, MapPin, PhoneCall, UploadCloud } from "lucide-react";

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
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/context/ToastContext";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";

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
  const { toast } = useToast();
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
      toast({
        variant: "error",
        title: "Couldn't load this job",
        description: "Try refreshing the page in a moment.",
      });
    } finally {
      setIsLoading(false);
    }
  }, [jobId, toast]);

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
      toast({
        variant: "success",
        title: "Resume removed",
        description: "The candidate record has been deleted.",
      });
    } catch (error) {
      console.error("Failed to delete resume", error);
      toast({
        variant: "error",
        title: "Delete failed",
        description: "We couldn't remove that resume just now.",
      });
    } finally {
      setIsDeleting(false);
    }
  };

  const handleStartCall = (resume: Resume) => {
    setViewingResume(resume);
  };

  const handleCallUpdate = useCallback((updatedCall: CallRecord) => {
    setCalls((previous) => {
      const existing = previous.find((call) => call.id === updatedCall.id);
      if (!existing) return [updatedCall, ...previous];
      return previous.map((call) => (call.id === updatedCall.id ? updatedCall : call));
    });
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-6 pb-12">
        <Skeleton className="h-6 w-28" />
        <div className="space-y-3">
          <Skeleton className="h-10 w-80" />
          <Skeleton className="h-5 w-64" />
        </div>
        <Skeleton className="h-11 w-full rounded-lg" />
        <div className="grid gap-8 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Skeleton className="h-10 w-48" />
            <Skeleton className="h-72 w-full rounded-lg" />
          </div>
          <div className="space-y-8">
            <Skeleton className="h-80 w-full rounded-lg" />
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        </div>
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
      <div className="flex flex-col gap-6">
        <Link to="/jobs" className="group flex items-center text-sm font-black tracking-tight text-muted-foreground transition-all hover:text-primary">
          <ChevronLeft className="mr-1 h-4 w-4 transition-transform group-hover:-translate-x-1" /> BACK TO JOBS
        </Link>
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-3">
            <h2 className="text-5xl md:text-6xl font-black tracking-tighter leading-none">
              {job.title}
            </h2>
            <div className="flex flex-wrap gap-4">
              <Badge variant="secondary" className="px-3 py-1 rounded-lg font-bold flex items-center gap-2">
                <Calendar className="h-3.5 w-3.5" />
                POSTED {new Date(job.created_at).toLocaleDateString()}
              </Badge>
              <Badge variant="secondary" className="px-3 py-1 rounded-lg font-bold flex items-center gap-2">
                <MapPin className="h-3.5 w-3.5" />
                REMOTE
              </Badge>
              <Badge variant="outline" className={`px-3 py-1 rounded-lg font-black uppercase tracking-tight ${
                job.status === 'active' ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 'bg-amber-500/10 text-amber-500 border-amber-500/20'
              }`}>
                {job.status}
              </Badge>
            </div>
          </div>
          <Button 
            variant="outline" 
            className="h-14 px-8 rounded-lg font-black tracking-tight border-primary/20 hover:bg-primary/5 shadow-md transition-all active:scale-95"
          >
            EDIT JOB
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 p-1 bg-muted/30 backdrop-blur-xl border border-border/40 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`relative rounded-lg px-6 py-2.5 text-sm font-black tracking-tight transition-all duration-300 ${
              activeTab === tab.key
                ? "text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            }`}
          >
            {activeTab === tab.key && (
              <motion.div
                layoutId="activeTab"
                className="absolute inset-0 bg-primary rounded-lg shadow-sm shadow-primary/10"
                transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
              />
            )}
            <span className="relative z-10 uppercase">{tab.label}</span>
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
        <div className="lg:col-span-2">
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="space-y-8"
            >
              {activeTab === "resumes" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between px-2">
                    <h3 className="text-3xl font-black tracking-tighter">CANDIDATES</h3>
                    <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
                      {resumes.length} Total
                    </Badge>
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
                <div className="space-y-6">
                  <div className="flex items-center justify-between px-2">
                    <h3 className="text-3xl font-black tracking-tighter">CALL HISTORY</h3>
                    <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
                      {calls.length} Calls
                    </Badge>
                  </div>
                  <div className="rounded-lg border border-border/40 bg-card/40 backdrop-blur-xl overflow-hidden shadow-md">
                    <CallsTable calls={calls} />
                  </div>
                </div>
              )}

              {activeTab === "details" && (
                <div className="space-y-6">
                   <div className="px-2">
                    <h3 className="text-3xl font-black tracking-tighter">JOB INFORMATION</h3>
                  </div>
                  <Card className="border-border/40 bg-card/40 backdrop-blur-xl shadow-md rounded-lg overflow-hidden">
                    <CardHeader className="border-b border-border/40 bg-muted/30">
                      <CardTitle className="text-xl font-black tracking-tight uppercase">Detailed Brief</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-8 p-8">
                      <div className="space-y-3">
                        <h4 className="text-sm font-black tracking-widest text-primary uppercase">Description</h4>
                        <p className="whitespace-pre-wrap leading-relaxed text-lg font-medium text-foreground">
                          {job.description}
                        </p>
                      </div>
                      <div className="space-y-3 pt-4 border-t border-border/40">
                        <h4 className="text-sm font-black tracking-widest text-primary uppercase">Requirements</h4>
                        <div className="bg-background/40 p-6 rounded-lg border border-border/40">
                          <p className="whitespace-pre-wrap font-medium text-muted-foreground leading-relaxed">
                            {job.requirements || "No specific requirements provided."}
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="space-y-8">
          <Card className="border-none bg-muted/30 shadow-xl">
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
