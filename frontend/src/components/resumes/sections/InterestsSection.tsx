import type { UseFormReturn } from "react-hook-form";
import { Label } from "@/components/ui/label";
import { ChipTagInput } from "../editor/ChipTagInput";
import type { ResumeUpdate } from "@/lib/resume-schema";

interface InterestsSectionProps {
  form: UseFormReturn<ResumeUpdate>;
}

export function InterestsSection({ form }: InterestsSectionProps) {
  const { watch, setValue } = form;
  const interests = watch("parsed_data.interests") ?? [];

  return (
    <div className="space-y-2">
      <Label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
        Interests & Hobbies
      </Label>
      <ChipTagInput
        value={interests}
        onChange={(v) => setValue("parsed_data.interests", v)}
        placeholder="Open-source contributing, Chess, Rock climbing…"
      />
      <p className="text-[11px] text-muted-foreground/50">
        Add interests that highlight relevant passion areas for the role.
      </p>
    </div>
  );
}
