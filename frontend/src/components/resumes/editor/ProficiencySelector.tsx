import { cn } from "@/lib/utils";
import { PROFICIENCY_LEVELS, type ProficiencyLevel } from "@/lib/resume-schema";

interface ProficiencySelectorProps {
  value: ProficiencyLevel | undefined;
  onChange: (value: ProficiencyLevel | undefined) => void;
  className?: string;
}

const COLORS: Record<ProficiencyLevel, string> = {
  Beginner: "bg-slate-400",
  Intermediate: "bg-blue-400",
  Advanced: "bg-violet-500",
  Expert: "bg-emerald-500",
};

/**
 * Four-dot visual proficiency selector for skills.
 * Clicking a filled dot cycles through levels; clicking the same level deselects.
 */
export function ProficiencySelector({ value, onChange, className }: ProficiencySelectorProps) {
  const currentIdx = value ? PROFICIENCY_LEVELS.indexOf(value) : -1;

  return (
    <div className={cn("flex items-center gap-1.5", className)} title={value ?? "No proficiency set"}>
      {PROFICIENCY_LEVELS.map((level, i) => (
        <button
          key={level}
          type="button"
          onClick={() => onChange(i === currentIdx ? undefined : level)}
          title={level}
          className={cn(
            "h-2.5 w-2.5 rounded-full border border-border/60 transition-all hover:scale-125",
            i <= currentIdx
              ? COLORS[level]
              : "bg-muted/40"
          )}
        />
      ))}
      {value && (
        <span className="text-[10px] text-muted-foreground/70 ml-0.5">{value}</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Language proficiency — 5-bar horizontal indicator
// ---------------------------------------------------------------------------

const LANG_LEVELS = ["Basic", "Conversational", "Professional", "Fluent", "Native"] as const;
type LangLevel = typeof LANG_LEVELS[number];

interface LanguageProficiencySelectorProps {
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export function LanguageProficiencySelector({ value, onChange, className }: LanguageProficiencySelectorProps) {
  const currentIdx = LANG_LEVELS.indexOf(value as LangLevel);

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {LANG_LEVELS.map((level, i) => (
        <button
          key={level}
          type="button"
          onClick={() => onChange(level)}
          title={level}
          className={cn(
            "h-4 w-6 rounded-sm border border-border/40 transition-all hover:opacity-80",
            i <= currentIdx
              ? "bg-primary"
              : "bg-muted/30"
          )}
        />
      ))}
      <span className="text-[11px] text-muted-foreground ml-1">{value}</span>
    </div>
  );
}
