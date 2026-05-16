import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Present",
  "Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026",
  "Jan 2025", "Jun 2025", "Sep 2025", "Dec 2025",
  "Jan 2024", "Jun 2024", "Sep 2024", "Dec 2024",
  "2026", "2025", "2024", "2023", "2022", "2021", "2020",
];

interface DateTextInputProps {
  value: string | undefined;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Free-form date text input.
 * Resume dates are stored as strings (e.g. "Jan 2024", "2024", "Present").
 * Shows a datalist for quick autocompletion.
 */
export function DateTextInput({
  value,
  onChange,
  placeholder = "e.g. Jan 2024",
  className,
  disabled,
}: DateTextInputProps) {
  const listId = `date-suggestions-${Math.random().toString(36).slice(2, 6)}`;

  return (
    <>
      <Input
        list={listId}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={cn("h-9 bg-background/50 border-border/40", className)}
        autoComplete="off"
      />
      <datalist id={listId}>
        {SUGGESTIONS.map((s) => (
          <option key={s} value={s} />
        ))}
      </datalist>
    </>
  );
}
