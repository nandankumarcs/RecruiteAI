import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { Calendar, ChevronLeft, Download, PhoneCall, UploadCloud, X } from "lucide-react";

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
import { QuestionManager } from "@/components/jobs/QuestionManager";
import { Skeleton } from "@/components/ui/Skeleton";
import { JobDialog } from "@/components/jobs/JobDialog";
import type { Job } from "@/lib/jobs";

import { useToast } from "@/context/ToastContext";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Markdown } from "@/components/ui/Markdown";


type DetailTab = "resumes" | "calls" | "strategy" | "details";

type ResumeSortBy = "matching_score" | "candidate_name" | "status" | "created_at";
type CallSortBy = "created_at" | "status" | "phone_number";
type SortOrder = "asc" | "desc";

interface ResumeFilters {
  name: string;
  email: string;
  uploadedFrom: string; // YYYY-MM-DD
  uploadedTo: string;   // YYYY-MM-DD
}

const resumeSortKeys: ResumeSortBy[] = ["matching_score", "candidate_name", "status", "created_at"];
const callSortKeys: CallSortBy[] = ["created_at", "status", "phone_number"];

const tabs: Array<{ key: DetailTab; label: string }> = [

  { key: "resumes", label: "Candidates" },
  { key: "calls", label: "Call History" },
  { key: "strategy", label: "Questions" },
  { key: "details", label: "Job Info" },
];


