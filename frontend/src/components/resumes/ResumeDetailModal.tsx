import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Briefcase,
  PhoneCall,
  FileQuestion,
  Loader2,
  Mail,
  Phone,
  Sparkles,
  Calendar,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import type { CallRecord } from "@/lib/calls";
import { useToast } from "@/context/ToastContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import type { Resume } from "./ResumeTable";

interface InterviewQuestion {
  id: string;
  question_text: string;
  category: string | null;
  difficulty: number;
  order_index: number;
}

interface QuestionSetResponse {
  schema_version: string;
  questions: InterviewQuestion[];
}

interface CallStartResponse {
  provider: string;
  call: CallRecord;
}

interface ResumeDetailModalProps {
  resume: Resume | null;
  activeCall?: CallRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onCallUpdate?: (call: CallRecord) => void;
}

const difficultyClasses: Record<number, string> = {
  1: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  2: "bg-teal-500/10 text-teal-600 border-teal-500/20",
  3: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  4: "bg-orange-500/10 text-orange-600 border-orange-500/20",
  5: "bg-rose-500/10 text-rose-600 border-rose-500/20",
};

import { useCallWebSocket } from "@/hooks/useCallWebSocket";


export function ResumeDetailModal({
  resume,
  activeCall,
  isOpen,
  onClose,
  onCallUpdate,
}: ResumeDetailModalProps) {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [isQuestionsLoading, setIsQuestionsLoading] = useState(false);
  const [questionsError, setQuestionsError] = useState<string | null>(null);

  const [isStartingCall, setIsStartingCall] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [startedCallInternal, setStartedCallInternal] = useState<CallRecord | null>(activeCall ?? null);

  const { lastCall } = useCallWebSocket(isOpen ? (startedCallInternal?.id || activeCall?.id) : undefined, onCallUpdate);
  const startedCall = lastCall ?? startedCallInternal;

  useEffect(() => {
    if (!resume || !isOpen || resume.status !== "parsed") {
      setQuestions([]);
      setQuestionsError(null);
      setStartedCallInternal(activeCall ?? null);
      setCallError(null);
      return;
    }

    const loadQuestions = async () => {
      setIsQuestionsLoading(true);
      setQuestionsError(null);

      try {
        const response = await api.get<InterviewQuestion[]>(
          `/jobs/${resume.job_id}/questions`
        );
        setQuestions(response.data || []);
      } catch (error) {
        console.error("Failed to load interview questions", error);
        setQuestionsError("Unable to load interview questions right now.");
      } finally {
        setIsQuestionsLoading(false);
      }
    };

    void loadQuestions();
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
        `/resumes/${resume.id}/calls/start`
      );
      setStartedCallInternal(response.data.call);
      onCallUpdate?.(response.data.call);
      toast({
        variant: "success",
        title: "Call started",
        description: "The interview call has been queued successfully.",
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
      <DialogContent className="max-w-6xl p-0 overflow-hidden bg-background/95 backdrop-blur-2xl border-border/40 shadow-2xl animate-in zoom-in-95 duration-200">
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
          <Badge variant="outline" className="hidden sm:flex bg-background/50 border-border/40 px-3 py-1 font-bold text-[10px] uppercase tracking-tighter text-muted-foreground">
            ID: {resume.id.slice(0, 8)}
          </Badge>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 max-h-[80vh] overflow-hidden">
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
                  {skills.map((skill: string, i: number) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="px-3 py-1 text-[10px] font-black uppercase tracking-tighter bg-primary/5 text-primary border border-primary/10 hover:bg-primary/10 transition-colors cursor-default"
                    >
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Main Content Area */}
          <div className="lg:col-span-8 p-0 overflow-y-auto h-full scrollbar-thin">
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
                        <p className="text-sm text-muted-foreground leading-relaxed max-w-lg font-medium">
                          Initiate a high-fidelity voice interview. Our AI will conduct a structured screening based on the candidate's background and target role.
                        </p>
                      </div>
                      <div className="flex flex-col sm:flex-row gap-4">
                        <Button
                          size="lg"
                          onClick={handleStartCall}
                          disabled={resume.status !== "parsed" || !resume.phone_number || isStartingCall}
                          className="flex-1 rounded-xl h-14 font-black tracking-tight shadow-xl shadow-primary/20 hover:scale-[1.02] active:scale-95 transition-all"
                        >
                          {isStartingCall ? (
                            <Loader2 className="mr-2 h-6 w-6 animate-spin" />
                          ) : (
                            <PhoneCall className="mr-2 h-6 w-6" />
                          )}
                          START INTERVIEW CALL
                        </Button>
                      </div>
                      {!resume.phone_number && (
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
                    </div>
                  )}
                </div>
              </section>

              {/* Questions Section */}
              <section className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs font-black uppercase tracking-[0.2em] text-muted-foreground">
                    <FileQuestion className="h-4 w-4" />
                    Interview Strategy
                  </div>
                </div>


                {questionsError && (
                  <div className="rounded-lg border border-destructive/20 bg-destructive/10 px-4 py-3 text-xs font-bold uppercase tracking-wider text-destructive">
                    {questionsError}
                  </div>
                )}

                {questions.length > 0 ? (
                  <div className="grid gap-5">
                    {questions.map((question, idx) => (
                      <div key={question.id} className="group relative rounded-xl border border-border/40 bg-muted/5 p-6 transition-all hover:bg-background hover:border-primary/30 hover:shadow-lg hover:shadow-primary/5 active:scale-[0.99]">
                        <div className="flex items-start gap-4">
                          <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center text-xs font-black">
                            {idx + 1}
                          </div>
                          <div className="space-y-3 flex-1">
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-[9px] font-black uppercase tracking-widest bg-background/50 border-border/60">
                                {question.category || "general"}
                              </Badge>
                              <Badge className={cn("text-[9px] font-black uppercase tracking-widest shadow-sm", difficultyClasses[question.difficulty])}>
                                LVL {question.difficulty}
                              </Badge>
                            </div>
                            <p className="text-sm font-bold leading-relaxed tracking-tight text-foreground/90 group-hover:text-foreground transition-colors">
                              {question.question_text}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-xl border-2 border-dashed border-border/40 p-12 text-center bg-muted/5">
                    <div className="w-16 h-16 bg-muted/10 rounded-full flex items-center justify-center mx-auto mb-4 border border-border/40">
                      <FileQuestion className="h-8 w-8 text-muted-foreground/30" />
                    </div>
                    <p className="text-xs font-black text-muted-foreground uppercase tracking-[0.2em]">No questions added to this job yet</p>
                    <p className="text-[10px] text-muted-foreground/60 font-medium mt-2">Add manual questions in the Job Strategy tab.</p>
                  </div>
                )}

              </section>

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
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-widest text-muted-foreground/50">
            <span className="h-1.5 w-1.5 rounded-full bg-primary/40 animate-pulse" />
            LIVE ANALYSIS • V1.2.0
          </div>
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
