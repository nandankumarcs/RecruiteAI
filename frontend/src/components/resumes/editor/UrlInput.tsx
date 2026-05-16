import { ExternalLink } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

interface UrlInputProps {
  value: string | undefined;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * URL text input with an open-in-new-tab icon button when a value is present.
 */
export function UrlInput({
  value,
  onChange,
  placeholder = "https://",
  className,
  disabled,
}: UrlInputProps) {
  const hasValue = !!value?.trim();

  return (
    <div className={cn("relative flex items-center", className)}>
      <Input
        type="url"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className={cn(
          "h-9 bg-background/50 border-border/40",
          hasValue && "pr-8"
        )}
      />
      {hasValue && (
        <a
          href={value}
          target="_blank"
          rel="noopener noreferrer"
          className="absolute right-2.5 text-muted-foreground hover:text-primary transition-colors"
          tabIndex={-1}
          title="Open link"
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      )}
    </div>
  );
}
