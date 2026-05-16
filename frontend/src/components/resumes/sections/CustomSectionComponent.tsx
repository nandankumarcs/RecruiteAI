import type { UseFormReturn } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { SectionCard } from "../editor/SectionCard";
import { DateTextInput } from "../editor/DateTextInput";
import { UrlInput } from "../editor/UrlInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface CustomSectionComponentProps {
  form: UseFormReturn<ResumeUpdate>;
  sectionIndex: number;
  onRemoveSection: () => void;
}

export function CustomSectionComponent({ form, sectionIndex, onRemoveSection }: CustomSectionComponentProps) {
  const { watch, setValue } = form;
  const customSections = watch("parsed_data.custom_sections") ?? [];
  const section = customSections[sectionIndex];
  if (!section) return null;

  const update = (field: string, value: unknown) => {
    const next = [...customSections];
    next[sectionIndex] = { ...next[sectionIndex], [field]: value };
    setValue("parsed_data.custom_sections", next);
  };

  const updateItem = (itemIndex: number, field: string, value: unknown) => {
    const items = [...(section.items ?? [])];
    items[itemIndex] = { ...items[itemIndex], [field]: value };
    update("items", items);
  };

  const addItem = () => update("items", [...(section.items ?? []), {}]);
  const removeItem = (i: number) => update("items", section.items?.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-3">
      {/* Editable section title */}
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <Input
            value={section.section_title}
            onChange={(e) => update("section_title", e.target.value)}
            placeholder="Section Title (e.g. Patents, Awards, Media)"
            className="h-9 bg-background/50 border-border/40 font-semibold"
          />
        </div>
        <button type="button" onClick={onRemoveSection} className="text-muted-foreground hover:text-destructive transition-colors shrink-0" title="Remove section">
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      {/* Items */}
      {(section.items ?? []).map((item, j) => (
        <SectionCard
          key={j}
          title={item.title || item.subtitle || `Item ${j + 1}`}
          subtitle={item.date}
          defaultExpanded={!item.title}
          onRemove={() => removeItem(j)}
        >
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Title</Label>
                <Input value={item.title ?? ""} onChange={(e) => updateItem(j, "title", e.target.value)} placeholder="Item title" className="h-9 bg-background/50 border-border/40" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Date</Label>
                <DateTextInput value={item.date} onChange={(v) => updateItem(j, "date", v)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Subtitle</Label>
              <Input value={item.subtitle ?? ""} onChange={(e) => updateItem(j, "subtitle", e.target.value)} placeholder="Subtitle or role" className="h-9 bg-background/50 border-border/40" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Description</Label>
              <Textarea value={item.description ?? ""} onChange={(e) => updateItem(j, "description", e.target.value)} rows={2} className="bg-background/50 border-border/40 resize-none" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">URL</Label>
              <UrlInput value={item.url} onChange={(v) => updateItem(j, "url", v)} />
            </div>
          </div>
        </SectionCard>
      ))}

      <Button type="button" variant="ghost" size="sm" onClick={addItem} className="h-8 text-xs gap-1.5 text-muted-foreground">
        <Plus className="h-3 w-3" /> Add item
      </Button>
    </div>
  );
}
