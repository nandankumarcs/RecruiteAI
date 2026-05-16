import type { UseFormReturn } from "react-hook-form";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard } from "../editor/SectionCard";
import { DraggableList } from "../editor/DraggableList";
import { LanguageProficiencySelector } from "../editor/ProficiencySelector";
import type { ResumeUpdate } from "@/lib/resume-schema";
import { LANGUAGE_PROFICIENCY } from "@/lib/resume-schema";

interface LanguagesSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function LanguagesSection({ form }: LanguagesSectionProps) {
  const { watch, setValue } = form;
  const languages = watch("parsed_data.languages") ?? [];

  const add = () => {
    setValue("parsed_data.languages", [
      ...languages,
      { language: "", proficiency: "Conversational" },
    ]);
  };

  const remove = (i: number) => {
    setValue("parsed_data.languages", languages.filter((_, idx) => idx !== i));
  };

  const update = (i: number, field: string, value: string) => {
    const next = [...languages];
    next[i] = { ...next[i], [field]: value };
    setValue("parsed_data.languages", next);
  };

  return (
    <div className="space-y-3">
      <DraggableList
        items={languages}
        getKey={(_, i) => `lang-${i}`}
        onReorder={(reordered) => setValue("parsed_data.languages", reordered)}
        renderItem={(lang, i) => (
        <SectionCard
          title={lang.language || "Language"}
          subtitle={lang.proficiency}
          defaultExpanded={!lang.language}
          onRemove={() => remove(i)}
        >
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Language</Label>
              <Input
                value={lang.language}
                onChange={(e) => update(i, "language", e.target.value)}
                placeholder="e.g. Spanish"
                className="h-9 bg-background/50 border-border/40"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Proficiency</Label>
              <LanguageProficiencySelector
                value={lang.proficiency}
                onChange={(v) => update(i, "proficiency", v)}
              />
              <div className="flex gap-2 flex-wrap mt-2">
                {LANGUAGE_PROFICIENCY.map((level) => (
                  <button
                    key={level}
                    type="button"
                    onClick={() => update(i, "proficiency", level)}
                    className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                      lang.proficiency === level
                        ? "bg-primary/10 border-primary/40 text-primary font-semibold"
                        : "border-border/30 text-muted-foreground hover:border-primary/30"
                    }`}
                  >
                    {level}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </SectionCard>
      )}

      />

      <Button type="button" variant="outline" size="sm" onClick={add} className="w-full h-10 border-dashed border-border/50 text-muted-foreground hover:text-foreground gap-2">
        <Plus className="h-4 w-4" /> Add Language
      </Button>
    </div>
  );
}
