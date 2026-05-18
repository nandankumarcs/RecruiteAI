import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Briefcase,
  FileText,
  Mail,
  Phone,
  Sparkles,
  Calendar,
  PhoneCall,
  Loader2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { CallRecord } from "@/lib/calls";
import { useToast } from "@/context/ToastContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import type { Resume } from "./ResumeTable";

interface CallStartResponse {
  provider: string;
  call: CallRecord;
  join_url?: string | null;
}

interface ResumeDetailModalProps {
  resume: Resume | null;
  activeCall?: CallRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onCallUpdate?: (call: CallRecord) => void;
}


const recommendationClasses: Record<string, string> = {
  advance: "bg-emerald-500 text-white border-none",
  hold: "bg-amber-500 text-white border-none",
  reject: "bg-rose-500 text-white border-none",
  insufficient_data: "bg-slate-500 text-white border-none",
};

import { useCallWebSocket } from "@/hooks/useCallWebSocket";

/** Open the browser-telephony simulator as a centred popup sized for the
 *  iPhone 17 Pro Max mockup. Falls back to a full tab if the popup is blocked,
 *  and calls `onBlocked` so the UI can surface a manual-open affordance. */
function openSimulatorPopup(
  url: string,
  onBlocked?: (url: string | null) => void,
) {
  const W = 480;   // wide enough to show phone frame + OS chrome
  const H = 960;   // phone frame 870 px + OS title bar ~28 px + safe margin
  const left = Math.round((screen.width  - W) / 2);
  const top  = Math.round((screen.height - H) / 2);
  const features = [
    `width=${W}`,
    `height=${H}`,
    `left=${left}`,
    `top=${top}`,
    "resizable=no",
    "scrollbars=no",
    "toolbar=no",
    "menubar=no",
    "location=no",
    "status=no",
  ].join(",");
  const popup = window.open(url, "recruiteai_simulator", features);
  if (!popup) {
    // Popup blocked — open in a new tab as last resort and let the caller show a retry UI.
    window.open(url, "_blank", "noopener");
    onBlocked?.(url);
  } else {
    onBlocked?.(null); // clear any previous blocked state
    popup.focus();
  }
}


