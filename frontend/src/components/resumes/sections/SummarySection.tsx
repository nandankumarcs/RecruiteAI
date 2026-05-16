import type { UseFormReturn } from "react-hook-form";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface SummarySectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function SummarySection({ form }: SummarySectionProps) {
  const { register, watch } = form;
  const text = watch("parsed_data.summary") ?? "";
  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Professional Summary
        </Label>
        <span
          className={`text-[11px] tabular-nums ${
            wordCount > 0 && (wordCount < 40 || wordCount > 80)
              ? "text-amber-500"
              : "text-muted-foreground/50"
          }`}
        >
          {wordCount} word{wordCount !== 1 ? "s" : ""} · recommended 40–80
        </span>
      </div>
      <Textarea
        {...register("parsed_data.summary")}
        placeholder="Write a 2–4 sentence overview of your professional background, key skills, and what you bring to this role…"
        rows={6}
        className="bg-background/50 border-border/40 resize-none leading-relaxed"
      />
    </div>
  );
}