export function JobDetail() {
  const { toast } = useToast();
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<Job | null>(null);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [activeTab, setActiveTab] = useState<DetailTab>("resumes");
  const [isLoading, setIsLoading] = useState(true);

  const [viewingResume, setViewingResume] = useState<Resume | null>(null);
  const [resumeToDelete, setResumeToDelete] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isExportingCandidates, setIsExportingCandidates] = useState(false);

  const [totalResumes, setTotalResumes] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(20);
  const [sortBy, setSortBy] = useState<ResumeSortBy>("matching_score");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [filters, setFilters] = useState<ResumeFilters>({ name: "", email: "", uploadedFrom: "", uploadedTo: "" });

  const [totalCalls, setTotalCalls] = useState(0);
  const [completedCallsCount, setCompletedCallsCount] = useState(0);
  const [callsPage, setCallsPage] = useState(1);
  const [callsPageSize] = useState(20);
  const [callsSortBy, setCallsSortBy] = useState<CallSortBy>("created_at");
  const [callsSortOrder, setCallsSortOrder] = useState<SortOrder>("desc");

  const fetchResumes = useCallback(async (
    page: number,
    sb: ResumeSortBy,
    so: SortOrder,
    f: ResumeFilters = filters,
  ) => {
    if (!jobId) return;
    try {
      const res = await api.get(`/jobs/${jobId}/resumes`, {
        params: {
          page,
          page_size: pageSize,
          sort_by: sb,
          sort_order: so,
          ...(f.name ? { name: f.name } : {}),
          ...(f.email ? { email: f.email } : {}),
          ...(f.uploadedFrom ? { uploaded_from: f.uploadedFrom } : {}),
          ...(f.uploadedTo ? { uploaded_to: f.uploadedTo } : {}),
        },
      });
      setResumes(res.data.items);
      setTotalResumes(res.data.total);
    } catch (error) {
      console.error("Failed to fetch resumes", error);
      toast({ variant: "error", title: "Couldn't load candidates", description: "Try refreshing the page." });
    }
  }, [jobId, pageSize, toast, filters]);

  const fetchJobData = useCallback(async () => {
    if (!jobId) return;
    try {
      const [jobRes, resumesRes, callsRes] = await Promise.all([
        api.get(`/jobs/${jobId}`),
        api.get(`/jobs/${jobId}/resumes`, {
          params: { page: 1, page_size: pageSize, sort_by: "matching_score", sort_order: "desc" },
        }),
        api.get(`/jobs/${jobId}/calls`, {
          params: { page: 1, page_size: callsPageSize, sort_by: "created_at", sort_order: "desc" },
        }),
      ]);
      setJob(jobRes.data);
      setResumes(resumesRes.data.items);
      setTotalResumes(resumesRes.data.total);
      setCalls(callsRes.data.items);
      setTotalCalls(callsRes.data.total);
      setCompletedCallsCount(callsRes.data.completed_count);
      // Seed active calls from the dedicated active_calls field so CallProgressIndicator works
      if (callsRes.data.active_calls?.length) {
        setCalls((prev) => {
          const ids = new Set(prev.map((c: CallRecord) => c.id));
          const extra = callsRes.data.active_calls.filter((c: CallRecord) => !ids.has(c.id));
          return extra.length ? [...extra, ...prev] : prev;
        });
      }
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
  }, [jobId, pageSize, callsPageSize, toast]);

  const handleSortChange = useCallback((newSortBy: string, newSortOrder: SortOrder) => {
    if (!resumeSortKeys.includes(newSortBy as ResumeSortBy)) return;
    const nextSortBy = newSortBy as ResumeSortBy;
    setSortBy(nextSortBy);
    setSortOrder(newSortOrder);
    setCurrentPage(1);
    void fetchResumes(1, nextSortBy, newSortOrder);
  }, [fetchResumes]);

  const handlePageChange = useCallback((newPage: number) => {
    setCurrentPage(newPage);
    void fetchResumes(newPage, sortBy, sortOrder);
  }, [fetchResumes, sortBy, sortOrder]);

  const handleFilterChange = useCallback((patch: Partial<ResumeFilters>) => {
    const next = { ...filters, ...patch };
    setFilters(next);
    setCurrentPage(1);
    void fetchResumes(1, sortBy, sortOrder, next);
  }, [fetchResumes, filters, sortBy, sortOrder]);

  const hasActiveFilters = filters.name || filters.email || filters.uploadedFrom || filters.uploadedTo;

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleTextFilterChange = useCallback((patch: Partial<ResumeFilters>) => {
    const next = { ...filters, ...patch };
    setFilters(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setCurrentPage(1);
      void fetchResumes(1, sortBy, sortOrder, next);
    }, 350);
  }, [fetchResumes, filters, sortBy, sortOrder]);

  const fetchCalls = useCallback(async (page: number, sb: CallSortBy, so: SortOrder) => {
    if (!jobId) return;
    try {
      const res = await api.get(`/jobs/${jobId}/calls`, {
        params: { page, page_size: callsPageSize, sort_by: sb, sort_order: so },
      });
      setCalls(res.data.items);
      setTotalCalls(res.data.total);
      setCompletedCallsCount(res.data.completed_count);
    } catch (error) {
      console.error("Failed to fetch calls", error);
      toast({ variant: "error", title: "Couldn't load call history", description: "Try refreshing." });
    }
  }, [jobId, callsPageSize, toast]);

  const handleCallsSortChange = useCallback((newSortBy: string, newSortOrder: SortOrder) => {
    if (!callSortKeys.includes(newSortBy as CallSortBy)) return;
    const nextSortBy = newSortBy as CallSortBy;
    setCallsSortBy(nextSortBy);
    setCallsSortOrder(newSortOrder);
    setCallsPage(1);
    void fetchCalls(1, nextSortBy, newSortOrder);
  }, [fetchCalls]);

  const handleCallsPageChange = useCallback((newPage: number) => {
    setCallsPage(newPage);
    void fetchCalls(newPage, callsSortBy, callsSortOrder);
  }, [fetchCalls, callsSortBy, callsSortOrder]);

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
      setResumeToDelete(null);
      toast({
        variant: "success",
        title: "Resume removed",
        description: "The candidate record has been deleted.",
      });
      // Refetch to keep pagination accurate; go to previous page if current page is now empty
      const newTotal = totalResumes - 1;
      const maxPage = Math.max(1, Math.ceil(newTotal / pageSize));
      const pageToLoad = Math.min(currentPage, maxPage);
      setCurrentPage(pageToLoad);
      await fetchResumes(pageToLoad, sortBy, sortOrder);
      setTotalResumes(newTotal);
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

  const handleExportCandidates = useCallback(async () => {
    if (!jobId || isExportingCandidates) return;
    setIsExportingCandidates(true);
    try {
      const response = await api.get(`/jobs/${jobId}/resumes/export`, {
        responseType: "blob",
        params: {
          sort_by: sortBy,
          sort_order: sortOrder,
          ...(filters.name ? { name: filters.name } : {}),
          ...(filters.email ? { email: filters.email } : {}),
          ...(filters.uploadedFrom ? { uploaded_from: filters.uploadedFrom } : {}),
          ...(filters.uploadedTo ? { uploaded_to: filters.uploadedTo } : {}),
        },
      });
      const blob = new Blob([response.data], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const disposition = response.headers["content-disposition"];
      const filenameMatch = disposition?.match(/filename="?([^"]+)"?/i);
      link.href = url;
      link.download = filenameMatch?.[1] || "candidates.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast({
        variant: "success",
        title: "Export ready",
        description: "Candidate spreadsheet downloaded.",
      });
    } catch (error) {
      console.error("Failed to export candidates", error);
      toast({
        variant: "error",
        title: "Export failed",
        description: "We couldn't export candidates just now.",
      });
    } finally {
      setIsExportingCandidates(false);
    }
  }, [isExportingCandidates, jobId, toast]);

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
            onClick={() => setIsEditDialogOpen(true)}
          >
            EDIT JOB
          </Button>
        </div>
      </div>

      <JobDialog
        job={job}
        isOpen={isEditDialogOpen}
        onClose={() => setIsEditDialogOpen(false)}
        onSuccess={(updatedJob) => setJob(updatedJob)}
      />

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
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-9 rounded-lg border-primary/20 bg-primary/5 px-3 text-xs font-black uppercase tracking-tight text-primary hover:bg-primary/10"
                        onClick={handleExportCandidates}
                        disabled={isExportingCandidates || totalResumes === 0}
                      >
                        <Download className="mr-1.5 h-3.5 w-3.5" />
                        {isExportingCandidates ? "Exporting" : "Export"}
                      </Button>
                      <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
                        {totalResumes} Total
                      </Badge>
                    </div>
                  </div>

                  {/* Filter bar */}
                  <div className="flex flex-wrap items-center gap-2 px-2">
                    <Input
                      placeholder="Name"
                      value={filters.name}
                      onChange={(e) => handleTextFilterChange({ name: e.target.value })}
                      className="h-8 w-40 text-xs rounded-lg border-border/50 bg-muted/30"
                    />
                    <Input
                      placeholder="Email"
                      value={filters.email}
                      onChange={(e) => handleTextFilterChange({ email: e.target.value })}
                      className="h-8 w-44 text-xs rounded-lg border-border/50 bg-muted/30"
                    />
                    <div className="flex items-center gap-1.5">
                      <Input
                        type="date"
                        title="Uploaded from"
                        value={filters.uploadedFrom}
                        onChange={(e) => handleFilterChange({ uploadedFrom: e.target.value })}
                        className="h-8 w-36 text-xs rounded-lg border-border/50 bg-muted/30"
                      />
                      <span className="text-xs text-muted-foreground font-bold">–</span>
                      <Input
                        type="date"
                        title="Uploaded to"
                        value={filters.uploadedTo}
                        onChange={(e) => handleFilterChange({ uploadedTo: e.target.value })}
                        className="h-8 w-36 text-xs rounded-lg border-border/50 bg-muted/30"
                      />
                    </div>
                    {hasActiveFilters && (
                      <button
                        type="button"
                        onClick={() => {
                          const cleared = { name: "", email: "", uploadedFrom: "", uploadedTo: "" };
                          setFilters(cleared);
                          setCurrentPage(1);
                          void fetchResumes(1, sortBy, sortOrder, cleared);
                        }}
                        className="flex items-center gap-1 h-8 px-2.5 rounded-lg text-xs font-bold text-muted-foreground hover:text-foreground border border-border/40 hover:border-border transition-all bg-muted/20"
                      >
                        <X className="h-3 w-3" /> Clear
                      </button>
                    )}
                  </div>

                  <ResumeTable
                    resumes={resumes}
                    activeCallsByResumeId={activeCallsByResumeId}
                    onDelete={(id) => setResumeToDelete(id)}
                    onView={setViewingResume}
                    onEdit={(r) => navigate(`/resumes/${r.id}/edit`)}
                    onStartCall={handleStartCall}
                    sortBy={sortBy}
                    sortOrder={sortOrder}
                    onSortChange={handleSortChange}
                    currentPage={currentPage}
                    pageSize={pageSize}
                    totalItems={totalResumes}
                    onPageChange={handlePageChange}
                  />
                </div>
              )}

              {activeTab === "calls" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between px-2">
                    <h3 className="text-3xl font-black tracking-tighter">CALL HISTORY</h3>
                    <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
                      {totalCalls} Calls
                    </Badge>
                  </div>
                  <CallsTable
                    calls={calls}
                    sortBy={callsSortBy}
                    sortOrder={callsSortOrder}
                    onSortChange={handleCallsSortChange}
                    currentPage={callsPage}
                    pageSize={callsPageSize}
                    totalItems={totalCalls}
                    onPageChange={handleCallsPageChange}
                  />
                </div>
              )}

              {activeTab === "strategy" && (
                <QuestionManager jobId={job.id} />
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
                        <Markdown content={job.description} />
                      </div>
                      <div className="space-y-3 pt-4 border-t border-border/40">
                        <h4 className="text-sm font-black tracking-widest text-primary uppercase">Requirements</h4>
                        <div className="bg-background/40 p-6 rounded-lg border border-border/40">
                          <Markdown 
                            content={job.requirements || "No specific requirements provided."} 
                            className="text-muted-foreground"
                          />
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
                <span className="font-medium text-foreground">{totalCalls}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Completed calls</span>
                <span className="font-medium text-foreground">
                  {completedCallsCount}
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
