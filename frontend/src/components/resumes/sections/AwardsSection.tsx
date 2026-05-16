import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { DateTextInput } from "../editor/DateTextInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface AwardsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function AwardsSection({ form }: AwardsSectionProps) {
  const { watch, setValue } = form;
  const awards = watch("parsed_data.awards") ?? [];

  const add = () => setValue("parsed_data.awards", [...awards, { title: "" }]);
  const remove = (i: number) => setValue("parsed_data.awards", awards.filter((_, idx) => idx !== i));
  const update = (i: number, field: string, value: unknown) => {
    const next = [...awards];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.awards", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={awards}
        getKey={(_, i) => `award-${i}`}
        onReorder={(reordered) => setValue("parsed_data.awards", reordered)}
        renderItem={(award, i) => (
        <SectionCard title={award.title || "New Award"} subtitle={award.issuer} defaultExpanded={!award.title} onRemove={() => remove(i)}>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Award Title *</Label>
              <Input value={award.title} onChange={(e) => update(i, "title", e.target.value)} placeholder="Best Paper Award" className="h-9 bg-background/50 border-border/40" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Issuer</Label>
                <Input value={award.issuer ?? ""} onChange={(e) => update(i, "issuer", e.target.value)} placeholder="IEEE" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Date</Label>
                <DateTextInput value={award.date} onChange={(v) => update(i, "date", v)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Description</Label>
              <Textarea value={award.description ?? ""} onChange={(e) => update(i, "description", e.target.value)} rows={2} placeholder="Brief description of the award…" className="bg-background/50 border-border/40 resize-none" />
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Award
      </Button>
    </div>
  );
}
