import type { UseFormReturn } from "react-hook-form";
import { Label } from "@/components/ui/label";
import { ChipTagInput } from "../editor/ChipTagInput";
import { ProficiencySelector } from "../editor/ProficiencySelector";
import type { ResumeUpdate, ProficiencyLevel } from "@/lib/resume-schema";

interface SkillsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function SkillsSection({ form }: SkillsSectionProps) {
  const { watch, setValue } = form;
  const skills = watch("parsed_data.skills") ?? [];

  // Keep flat skill list in sync with chip input (name-only)
  const skillNames = skills.map((s) => s.name);

  const handleTagChange = (names: string[]) => {
    // Preserve proficiency/category for existing skills, add blank for new ones
    const updated = names.map((name) => {
      const existing = skills.find((s) => s.name === name);
      return existing ?? { name, proficiency: undefined, category: undefined };
    });
    setValue("parsed_data.skills", updated);
  };

  const updateProficiency = (index: number, proficiency: ProficiencyLevel | undefined) => {
    const updated = [...skills];
    updated[index] = { ...updated[index], proficiency };
    setValue("parsed_data.skills", updated);
  };

  return (
    <div className="space-y-6">
      {/* Flat skill chip input */}
      <div className="space-y-2">
        <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          Skills
        </Label>
        <ChipTagInput
          value={skillNames}
          onChange={handleTagChange}
          placeholder="Type a skill and press Enter or comma…"
        />
        <p className="text-[11px] text-muted-foreground/50">
          Press Enter or comma to add · Backspace removes the last chip
        </p>
      </div>

      {/* Proficiency per skill */}
      {skills.length > 0 && (
        <div className="space-y-2">
          <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
            Proficiency Levels
          </Label>
          <div className="space-y-2">
            {skills.map((skill, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-muted/20 border border-border/20">
                <span className="text-sm font-medium">{skill.name}</span>
                <ProficiencySelector
                  value={skill.proficiency as ProficiencyLevel | undefined}
                  onChange={(v) => updateProficiency(i, v)}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
