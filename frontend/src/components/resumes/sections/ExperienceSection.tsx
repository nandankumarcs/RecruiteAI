import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { BulletListEditor } from "../editor/BulletListEditor";
import { DateTextInput } from "../editor/DateTextInput";
import { ChipTagInput } from "../editor/ChipTagInput";
import type { ResumeUpdate } from "@/lib/resume-schema";
import { EMPLOYMENT_TYPES } from "@/lib/resume-schema";

interface ExperienceSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function ExperienceSection({ form }: ExperienceSectionProps) {
  const { watch, setValue } = form;
  const experience = watch("parsed_data.experience") ?? [];

  const add = () => {
    setValue("parsed_data.experience", [
      ...experience,
      { role_title: "", company_name: "", is_current: false, is_remote: false, bullets: [], technologies: [] },
    ]);
  };

  const remove = (i: number) => {
    setValue("parsed_data.experience", experience.filter((_, idx) => idx !== i));
  };

  const update = (i: number, field: string, value: unknown) => {
    const next = [...experience];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.experience", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={experience}
        getKey={(_, i) => `exp-${i}`}
        onReorder={(reordered) => setValue("parsed_data.experience", reordered)}
        renderItem={(exp, i) => {
        const title = [exp.role_title, exp.company_name].filter(Boolean).join(" · ") || "New Position";
        const dates = [exp.from_date, exp.is_current ? "Present" : exp.to_date].filter(Boolean).join(" – ");
        return (
          <SectionCard
            title={title}
            subtitle={dates || undefined}
            defaultExpanded={!exp.role_title && !exp.company_name}
            onRemove={() => remove(i)}
          >
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Job Title</Label>
                  <Input value={exp.role_title ?? ""} onChange={(e) => update(i, "role_title", e.target.value)} placeholder="Senior Engineer" className="h-9 bg-background/50 border-border/40" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Company</Label>
                  <Input value={exp.company_name ?? ""} onChange={(e) => update(i, "company_name", e.target.value)} placeholder="Acme Corp" className="h-9 bg-background/50 border-border/40" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Employment Type</Label>
                  <select
                    value={exp.employment_type ?? ""}
                    onChange={(e) => update(i, "employment_type", e.target.value || undefined)}
                    className="h-9 w-full rounded-lg border border-border/40 bg-background/50 px-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary/30"
                  >
                    <option value="">Select type…</option>
                    {EMPLOYMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      value={exp.is_remote ? "Remote" : (exp.location ?? "")}
                      onChange={(e) => update(i, "location", e.target.value)}
                      disabled={exp.is_remote}
                      placeholder="Mumbai, India"
                      className="h-9 bg-background/50 border-border/40 flex-1"
                    />
                    <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer shrink-0">
                      <input type="checkbox" checked={exp.is_remote} onChange={(e) => { update(i, "is_remote", e.target.checked); if (e.target.checked) update(i, "location", "Remote"); }} className="rounded" />
                      Remote
                    </label>
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-4 items-end">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">From</Label>
                  <DateTextInput value={exp.from_date} onChange={(v) => update(i, "from_date", v)} placeholder="Jan 2022" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">To</Label>
                  <DateTextInput value={exp.is_current ? "Present" : (exp.to_date ?? "")} onChange={(v) => update(i, "to_date", v)} placeholder="Dec 2024" disabled={exp.is_current} />
                </div>
                <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer pb-1">
                  <input type="checkbox" checked={exp.is_current} onChange={(e) => { update(i, "is_current", e.target.checked); if (e.target.checked) update(i, "to_date", "Present"); }} className="rounded" />
                  Currently here
                </label>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Company Description</Label>
                <Input value={exp.company_description ?? ""} onChange={(e) => update(i, "company_description", e.target.value)} placeholder="Optional: 1-line about the company" className="h-9 bg-background/50 border-border/40" />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Highlights & Achievements</Label>
                <BulletListEditor value={exp.bullets ?? []} onChange={(v) => update(i, "bullets", v)} placeholder="Describe an achievement with impact…" />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Technologies Used</Label>
                <ChipTagInput value={exp.technologies ?? []} onChange={(v) => update(i, "technologies", v)} placeholder="React, Node.js, PostgreSQL…" />
              </div>
            </div>
          </SectionCard>
        );
      }}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Experience
      </Button>
    </div>
  );
}
