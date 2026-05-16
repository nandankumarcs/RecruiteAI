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
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface ProjectsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function ProjectsSection({ form }: ProjectsSectionProps) {
  const { watch, setValue } = form;
  const projects = watch("parsed_data.projects") ?? [];

  const add = () => {
    setValue("parsed_data.projects", [
      ...projects,
      { name: "", is_ongoing: false, bullets: [], technologies: [] },
    ]);
  };

  const remove = (i: number) => {
    setValue("parsed_data.projects", projects.filter((_, idx) => idx !== i));
  };

  const update = (i: number, field: string, value: unknown) => {
    const next = [...projects];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.projects", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={projects}
        getKey={(_, i) => `proj-${i}`}
        onReorder={(reordered) => setValue("parsed_data.projects", reordered)}
        renderItem={(proj, i) => (
        <SectionCard
          title={proj.name || "New Project"}
          subtitle={proj.technologies?.slice(0, 3).join(", ")}
          defaultExpanded={!proj.name}
          onRemove={() => remove(i)}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Project Name *</Label>
                <Input value={proj.name} onChange={(e) => update(i, "name", e.target.value)} placeholder="Resume Parser" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Your Role</Label>
                <Input value={proj.role ?? ""} onChange={(e) => update(i, "role", e.target.value)} placeholder="Lead Engineer" className="h-9 bg-background/50 border-border/40" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Live URL</Label>
                <UrlInput value={proj.url} onChange={(v) => update(i, "url", v)} placeholder="https://myproject.com" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Repository URL</Label>
                <UrlInput value={proj.repo_url} onChange={(v) => update(i, "repo_url", v)} placeholder="https://github.com/user/repo" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-4 items-end">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Start Date</Label>
                <DateTextInput value={proj.start_date} onChange={(v) => update(i, "start_date", v)} placeholder="Jan 2023" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">End Date</Label>
                <DateTextInput value={proj.is_ongoing ? "Ongoing" : (proj.end_date ?? "")} onChange={(v) => update(i, "end_date", v)} placeholder="Dec 2023" disabled={proj.is_ongoing} />
              </div>
              <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer pb-1">
                <input type="checkbox" checked={proj.is_ongoing} onChange={(e) => update(i, "is_ongoing", e.target.checked)} className="rounded" />
                Ongoing
              </label>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Description</Label>
              <BulletListEditor value={proj.bullets ?? []} onChange={(v) => update(i, "bullets", v)} placeholder="Describe a key aspect or achievement…" />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Technologies</Label>
              <ChipTagInput value={proj.technologies ?? []} onChange={(v) => update(i, "technologies", v)} placeholder="Python, FastAPI, Docker…" />
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Project
      </Button>
    </div>
  );
}
