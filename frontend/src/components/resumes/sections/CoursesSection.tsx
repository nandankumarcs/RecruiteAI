import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { DateTextInput } from "../editor/DateTextInput";
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface CoursesSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function CoursesSection({ form }: CoursesSectionProps) {
  const { watch, setValue } = form;
  const courses = watch("parsed_data.courses") ?? [];

  const add = () => setValue("parsed_data.courses", [...courses, { name: "" }]);
  const remove = (i: number) => setValue("parsed_data.courses", courses.filter((_, idx) => idx !== i));
  const update = (i: number, field: string, value: unknown) => {
    const next = [...courses];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.courses", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={courses}
        getKey={(_, i) => `course-${i}`}
        onReorder={(reordered) => setValue("parsed_data.courses", reordered)}
        renderItem={(course, i) => (
        <SectionCard title={course.name || "New Course"} subtitle={course.provider} defaultExpanded={!course.name} onRemove={() => remove(i)}>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Course Name *</Label>
              <Input value={course.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="Machine Learning Specialization" className="h-9 bg-background/50 border-border/40" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Provider</Label>
                <Input value={course.provider ?? ""} onChange={(e) => update(i, "provider", e.target.value)} placeholder="Coursera, Udemy, edX…" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Completion Date</Label>
                <DateTextInput value={course.completion_date} onChange={(v) => update(i, "completion_date", v)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Certificate URL</Label>
              <UrlInput value={course.credential_url} onChange={(v) => update(i, "credential_url", v)} placeholder="https://coursera.org/verify/..." />
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Course
      </Button>
    </div>
  );
}
