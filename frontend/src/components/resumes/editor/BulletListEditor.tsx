import { GripVertical, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DraggableList } from "./DraggableList";

interface BulletListEditorProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Editable bullet list with add/remove and drag-to-reorder.
 * Used for Experience bullets, Project bullets, Volunteer bullets.
 */
export function BulletListEditor({
  value,
  onChange,
  placeholder = "Add a bullet point…",
  disabled,
}: BulletListEditorProps) {
  const update = (index: number, text: string) => {
    const next = [...value];
    next[index] = text;
    onChange(next);
  };

  const remove = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  const add = () => {
    onChange([...value, ""]);
  };

  return (
    <div className="space-y-2">
      <DraggableList
        items={value}
        getKey={(bullet, i) => `bullet-${i}-${bullet.slice(0, 8)}`}
        onReorder={onChange}
        gap="space-y-2"
        renderItem={(bullet, i) => (
          <div className="flex items-center gap-2 group" style={{ cursor: "default" }}>
            <GripVertical className="h-4 w-4 text-muted-foreground/40 shrink-0 cursor-grab" />
            <span className="text-muted-foreground/50 text-sm mt-0.5">•</span>
            <Input
              value={bullet}
              onChange={(e) => update(i, e.target.value)}
              placeholder={placeholder}
              disabled={disabled}
              className="h-9 bg-background/50 border-border/40 flex-1"
              onMouseDown={(e) => e.stopPropagation()}
            />
            {!disabled && (
              <button
                type="button"
                onClick={() => remove(i)}
                onMouseDown={(e) => e.stopPropagation()}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive shrink-0"
                tabIndex={-1}
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      />
      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={add}
          className="h-8 text-xs text-muted-foreground hover:text-foreground gap-1.5 pl-7"
        >
          <Plus className="h-3 w-3" />
          Add bullet
        </Button>
      )}
    </div>
  );
}
