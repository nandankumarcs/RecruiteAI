import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { BulletListEditor } from "../editor/BulletListEditor";
import { DateTextInput } from "../editor/DateTextInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface VolunteerSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function VolunteerSection({ form }: VolunteerSectionProps) {
  const { watch, setValue } = form;
  const volunteer = watch("parsed_data.volunteer") ?? [];

  const add = () => setValue("parsed_data.volunteer", [...volunteer, { role: "", organization: "", is_current: false, bullets: [] }]);
  const remove = (i: number) => setValue("parsed_data.volunteer", volunteer.filter((_, idx) => idx !== i));
  const update = (i: number, field: string, value: unknown) => {
    const next = [...volunteer];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.volunteer", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={volunteer}
        getKey={(_, i) => `vol-${i}`}
        onReorder={(reordered) => setValue("parsed_data.volunteer", reordered)}
        renderItem={(vol, i) => (
        <SectionCard title={[vol.role, vol.organization].filter(Boolean).join(" · ") || "New Role"} defaultExpanded={!vol.role} onRemove={() => remove(i)}>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Role *</Label>
                <Input value={vol.role} onChange={(e) => update(i, "role", e.target.value)} placeholder="Mentor" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Organisation *</Label>
                <Input value={vol.organization} onChange={(e) => update(i, "organization", e.target.value)} placeholder="Code for India" className="h-9 bg-background/50 border-border/40" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Cause / Category</Label>
                <Input value={vol.cause ?? ""} onChange={(e) => update(i, "cause", e.target.value)} placeholder="Education, Technology…" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</Label>
                <Input value={vol.location ?? ""} onChange={(e) => update(i, "location", e.target.value)} placeholder="Mumbai" className="h-9 bg-background/50 border-border/40" />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4 items-end">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">From</Label>
                <DateTextInput value={vol.from_date} onChange={(v) => update(i, "from_date", v)} />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">To</Label>
                <DateTextInput value={vol.is_current ? "Present" : (vol.to_date ?? "")} onChange={(v) => update(i, "to_date", v)} disabled={vol.is_current} />
              </div>
              <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer pb-1">
                <input type="checkbox" checked={vol.is_current} onChange={(e) => update(i, "is_current", e.target.checked)} className="rounded" />
                Currently
              </label>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Highlights</Label>
              <BulletListEditor value={vol.bullets ?? []} onChange={(v) => update(i, "bullets", v)} />
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Volunteer Experience
      </Button>
    </div>
  );
}
