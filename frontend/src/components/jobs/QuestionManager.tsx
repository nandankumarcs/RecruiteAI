import { useState, useEffect } from "react";
import { Plus, Trash2, GripVertical, HelpCircle, Loader2 } from "lucide-react";
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

interface QuestionManagerProps {
  jobId: string;
}

export function QuestionManager({ jobId }: QuestionManagerProps) {
  const { toast } = useToast();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAdding, setIsAdding] = useState(false);
  const [newQuestionText, setNewQuestionText] = useState("");

  const fetchQuestions = async () => {
    try {
      setIsLoading(true);
      const response = await api.get(`/jobs/${jobId}/questions`);
      setQuestions(response.data);
    } catch (error) {
      console.error("Failed to fetch questions", error);
      toast({
        variant: "error",
        title: "Load failed",
        description: "Could not retrieve interview questions.",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void fetchQuestions();
  }, [jobId]);

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
      setQuestions([...questions, response.data]);
      setNewQuestionText("");
      toast({
        variant: "success",
        title: "Question added",
        description: "The new question has been saved to this job.",
      });
    } catch (error) {
      console.error("Failed to add question", error);
      toast({
        variant: "error",
        title: "Save failed",
        description: "We couldn't add the question just now.",
      });
    } finally {
      setIsAdding(false);
    }
  };

  const handleDeleteQuestion = async (questionId: string) => {
    try {
      await api.delete(`/jobs/${jobId}/questions/${questionId}`);
      setQuestions(questions.filter((q) => q.id !== questionId));
      toast({
        variant: "success",
        title: "Question removed",
      });
    } catch (error) {
      console.error("Failed to delete question", error);
      toast({
        variant: "error",
        title: "Delete failed",
      });
    }
  };

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
        <h3 className="text-3xl font-black tracking-tighter uppercase">INTERVIEW STRATEGY</h3>
        <Badge variant="outline" className="font-black tracking-tight uppercase px-4 py-1.5 rounded-lg border-primary/20 bg-primary/10 text-primary">
          {questions.length} QUESTIONS
        </Badge>
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
              <Reorder.Group axis="y" values={questions} onReorder={setQuestions} className="space-y-4">
                {questions.map((question) => (
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
                          {question.order_index + 1}
                        </span>
                        <Badge variant="secondary" className="text-[10px] font-bold uppercase tracking-widest px-2 py-0">
                          {question.category}
                        </Badge>
                      </div>
                      <p className="text-lg font-bold leading-tight tracking-tight text-foreground/90">
                        {question.question_text}
                      </p>
                    </div>
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
              <p className="text-xs font-bold text-muted-foreground/50 uppercase tracking-widest text-center pt-4">
                Tip: Drag handles to reorder your interview flow
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