export function ResumeDetailModal({
  resume,
  activeCall,
  isOpen,
  onClose,
  onCallUpdate,
}: ResumeDetailModalProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isStartingCall, setIsStartingCall] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [startedCallInternal, setStartedCallInternal] = useState<CallRecord | null>(activeCall ?? null);
  const [editablePhoneNumber, setEditablePhoneNumber] = useState(resume?.phone_number || "");
  // Populated when the browser blocked the simulator popup — lets the user open it manually.
  const [blockedSimUrl, setBlockedSimUrl] = useState<string | null>(null);

  const { lastCall } = useCallWebSocket(isOpen ? (startedCallInternal?.id || activeCall?.id) : undefined, onCallUpdate);
  const startedCall = lastCall ?? startedCallInternal;

  useEffect(() => {
    if (resume && isOpen) {
      setEditablePhoneNumber(resume.phone_number || "");
    }

    if (!resume || !isOpen) {
      setStartedCallInternal(activeCall ?? null);
      setCallError(null);
      return;
    }

  }, [resume, isOpen, activeCall]);


  if (!resume) return null;

  const parsedData = resume.parsed_data || {};
  const skills = parsedData.skills || [];
  const experience = parsedData.experience || [];



  const handleStartCall = async () => {
    if (!resume) return;

    setIsStartingCall(true);
    setCallError(null);

    try {
      const response = await api.post<CallStartResponse>(
        `/resumes/${resume.id}/calls/start`,
        { phone_number: editablePhoneNumber }
      );
      setStartedCallInternal(response.data.call);
      onCallUpdate?.(response.data.call);
      // Browser simulator: open the candidate-side call page as a centred popup
      // that's sized for the iPhone 17 Pro Max mockup (415 px wide phone + chrome).
      if (response.data.join_url) {
        openSimulatorPopup(response.data.join_url, setBlockedSimUrl);
      }
      toast({
        variant: "success",
        title: "Call started",
        description: response.data.join_url
          ? "Simulator opening — accept the call in the new window."
          : "The interview call has been queued successfully.",
      });
    } catch (error) {
      console.error("Failed to start interview call", error);
      setCallError("Call initiation failed. Please try again.");
      toast({
        variant: "error",
        title: "Call start failed",
        description: "We couldn't start the interview call just now.",
      });
    } finally {
      setIsStartingCall(false);
    }
  };


  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-6xl p-0 overflow-hidden bg-background/95 backdrop-blur-2xl border-border/40 shadow-2xl animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        <div className="sticky top-0 z-50 flex items-center justify-between px-8 py-6 border-b border-border/40 bg-background/60 backdrop-blur-xl">
          <div className="flex items-center gap-5">
            <Avatar className="h-14 w-14 border-2 border-primary/20 shadow-sm">
              <AvatarFallback className="bg-primary/10 text-primary font-black text-xl">
                {resume.candidate_name?.split(' ').map(n => n[0]).join('').toUpperCase() || "?"}
              </AvatarFallback>
            </Avatar>
            <div>
              <DialogTitle className="text-3xl font-black tracking-tighter">
                {resume.candidate_name || "Unknown Candidate"}
              </DialogTitle>
              <div className="flex items-center gap-3 mt-1">
                <Badge variant="secondary" className="bg-primary/10 text-primary border-primary/20 font-bold text-[10px] uppercase tracking-widest px-2">
                  {resume.status}
                </Badge>
                <span className="text-xs font-bold text-muted-foreground/60 uppercase tracking-widest flex items-center gap-1.5">
                  <Calendar className="h-3 w-3" />
                  {new Date(resume.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Match Insights Header (New) */}
        {resume.matching_score !== null && (
          <div className="px-8 py-3 bg-primary/5 border-b border-primary/10 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles className="h-4 w-4 text-primary animate-pulse" />
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-primary">AI Match Analysis</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-32 rounded-full bg-primary/10 overflow-hidden">
                <div 
                  className="h-full bg-primary transition-all duration-1000" 
                  style={{ width: `${resume.matching_score}%` }} 
                />
              </div>
              <span className="text-sm font-black text-primary">{Math.round(resume.matching_score)}%</span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 flex-1 min-h-0 overflow-hidden">
          {/* Left Sidebar - Quick Info */}
          <div className="lg:col-span-4 border-r border-border/40 bg-muted/20 p-8 space-y-10 overflow-y-auto hidden lg:block custom-scrollbar">
            <div className="space-y-5">
              <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/80">Contact Details</h4>
              <div className="space-y-4">
                <div className="group flex flex-col gap-1 rounded-xl border border-border/40 bg-background/40 p-4 transition-all hover:border-primary/40 hover:bg-background/60">
                  <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/60 mb-1">Email Address</span>
                  <div className="flex items-center gap-3">
                    <Mail className="h-4 w-4 text-primary" />
                    <span className="text-sm font-bold truncate selection:bg-primary/20">{resume.email || "No email provided"}</span>
                  </div>
                </div>
                <div className="group flex flex-col gap-1 rounded-xl border border-border/40 bg-background/40 p-4 transition-all hover:border-primary/40 hover:bg-background/60">
                  <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground/60 mb-1">Phone Number</span>
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-primary" />
                    <span className="text-sm font-bold truncate selection:bg-primary/20">{resume.phone_number || "No phone provided"}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-5">
              <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/80">Candidate Summary</h4>
              <div className="relative">
                <div className="absolute -left-2 top-0 bottom-0 w-1 bg-primary/20 rounded-full" />
                <p className="text-sm leading-relaxed text-muted-foreground font-medium pl-4 py-1">
                  {parsedData.summary || "No executive summary extracted yet."}
                </p>
              </div>
            </div>

            {skills.length > 0 && (
              <div className="space-y-5">
                <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/80">Core Expertise</h4>
                <div className="flex flex-wrap gap-2">
                  {skills.map((skill: string | { name: string; proficiency?: string; category?: string }, i: number) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="px-3 py-1 text-[10px] font-black uppercase tracking-tighter bg-primary/5 text-primary border border-primary/10 hover:bg-primary/10 transition-colors cursor-default"
                    >
                      {typeof skill === "string" ? skill : skill.name}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {resume.match_explanation && (
              <div className="space-y-5">
                <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-muted-foreground/80">Match Justification</h4>
                <div className="bg-primary/5 border border-primary/10 rounded-xl p-5 relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-2 opacity-5">
                    <Sparkles className="h-12 w-12 text-primary" />
                  </div>
                  <p className="text-xs leading-relaxed text-foreground/90 font-medium relative z-10">
                    {resume.match_explanation}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Main Content Area */}
          <div className="lg:col-span-8 p-0 overflow-y-auto h-full custom-scrollbar">
            <div className="p-6 space-y-10 pb-20">
              {/* Interview Call Section (Highest Priority) */}
              <section className="space-y-4">
                <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.2em] text-primary">
                  <PhoneCall className="h-4 w-4" />
                  Interview Automation
                </div>
                
                <div className="relative overflow-hidden rounded-xl border border-primary/30 bg-primary/5 p-8 shadow-lg shadow-primary/5">
                  <div className="absolute top-0 right-0 p-6 opacity-10">
                    <Sparkles className="h-32 w-32 text-primary" />
                  </div>

                  {startedCall ? (
                    <div className="space-y-6 relative z-10">
                      <div className="flex items-center justify-between">
                        <div className="space-y-2">
                          <div className="flex items-center gap-3 font-black text-2xl tracking-tighter">
                            <span className="relative flex h-4 w-4">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                              <span className="relative inline-flex rounded-full h-4 w-4 bg-emerald-500"></span>
                            </span>
                            CALL {startedCall.status.toUpperCase()}
                          </div>
                          <p className="text-sm text-muted-foreground font-bold uppercase tracking-widest flex items-center gap-2">
                            <Calendar className="size-3" />
                            {new Date(startedCall.created_at).toLocaleString()}
                          </p>
                        </div>
                        <Button 
                          onClick={() => { onClose(); navigate(`/calls/${startedCall.id}`); }}
                          className="rounded-lg font-black tracking-tight h-14 px-10 shadow-xl shadow-primary/20 hover:scale-105 transition-transform"
                        >
                          OPEN WORKSPACE
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-6 relative z-10">
                      <div className="space-y-2">
                        <h5 className="font-black text-2xl tracking-tighter">Launch AI Screening</h5>
                     
                      </div>
                      <div className="space-y-2 max-w-2xl">
                        <Label htmlFor="phone" className="text-[10px] font-black uppercase tracking-widest text-primary/70">Candidate Phone Number</Label>
                        <div className="flex flex-col sm:flex-row gap-3 items-stretch">
                          <Input 
                            id="phone"
                            type="tel"
                            placeholder="+1234567890"
                            value={editablePhoneNumber}
                            onChange={(e) => setEditablePhoneNumber(e.target.value)}
                            className="h-14 bg-background/50 border-primary/20 font-bold focus:border-primary transition-all flex-1"
                          />
                          <Button
                            size="lg"
                            onClick={handleStartCall}
                            disabled={resume.status !== "parsed" || !editablePhoneNumber || isStartingCall}
                            className="rounded-xl h-14 font-black tracking-tight shadow-xl shadow-primary/20 hover:scale-[1.02] active:scale-95 transition-all px-8 whitespace-nowrap"
                          >
                            {isStartingCall ? (
                              <Loader2 className="mr-2 h-6 w-6 animate-spin" />
                            ) : (
                              <PhoneCall className="mr-2 h-6 w-6" />
                            )}
                            START INTERVIEW CALL
                          </Button>
                        </div>
                      </div>
                      {!editablePhoneNumber && (
                        <div className="flex items-center justify-center gap-2 px-4 py-2 bg-destructive/10 rounded-lg border border-destructive/20">
                           <span className="text-[10px] font-black text-destructive uppercase tracking-widest text-center">
                            ⚠ Missing phone number for this candidate
                          </span>
                        </div>
                      )}
                      {callError && (
                        <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-xs font-bold uppercase tracking-wider text-destructive">
                          {callError}
                        </div>
                      )}
                      {blockedSimUrl && (
                        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-400 flex items-center justify-between gap-3">
                          <span>Popup was blocked by your browser.</span>
                          <button
                            className="font-bold underline underline-offset-2 whitespace-nowrap hover:text-amber-300 transition"
                            onClick={() => openSimulatorPopup(blockedSimUrl, setBlockedSimUrl)}
                          >
                            Open Simulator ↗
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </section>

              {/* AI Evaluation Insights (Phase 4) */}
              {startedCall?.ai_evaluation && (
                <section className="space-y-6">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.2em] text-emerald-500">
                    <Sparkles className="h-4 w-4" />
                    Interview Insights
                  </div>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-6 space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black uppercase tracking-widest text-emerald-600/80">Behavioral Score</span>
                        <span className="text-2xl font-black text-emerald-600">
                          {typeof (startedCall.ai_evaluation as any).behavioral_score === "number"
                            ? `${(startedCall.ai_evaluation as any).behavioral_score}/10`
                            : "N/A"}
                        </span>
                      </div>
                      <p className="text-xs font-medium leading-relaxed text-emerald-900/70">
                        {(startedCall.ai_evaluation as any).behavioral_summary || "Not enough reliable behavioral evidence was available."}
                      </p>
                    </div>

                    <div className="bg-primary/5 border border-primary/20 rounded-xl p-6 space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-black uppercase tracking-widest text-primary/80">Overall Fit</span>
                        <span className="text-2xl font-black text-primary">
                          {typeof (startedCall.ai_evaluation as any).overall_score === "number"
                            ? `${(startedCall.ai_evaluation as any).overall_score}/10`
                            : "N/A"}
                        </span>
                      </div>
                      <Badge variant="outline" className={cn(
                        "font-black uppercase tracking-widest",
                        recommendationClasses[(startedCall.ai_evaluation as any).recommendation] ?? recommendationClasses.insufficient_data
                      )}>
                        {(startedCall.ai_evaluation as any).recommendation}
                      </Badge>
                      {(startedCall.ai_evaluation as any).status !== "completed_evaluation" ? (
                        <p className="text-xs font-medium leading-relaxed text-muted-foreground">
                          This call was not scored as a full interview because the transcript did not contain enough reliable evidence.
                        </p>
                      ) : null}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="space-y-3">
                      <h6 className="text-[10px] font-black uppercase tracking-widest text-emerald-600">Strengths</h6>
                      <ul className="space-y-2">
                        {(startedCall.ai_evaluation as any).strengths?.map((s: string, i: number) => (
                          <li key={i} className="flex gap-2 text-xs font-medium text-muted-foreground leading-tight">
                            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                            {s}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="space-y-3">
                      <h6 className="text-[10px] font-black uppercase tracking-widest text-rose-600">Development Areas</h6>
                      <ul className="space-y-2">
                        {(startedCall.ai_evaluation as any).weaknesses?.map((w: string, i: number) => (
                          <li key={i} className="flex gap-2 text-xs font-medium text-muted-foreground leading-tight">
                            <div className="h-1.5 w-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                            {w}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="p-4 bg-muted/30 rounded-lg border border-border/40">
                    <p className="text-sm font-medium leading-relaxed italic text-muted-foreground">
                      "{(startedCall.ai_evaluation as any).remarks}"
                    </p>
                  </div>
                </section>
              )}


              {/* Work History */}
              {experience.length > 0 && (
                <section className="space-y-4">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.2em] text-muted-foreground">
                    <Briefcase className="h-4 w-4" />
                    Professional History
                  </div>
                  <div className="space-y-8 relative before:absolute before:left-[11px] before:top-2 before:bottom-2 before:w-[2px] before:bg-gradient-to-b before:from-primary/40 before:via-border before:to-transparent">
                    {experience.map((exp: any, i: number) => (
                      <div key={i} className="relative pl-10 group">
                        <div className="absolute left-0 top-1.5 h-6 w-6 rounded-full bg-background border-2 border-primary/40 flex items-center justify-center z-10 group-hover:border-primary transition-colors shadow-sm">
                          <div className="h-2 w-2 rounded-full bg-primary" />
                        </div>
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                            <div className="space-y-1">
                              <h5 className="font-black text-xl leading-none tracking-tighter text-foreground/90">
                                {exp.role_title || exp.title || exp.role}
                              </h5>
                              <div className="flex items-center gap-2 text-sm font-bold text-primary/80">
                                <span>{exp.company_name || exp.company}</span>
                                {exp.location && (
                                  <>
                                    <span className="h-1 w-1 rounded-full bg-primary/30" />
                                    <span className="text-xs font-medium text-muted-foreground">{exp.location}</span>
                                  </>
                                )}
                              </div>
                            </div>
                            <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground/70 bg-muted/40 px-3 py-1 rounded-full border border-border/60">
                              {exp.duration_text || [exp.from_date || exp.start_date, exp.to_date || exp.end_date].filter(Boolean).join(" - ")}
                            </span>
                          </div>
                          {Array.isArray(exp.tasks_performed || exp.bullets) && (exp.tasks_performed || exp.bullets).length > 0 && (
                            <ul className="space-y-3 pt-1">
                              {(exp.tasks_performed || exp.bullets).map((bullet: string, bulletIndex: number) => (
                                <li key={bulletIndex} className="flex gap-3 text-sm leading-relaxed text-muted-foreground font-medium">
                                  <div className="mt-2 h-1.5 w-1.5 rounded-full bg-primary/40 flex-shrink-0" />
                                  {bullet}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between px-8 py-4 border-t border-border/40 bg-muted/30">
          <Button
            variant="ghost"
            size="sm"
            className="gap-2 text-[11px] font-bold text-muted-foreground hover:text-foreground hover:bg-background border border-border/40 rounded-lg h-9 px-4"
            onClick={async () => {
              try {
                const resp = await api.get(`/resumes/${resume.id}/file`, { responseType: "blob" });
                const url = URL.createObjectURL(resp.data);
                window.open(url, "_blank", "noopener");
                // revoke after 60s so memory isn't held forever
                setTimeout(() => URL.revokeObjectURL(url), 60_000);
              } catch {
                toast({ variant: "error", title: "Could not load resume file" });
              }
            }}
          >
            <FileText className="h-3.5 w-3.5" />
            View original resume
          </Button>
          <Button
            variant="ghost"
            onClick={onClose}
            className="rounded-lg font-black uppercase tracking-widest text-[10px] hover:bg-background h-10 px-6 border border-border/40"
          >
            DISMISS
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
