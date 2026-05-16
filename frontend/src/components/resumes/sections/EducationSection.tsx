import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { DateTextInput } from "../editor/DateTextInput";
import { ChipTagInput } from "../editor/ChipTagInput";
import type { ResumeUpdate } from "@/lib/resume-schema";
import { DEGREE_TYPES } from "@/lib/resume-schema";

interface EducationSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function EducationSection({ form }: EducationSectionProps) {
  const { watch, setValue } = form;
  const education = watch("parsed_data.education") ?? [];

  const add = () => {
    setValue("parsed_data.education", [
      ...education,
      { institution: "", is_current: false, relevant_coursework: [] },
    ]);
  };

  const remove = (i: number) => {
    setValue("parsed_data.education", education.filter((_, idx) => idx !== i));
  };

  const update = (i: number, field: string, value: unknown) => {
    const next = [...education];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.education", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={education}
        getKey={(_, i) => `edu-${i}`}
        onReorder={(reordered) => setValue("parsed_data.education", reordered)}
        renderItem={(edu, i) => {
        const title = [edu.degree_type, edu.field_of_study].filter(Boolean).join(" in ") || edu.institution || "New Education";
        const subtitle = edu.institution && (edu.degree_type || edu.field_of_study) ? edu.institution : undefined;
        return (
          <SectionCard title={title} subtitle={subtitle} defaultExpanded={!edu.institution} onRemove={() => remove(i)}>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Institution *</Label>
                <Input value={edu.institution} onChange={(e) => update(i, "institution", e.target.value)} placeholder="MIT, IIT Bombay…" className="h-9 bg-background/50 border-border/40" />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Degree Type</Label>
                  <select value={edu.degree_type ?? ""} onChange={(e) => update(i, "degree_type", e.target.value || undefined)} className="h-9 w-full rounded-lg border border-border/40 bg-background/50 px-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary/30">
                    <option value="">Select…</option>
                    {DEGREE_TYPES.map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Field of Study</Label>
                  <Input value={edu.field_of_study ?? ""} onChange={(e) => update(i, "field_of_study", e.target.value)} placeholder="Computer Science" className="h-9 bg-background/50 border-border/40" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Minor (optional)</Label>
                  <Input value={edu.minor ?? ""} onChange={(e) => update(i, "minor", e.target.value)} placeholder="Mathematics" className="h-9 bg-background/50 border-border/40" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</Label>
                  <Input value={edu.location ?? ""} onChange={(e) => update(i, "location", e.target.value)} placeholder="Cambridge, MA" className="h-9 bg-background/50 border-border/40" />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 items-end">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">From</Label>
                  <DateTextInput value={edu.start_date} onChange={(v) => update(i, "start_date", v)} placeholder="Sep 2019" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">To / Expected</Label>
                  <DateTextInput value={edu.is_current ? "Present" : (edu.end_date ?? "")} onChange={(v) => update(i, "end_date", v)} placeholder="May 2023" disabled={edu.is_current} />
                </div>
                <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer pb-1">
                  <input type="checkbox" checked={edu.is_current} onChange={(e) => update(i, "is_current", e.target.checked)} className="rounded" />
                  Enrolled
                </label>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">GPA / Score</Label>
                  <Input value={edu.gpa ?? ""} onChange={(e) => update(i, "gpa", e.target.value)} placeholder="3.8 / 4.0" className="h-9 bg-background/50 border-border/40" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Honors</Label>
                  <Input value={edu.honors ?? ""} onChange={(e) => update(i, "honors", e.target.value)} placeholder="Summa Cum Laude, Dean's List…" className="h-9 bg-background/50 border-border/40" />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Relevant Coursework</Label>
                <ChipTagInput value={edu.relevant_coursework ?? []} onChange={(v) => update(i, "relevant_coursework", v)} placeholder="Algorithms, Machine Learning…" />
              </div>

              {(edu.degree_type === "Master's" || edu.degree_type === "Ph.D.") && (
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Thesis / Dissertation Title</Label>
                  <Input value={edu.thesis_title ?? ""} onChange={(e) => update(i, "thesis_title", e.target.value)} placeholder="Thesis title…" className="h-9 bg-background/50 border-border/40" />
                </div>
              )}
            </div>
          </SectionCard>
        );
      }}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Education
      </Button>
    </div>
  );
}
