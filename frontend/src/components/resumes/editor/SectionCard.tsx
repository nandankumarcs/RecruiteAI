import { useState } from "react";
import { ChevronDown, ChevronUp, GripVertical, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface SectionCardProps {
  title: string;
  subtitle?: string;
  defaultExpanded?: boolean;
  onRemove?: () => void;
  children: React.ReactNode;
  className?: string;
}

/**
 * Collapsible card used for each repeating item in a section
 * (one per experience entry, one per education entry, etc.).
 */
export function SectionCard({
  title,
  subtitle,
  defaultExpanded = false,
  onRemove,
  children,
  className,
}: SectionCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div
      className={cn(
        "rounded-xl border border-border/40 bg-card/60 backdrop-blur-sm overflow-hidden transition-shadow hover:shadow-md",
        className
      )}
    >
      {/* Card header */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer select-none group"
        onClick={() => setExpanded((e) => !e)}
      >
        <GripVertical className="h-4 w-4 text-muted-foreground/30 shrink-0 cursor-grab" />
        <div className="flex-1 min-w-0">
          <p className={cn("text-sm font-semibold truncate", !title && "text-muted-foreground/50 italic")}>
            {title || "Untitled"}
          </p>
          {subtitle && (
            <p className="text-xs text-muted-foreground/70 truncate mt-0.5">{subtitle}</p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {onRemove && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded text-muted-foreground hover:text-destructive transition-all"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground/50" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground/50" />
          )}
        </div>
      </div>

      {/* Card body */}
      {expanded && (
        <div className="px-5 pb-5 pt-1 border-t border-border/30 space-y-4">
          {children}
        </div>
      )}
    </div>
  );
}
