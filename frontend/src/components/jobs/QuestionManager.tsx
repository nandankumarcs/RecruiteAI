import { useState, useEffect, useRef, useCallback } from "react";
import {
  Plus,
  Trash2,
  GripVertical,
  HelpCircle,
  Loader2,
  Sparkles,
  Play,
  Square,
  RefreshCw,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/context/ToastContext";
import { motion, Reorder } from "framer-motion";

interface Question {
  id: string;
  question_text: string;
  category: string;
  difficulty: number;
  order_index: number;
}

/** TTS status per question: ready | pending | failed | missing */
type AudioStatus = "ready" | "pending" | "failed" | "missing";

interface QuestionManagerProps {
  jobId: string;
}

export function QuestionManager({ jobId }: QuestionManagerProps) {
  const { toast } = useToast();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [newQuestionText, setNewQuestionText] = useState("");

  // Audio state
  const [audioStatuses, setAudioStatuses] = useState<Record<string, AudioStatus>>({});
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [regenIds, setRegenIds] = useState<Set<string>>(new Set());
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---------------------------------------------------------------------------
  // Audio status helpers
  // ---------------------------------------------------------------------------
  const fetchAudioStatuses = useCallback(async () => {
    try {
      const res = await api.get(`/jobs/${jobId}/questions/audio-status`);
      setAudioStatuses(res.data as Record<string, AudioStatus>);
    } catch {
      // Non-critical — keep existing statuses
    }
  }, [jobId]);

  /** Poll until no statuses are "pending" or we time out after 2 minutes. */
  const startPollingIfNeeded = useCallback(
    (statuses: Record<string, AudioStatus>) => {
      const hasPending = Object.values(statuses).some((s) => s === "pending");
      if (!hasPending) return;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);

      const poll = async (deadline: number) => {
        if (Date.now() > deadline) return;
        await fetchAudioStatuses();
        setAudioStatuses((prev) => {
          const stillPending = Object.values(prev).some((s) => s === "pending");
          if (stillPending) {
            pollTimerRef.current = setTimeout(() => void poll(deadline), 3000);
          }
          return prev;
        });
      };
      pollTimerRef.current = setTimeout(() => void poll(Date.now() + 120_000), 3000);
    },
    [fetchAudioStatuses],
  );

  // Stop current audio playback
  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    setPlayingId(null);
  }, []);

  // ---------------------------------------------------------------------------
  // Play a question's TTS audio
  // ---------------------------------------------------------------------------
  const handlePlay = useCallback(
    async (question: Question) => {
      // Stop if already playing this one
      if (playingId === question.id) {
        stopAudio();
        return;
      }
      stopAudio();

      try {
        const res = await api.get(
          `/jobs/${jobId}/questions/${question.id}/audio/file`,
          { responseType: "blob" },
        );
        const url = URL.createObjectURL(res.data as Blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        setPlayingId(question.id);
        audio.onended = () => {
          URL.revokeObjectURL(url);
          setPlayingId(null);
          audioRef.current = null;
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          setPlayingId(null);
          audioRef.current = null;
          toast({ variant: "error", title: "Playback failed" });
        };
        void audio.play();
      } catch {
        toast({ variant: "error", title: "Could not load audio" });
      }
    },
    [jobId, playingId, stopAudio, toast],
  );

  // ---------------------------------------------------------------------------
  // Regenerate a question's TTS audio
  // ---------------------------------------------------------------------------
  const handleRegenerate = useCallback(
    async (question: Question) => {
      if (regenIds.has(question.id)) return;
      setRegenIds((prev) => new Set(prev).add(question.id));
      setAudioStatuses((prev) => ({ ...prev, [question.id]: "pending" }));

      try {
        await api.post(`/jobs/${jobId}/questions/${question.id}/audio/regenerate`);
        toast({ variant: "success", title: "Regenerating audio…", description: "This may take a few seconds." });
        // Start polling to detect when it becomes ready
        startPollingIfNeeded({ [question.id]: "pending" });
      } catch {
        toast({ variant: "error", title: "Regeneration failed" });
        setAudioStatuses((prev) => ({ ...prev, [question.id]: "failed" }));
      } finally {
        setRegenIds((prev) => {
          const next = new Set(prev);
          next.delete(question.id);
          return next;
        });
      }
    },
    [jobId, regenIds, startPollingIfNeeded, toast],
  );

  // ---------------------------------------------------------------------------
  // Fetch questions + audio statuses on mount
  // ---------------------------------------------------------------------------
  const fetchQuestions = useCallback(async () => {
    try {
      setIsLoading(true);
      const response = await api.get(`/jobs/${jobId}/questions`);
      setQuestions(response.data);
    } catch {
      toast({ variant: "error", title: "Load failed", description: "Could not retrieve interview questions." });
    } finally {
      setIsLoading(false);
    }
  }, [jobId, toast]);

  useEffect(() => {
    void fetchQuestions();
  }, [fetchQuestions]);

  useEffect(() => {
    if (!isLoading && questions.length > 0) {
      void fetchAudioStatuses();
    }
  }, [isLoading, questions.length, fetchAudioStatuses]);

  // Start polling whenever statuses change and there are pending ones
  useEffect(() => {
    startPollingIfNeeded(audioStatuses);
  }, [audioStatuses, startPollingIfNeeded]);

  // Cleanup
  useEffect(
    () => () => {
      stopAudio();
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    },
    [stopAudio],
  );

  // ---------------------------------------------------------------------------
  // Reorder
  // ---------------------------------------------------------------------------
  const handleReorder = async (newOrder: Question[]) => {
    setQuestions(newOrder);
    try {
      const updates = newOrder.map((q, i) => ({ id: q.id, order_index: i }));
      await api.patch(`/jobs/${jobId}/questions/reorder`, { questions: updates });
    } catch {
      console.error("Failed to update question order");
    }
  };

  // ---------------------------------------------------------------------------
  // Add question
  // ---------------------------------------------------------------------------
  const handleAddQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newQuestionText.trim()) return;
    setIsAdding(true);
    try {
      const response = await api.post(`/jobs/${jobId}/questions`, {
        question_text: newQuestionText,
        category: "general",
        difficulty: 1,
        order_index: questions.length,
      });
      const newQ = response.data as Question;
      setQuestions((prev) => [...prev, newQ]);
      setAudioStatuses((prev) => ({ ...prev, [newQ.id]: "missing" }));
      setNewQuestionText("");
      toast({ variant: "success", title: "Question added", description: "The new question has been saved to this job." });
    } catch {
      toast({ variant: "error", title: "Save failed", description: "We couldn't add the question just now." });
    } finally {
      setIsAdding(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Generate questions
  // ---------------------------------------------------------------------------
  const handleGenerateQuestions = async () => {
    setIsGenerating(true);
    try {
      const response = await api.post(`/jobs/${jobId}/questions/generate`);
      const generated = (response.data.questions ?? []) as Question[];
      setQuestions(generated);
      // Mark all as pending (audio will be generated in background)
      const pending: Record<string, AudioStatus> = {};
      generated.forEach((q) => { pending[q.id] = "pending"; });
      setAudioStatuses(pending);
      startPollingIfNeeded(pending);
      toast({ variant: "success", title: "Questions generated", description: "AI has generated a set of questions based on your job description." });
    } catch {
      toast({ variant: "error", title: "Generation failed", description: "We couldn't generate AI questions at this time." });
    } finally {
      setIsGenerating(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Delete question
  // ---------------------------------------------------------------------------
  const handleDeleteQuestion = async (questionId: string) => {
    if (playingId === questionId) stopAudio();
    try {
      await api.delete(`/jobs/${jobId}/questions/${questionId}`);
      setQuestions((prev) => prev.filter((q) => q.id !== questionId));
      setAudioStatuses((prev) => { const next = { ...prev }; delete next[questionId]; return next; });
      toast({ variant: "success", title: "Question removed" });
    } catch {
      toast({ variant: "error", title: "Delete failed" });
    }
  };

  // ---------------------------------------------------------------------------
  // Per-question audio controls
  // ---------------------------------------------------------------------------
  function AudioControls({ question }: { question: Question }) {
    const status = audioStatuses[question.id] ?? "missing";
    const isPlaying = playingId === question.id;
    const isRegen = regenIds.has(question.id);

    return (
      <div className="flex items-center gap-1 flex-shrink-0">
        {/* Play / warning button */}
        {status === "ready" ? (
          <Button
            variant="ghost"
            size="icon"
            title={isPlaying ? "Stop preview" : "Preview audio"}
            onClick={() => void handlePlay(question)}
            className={`h-8 w-8 transition-all ${
              isPlaying
                ? "text-primary bg-primary/10 hover:bg-primary/20"
                : "text-muted-foreground/50 hover:text-primary hover:bg-primary/10"
            }`}
          >
            {isPlaying ? <Square className="h-3.5 w-3.5 fill-current" /> : <Play className="h-3.5 w-3.5 fill-current" />}
          </Button>
        ) : status === "pending" ? (
          <div className="h-8 w-8 flex items-center justify-center">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground/50" />
          </div>
        ) : (
          /* missing | failed */
          <div
            className="h-8 w-8 flex items-center justify-center"
            title={status === "failed" ? "TTS generation failed — click regenerate" : "TTS audio not generated yet"}
          >
            <AlertTriangle className={`h-3.5 w-3.5 ${status === "failed" ? "text-destructive/70" : "text-amber-500/70"}`} />
          </div>
        )}

        {/* Regenerate button */}
        <Button
          variant="ghost"
          size="icon"
          title="Regenerate TTS audio"
          disabled={isRegen || status === "pending"}
          onClick={() => void handleRegenerate(question)}
          className="h-8 w-8 text-muted-foreground/40 hover:text-primary hover:bg-primary/10 transition-all"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isRegen ? "animate-spin" : ""}`} />
        </Button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="flex h-48 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between px-2">
        <h3 className="text-3xl font-black tracking-tighter uppercase">INTERVIEW QUESTIONS</h3>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={handleGenerateQuestions}
            disabled={isGenerating}
            className="h-10 px-4 rounded-lg font-black tracking-tight border-primary/20 hover:bg-primary/5 text-primary"
          >
            {isGenerating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Sparkles className="mr-2 h-4 w-4" />}
            AI GENERATE
          </Button>
          <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
            {questions.length} QUESTIONS
          </Badge>
        </div>
      </div>

      <Card className="border-border/40 bg-card/40 backdrop-blur-xl shadow-md rounded-lg overflow-hidden">
        <CardHeader className="border-b border-border/40 bg-muted/30">
          <CardTitle className="text-xl font-black tracking-tight uppercase flex items-center gap-2">
            <HelpCircle className="h-5 w-5 text-primary" />
            Interview Script
          </CardTitle>
        </CardHeader>
        <CardContent className="p-8 space-y-8">
          <form onSubmit={handleAddQuestion} className="flex gap-4">
            <Input
              placeholder="Type a new interview question here..."
              value={newQuestionText}
              onChange={(e) => setNewQuestionText(e.target.value)}
              className="h-14 rounded-lg border-border/40 bg-background/50 text-lg font-medium focus:ring-primary/20"
            />
            <Button
              type="submit"
              disabled={isAdding || !newQuestionText.trim()}
              className="h-14 px-8 rounded-lg font-black tracking-tight"
            >
              {isAdding ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plus className="mr-2 h-5 w-5" />}
              ADD
            </Button>
          </form>

          {questions.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/60 bg-background/20 p-12 text-center">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-muted/50 mb-4">
                <HelpCircle className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <h4 className="text-xl font-bold mb-1">No questions yet</h4>
              <p className="text-muted-foreground max-w-xs mx-auto">
                Add manual questions to define the structure of your AI-led interviews for this job.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <Reorder.Group axis="y" values={questions} onReorder={handleReorder} className="space-y-4">
                {questions.map((question, index) => (
                  <Reorder.Item
                    key={question.id}
                    value={question}
                    className="group flex items-start gap-4 rounded-xl border border-border/40 bg-background/40 p-6 transition-all hover:bg-background/60 hover:shadow-lg"
                  >
                    <div className="flex-shrink-0 mt-1 cursor-grab active:cursor-grabbing text-muted-foreground/30 group-hover:text-muted-foreground/70">
                      <GripVertical className="h-5 w-5" />
                    </div>
                    <div className="flex-grow space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10 text-[10px] font-black text-primary">
                          {index + 1}
                        </span>
                        <Badge variant="secondary" className="text-[10px] font-bold uppercase tracking-widest px-2 py-0">
                          {question.category}
                        </Badge>
                      </div>
                      <p className="text-lg font-bold leading-tight tracking-tight text-foreground/90">
                        {question.question_text}
                      </p>
                    </div>

                    {/* Audio controls */}
                    <AudioControls question={question} />

                    {/* Delete */}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleDeleteQuestion(question.id)}
                      className="flex-shrink-0 text-muted-foreground/40 hover:bg-destructive/10 hover:text-destructive transition-all"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </Reorder.Item>
                ))}
              </Reorder.Group>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
