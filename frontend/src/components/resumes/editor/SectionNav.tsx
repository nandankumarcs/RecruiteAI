import { GripVertical, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { DraggableList } from "./DraggableList";

export interface NavSection {
  key: string;
  label: string;
  count?: number;
  icon?: React.ReactNode;
}

interface SectionNavProps {
  sections: NavSection[];
  activeKey: string;
  onSelect: (key: string) => void;
  onReorder?: (newSections: NavSection[]) => void;
  onAdd?: () => void;
  className?: string;
}

/**
 * Left-panel section navigator for the resume editor.
 * Shows section names with item counts; scroll-spy highlights the active one.
 */
export function SectionNav({
  sections,
  activeKey,
  onSelect,
  onReorder,
  onAdd,
  className,
}: SectionNavProps) {
  return (
    <nav
      className={cn(
        "flex flex-col gap-0.5 bg-muted/20 rounded-xl border border-border/30 p-2",
        className
      )}
    >
      <DraggableList
        items={sections}
        getKey={(s) => s.key}
        onReorder={(reordered) => onReorder?.(reordered)}
        gap="space-y-0.5"
        renderItem={(section) => (
          <button
            type="button"
            onClick={() => onSelect(section.key)}
            onMouseDown={(e) => e.stopPropagation()}
            className={cn(
              "flex items-center gap-2.5 w-full px-3 py-2 rounded-lg text-left text-sm transition-all",
              activeKey === section.key
                ? "bg-primary/10 text-primary font-semibold"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            )}
          >
            <GripVertical className="h-3.5 w-3.5 text-muted-foreground/30 shrink-0 cursor-grab" />
            <span className="flex-1 truncate">{section.label}</span>
            {section.count !== undefined && section.count > 0 && (
              <span
                className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                  activeKey === section.key
                    ? "bg-primary/20 text-primary"
                    : "bg-muted text-muted-foreground"
                )}
              >
                {section.count}
              </span>
            )}
          </button>
        )}
      />

      {onAdd && (
        <button
          type="button"
          onClick={onAdd}
          className="flex items-center gap-2 w-full px-3 py-2 mt-1 rounded-lg text-sm text-muted-foreground/60 hover:text-primary hover:bg-primary/5 border-t border-border/20 transition-all"
        >
          <Plus className="h-3.5 w-3.5" />
          Add section
        </button>
      )}
    </nav>
  );
}
