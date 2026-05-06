import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Award,
  Briefcase,
  PhoneCall,
  FileQuestion,
  FileText,
  FolderKanban,
  GraduationCap,
  Loader2,
  Mail,
  Phone,
  Sparkles,
  User,
  Code,
} from "lucide-react";

import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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

interface StartedCall {
  id: string;
  status: string;
  phone_number: string;
  twilio_call_sid: string | null;
  created_at: string;
}

interface CallStartResponse {
  provider: string;
  call: StartedCall;
}

interface ResumeDetailModalProps {
  resume: Resume | null;
  isOpen: boolean;
  onClose: () => void;
}

const difficultyClasses: Record<number, string> = {
  1: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
  2: "bg-teal-500/10 text-teal-600 border-teal-500/20",
  3: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  4: "bg-orange-500/10 text-orange-600 border-orange-500/20",
  5: "bg-rose-500/10 text-rose-600 border-rose-500/20",
};

export function ResumeDetailModal({
  resume,
  isOpen,
  onClose,
}: ResumeDetailModalProps) {
  const navigate = useNavigate();
  const [questions, setQuestions] = useState<InterviewQuestion[]>([]);
  const [isQuestionsLoading, setIsQuestionsLoading] = useState(false);
  const [isGeneratingQuestions, setIsGeneratingQuestions] = useState(false);
  const [questionsError, setQuestionsError] = useState<string | null>(null);
  const [isStartingCall, setIsStartingCall] = useState(false);
  const [callError, setCallError] = useState<string | null>(null);
  const [startedCall, setStartedCall] = useState<StartedCall | null>(null);

  useEffect(() => {
    if (!resume || !isOpen || resume.status !== "parsed") {
      setQuestions([]);
      setQuestionsError(null);
      setStartedCall(null);
      setCallError(null);
      return;
    }

    const loadQuestions = async () => {
      setIsQuestionsLoading(true);
      setQuestionsError(null);

      try {
        const response = await api.get<QuestionSetResponse>(
          `/resumes/${resume.id}/questions`
        );
        setQuestions(response.data.questions || []);
      } catch (error) {
        console.error("Failed to load interview questions", error);
        setQuestionsError("Unable to load interview questions right now.");
      } finally {
        setIsQuestionsLoading(false);
      }
    };

    void loadQuestions();
  }, [resume, isOpen]);

  if (!resume) return null;

  const parsedData = resume.parsed_data || {};
  const skills = parsedData.skills || [];
  const experience = parsedData.experience || [];
  const projects = parsedData.projects || [];
  const education = parsedData.education || [];
  const certifications = parsedData.certifications || [];
  const skillCategories = parsedData.skill_categories || [];

  const handleGenerateQuestions = async () => {
    if (!resume) return;

    setIsGeneratingQuestions(true);
    setQuestionsError(null);

    try {
      const response = await api.post<QuestionSetResponse>(
        `/resumes/${resume.id}/questions/generate`
      );
      setQuestions(response.data.questions || []);
    } catch (error) {
      console.error("Failed to generate interview questions", error);
      setQuestionsError("Question generation failed. Please try again.");
    } finally {
      setIsGeneratingQuestions(false);
    }
  };

  const handleStartCall = async () => {
    if (!resume) return;

    setIsStartingCall(true);
    setCallError(null);

    try {
      const response = await api.post<CallStartResponse>(
        `/resumes/${resume.id}/calls/start`
      );
      setStartedCall(response.data.call);
    } catch (error) {
      console.error("Failed to start interview call", error);
      setCallError("Call initiation failed. Please try again.");
    } finally {
      setIsStartingCall(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl bg-card/95 backdrop-blur-xl border-border/50">
        <DialogHeader>
          <div className="mb-2 flex items-center gap-4">
            <div className="rounded-xl bg-primary/10 p-3 text-primary">
              <User className="h-6 w-6" />
            </div>
            <div>
              <DialogTitle className="text-2xl font-bold">
                {resume.candidate_name || "Unknown Candidate"}
              </DialogTitle>
              <DialogDescription>
                Uploaded on {new Date(resume.created_at).toLocaleDateString()}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="grid max-h-[68vh] gap-6 overflow-y-auto py-4 pr-2">
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 p-3 text-sm text-muted-foreground">
              <Mail className="h-4 w-4 text-primary" />
              {resume.email || "No email"}
            </div>
            <div className="flex items-center gap-2 rounded-lg border border-border/50 bg-muted/30 p-3 text-sm text-muted-foreground">
              <Phone className="h-4 w-4 text-primary" />
              {resume.phone_number || "No phone"}
            </div>
          </div>

          {skills.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Code className="h-4 w-4 text-primary" />
                Skills
              </div>
              <div className="flex flex-wrap gap-2">
                {skills.map((skill: string, i: number) => (
                  <Badge
                    key={i}
                    variant="secondary"
                    className="border-primary/10 bg-primary/5 text-primary"
                  >
                    {skill}
                  </Badge>
                ))}
              </div>
              {skillCategories.length > 0 && (
                <div className="space-y-2">
                  {skillCategories.map((category: any, i: number) => (
                    <div key={i} className="text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">
                        {category.category}:
                      </span>{" "}
                      {(category.items || []).join(", ")}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {experience.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Briefcase className="h-4 w-4 text-primary" />
                Experience
              </div>
              <div className="space-y-3">
                {experience.map((exp: any, i: number) => (
                  <div
                    key={i}
                    className="space-y-1 rounded-lg border border-border/50 bg-muted/20 p-3"
                  >
                    <div className="font-medium">
                      {exp.role_title || exp.title || exp.role || exp}
                    </div>
                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                      <span>{exp.company_name || exp.company || ""}</span>
                      <span>
                        {exp.duration_text ||
                          [exp.from_date || exp.start_date, exp.to_date || exp.end_date]
                            .filter(Boolean)
                            .join(" - ") ||
                          exp.duration ||
                          ""}
                      </span>
                    </div>
                    {exp.location && (
                      <div className="text-sm text-muted-foreground">
                        {exp.location}
                      </div>
                    )}
                    {Array.isArray(exp.tasks_performed || exp.bullets) &&
                      (exp.tasks_performed || exp.bullets).length > 0 && (
                        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                          {(exp.tasks_performed || exp.bullets).map(
                            (bullet: string, bulletIndex: number) => (
                              <li key={bulletIndex}>{bullet}</li>
                            )
                          )}
                        </ul>
                      )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 font-semibold">
                <FileQuestion className="h-4 w-4 text-primary" />
                Interview Questions
              </div>
              <Button
                onClick={handleGenerateQuestions}
                disabled={resume.status !== "parsed" || isGeneratingQuestions}
                className="min-w-40"
              >
                {isGeneratingQuestions ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-2 h-4 w-4" />
                    {questions.length > 0 ? "Regenerate" : "Generate Questions"}
                  </>
                )}
              </Button>
            </div>

            {resume.status !== "parsed" && (
              <div className="text-sm text-muted-foreground">
                Questions become available after resume parsing finishes.
              </div>
            )}

            {questionsError && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                {questionsError}
              </div>
            )}

            {isQuestionsLoading ? (
              <div className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading saved questions...
              </div>
            ) : questions.length > 0 ? (
              <div className="space-y-3">
                {questions.map((question) => (
                  <div
                    key={question.id}
                    className="rounded-lg border border-border/50 bg-background/60 p-3"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <Badge variant="outline">
                        {question.category || "general"}
                      </Badge>
                      <Badge
                        variant="secondary"
                        className={difficultyClasses[question.difficulty] || difficultyClasses[3]}
                      >
                        Difficulty {question.difficulty}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        Q{question.order_index}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed text-foreground">
                      {question.question_text}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-border/50 bg-background/40 p-4 text-sm text-muted-foreground">
                No questions have been generated for this resume yet.
              </div>
            )}
          </div>

          <div className="space-y-3 rounded-xl border border-border/50 bg-muted/20 p-4">
            <div className="flex items-center gap-2 font-semibold">
              <PhoneCall className="h-4 w-4 text-primary" />
              Interview Call
            </div>

            {startedCall ? (
              <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm">
                <div className="font-medium text-emerald-700 dark:text-emerald-400">
                  Call {startedCall.status}
                </div>
                <div className="text-muted-foreground">
                  {startedCall.phone_number} • {new Date(startedCall.created_at).toLocaleString()}
                </div>
                <Button
                  variant="link"
                  className="mt-2 h-auto p-0 text-primary"
                  onClick={() => {
                    onClose();
                    navigate(`/calls/${startedCall.id}`);
                  }}
                >
                  View call details
                </Button>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">
                Start an interview call for this parsed candidate. Questions will be generated automatically if they do not exist yet.
              </div>
            )}

            {callError && (
              <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                {callError}
              </div>
            )}

            <Button
              onClick={handleStartCall}
              disabled={
                resume.status !== "parsed" ||
                !resume.phone_number ||
                isStartingCall ||
                startedCall?.status === "queued" ||
                startedCall?.status === "ringing" ||
                startedCall?.status === "in_progress"
              }
              className="w-full"
            >
              {isStartingCall ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Starting Call
                </>
              ) : (
                <>
                  <PhoneCall className="mr-2 h-4 w-4" />
                  Start Interview Call
                </>
              )}
            </Button>
          </div>

          {projects.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <FolderKanban className="h-4 w-4 text-primary" />
                Projects
              </div>
              <div className="space-y-3">
                {projects.map((project: any, i: number) => (
                  <div
                    key={i}
                    className="space-y-2 rounded-lg border border-border/50 bg-muted/20 p-3"
                  >
                    <div className="font-medium">{project.name || "Project"}</div>
                    {Array.isArray(project.technologies) &&
                      project.technologies.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          {project.technologies.map(
                            (tech: string, techIndex: number) => (
                              <Badge key={techIndex} variant="outline">
                                {tech}
                              </Badge>
                            )
                          )}
                        </div>
                      )}
                    {Array.isArray(project.bullets) && project.bullets.length > 0 && (
                      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {project.bullets.map(
                          (bullet: string, bulletIndex: number) => (
                            <li key={bulletIndex}>{bullet}</li>
                          )
                        )}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {education.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <GraduationCap className="h-4 w-4 text-primary" />
                Education
              </div>
              <div className="space-y-3">
                {education.map((item: any, i: number) => (
                  <div
                    key={i}
                    className="space-y-1 rounded-lg border border-border/50 bg-muted/20 p-3"
                  >
                    <div className="font-medium">
                      {item.institution || "Institution"}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {[item.degree, item.field].filter(Boolean).join(" - ")}
                    </div>
                    <div className="flex items-center justify-between text-sm text-muted-foreground">
                      <span>{item.location || ""}</span>
                      <span>
                        {[item.start_date, item.end_date].filter(Boolean).join(" - ")}
                      </span>
                    </div>
                    {item.score && (
                      <div className="text-sm text-muted-foreground">
                        {item.score}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {certifications.length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 font-semibold">
                <Award className="h-4 w-4 text-primary" />
                Certifications
              </div>
              <div className="space-y-2">
                {certifications.map((cert: any, i: number) => (
                  <div
                    key={i}
                    className="rounded-lg border border-border/50 bg-muted/20 p-3 text-sm text-muted-foreground"
                  >
                    <span className="font-medium text-foreground">{cert.name}</span>
                    {cert.issuer ? ` - ${cert.issuer}` : ""}
                    {cert.year ? ` (${cert.year})` : ""}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center gap-2 font-semibold">
              <FileText className="h-4 w-4 text-primary" />
              Resume Content
            </div>
            <div className="rounded-lg border border-border/50 bg-muted/30 p-4 text-sm italic leading-relaxed text-muted-foreground">
              {parsedData.summary ||
                "No summary extracted. Full resume text is available in the storage layer."}
            </div>
          </div>
        </div>

        <DialogFooter className="border-t border-border/50 pt-4">
          <Button onClick={onClose} className="w-full sm:w-auto">
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
