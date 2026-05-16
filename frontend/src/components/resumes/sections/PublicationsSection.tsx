import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { DateTextInput } from "../editor/DateTextInput";
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface PublicationsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function PublicationsSection({ form }: PublicationsSectionProps) {
  const { watch, setValue } = form;
  const publications = watch("parsed_data.publications") ?? [];

  const add = () => setValue("parsed_data.publications", [...publications, { title: "" }]);
  const remove = (i: number) => setValue("parsed_data.publications", publications.filter((_, idx) => idx !== i));
  const update = (i: number, field: string, value: unknown) => {
    const next = [...publications];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.publications", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={publications}
        getKey={(_, i) => `pub-${i}`}
        onReorder={(reordered) => setValue("parsed_data.publications", reordered)}
        renderItem={(pub, i) => (
        <SectionCard title={pub.title || "New Publication"} subtitle={pub.publisher} defaultExpanded={!pub.title} onRemove={() => remove(i)}>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Title *</Label>
              <Input value={pub.title} onChange={(e) => update(i, "title", e.target.value)} placeholder="Publication title" className="h-9 bg-background/50 border-border/40" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Publisher / Journal</Label>
                <Input value={pub.publisher ?? ""} onChange={(e) => update(i, "publisher", e.target.value)} placeholder="NeurIPS, ACM, O'Reilly…" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Date</Label>
                <DateTextInput value={pub.date} onChange={(v) => update(i, "date", v)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Authors</Label>
              <Input value={pub.authors ?? ""} onChange={(e) => update(i, "authors", e.target.value)} placeholder="Your Name, Co-Author Name…" className="h-9 bg-background/50 border-border/40" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">URL / DOI</Label>
              <UrlInput value={pub.url} onChange={(v) => update(i, "url", v)} placeholder="https://doi.org/..." />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Abstract / Description</Label>
              <Textarea value={pub.description ?? ""} onChange={(e) => update(i, "description", e.target.value)} rows={3} className="bg-background/50 border-border/40 resize-none" />
            </div>
          </div>
        </SectionCard>
      )}
      />
      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Publication
      </Button>
    </div>
  );
}
