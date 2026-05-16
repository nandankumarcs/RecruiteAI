import { useRef, useState, useCallback } from "react";
import { cn } from "@/lib/utils";

interface DraggableListProps<T> {
  items: T[];
  getKey: (item: T, index: number) => string;
  onReorder: (newItems: T[]) => void;
  renderItem: (item: T, index: number) => React.ReactNode;
  className?: string;
  gap?: string;
}

/**
 * Drag-and-drop sortable list using pointer events (mouse / touch).
 *
 * Pointer events are used instead of the HTML5 DnD API because:
 *  - HTML5 `dragstart` cannot be triggered by scripted events (browser security).
 *  - Pointer events work on both desktop (mouse) and mobile (touch).
 *  - Playwright's mouse API can simulate them reliably for automated testing.
 *
 * Grab any item → drag over another → release to reorder.
 * The dragging item fades to 40 % opacity; a blue insertion bar shows the
 * drop position.
 */
export function DraggableList<T>({
  items,
  getKey,
  onReorder,
  renderItem,
  className,
  gap = "space-y-2",
}: DraggableListProps<T>) {
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [overIdx, setOverIdx] = useState<number | null>(null);

  // Refs hold mutable state accessible inside closure without stale captures.
  const dragIdxRef = useRef<number | null>(null);
  const overIdxRef = useRef<number | null>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);
  // Capture items at drag-start so the commit uses a consistent snapshot.
  const itemsSnapshot = useRef<T[]>([]);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>, index: number) => {
      // Only initiate from left-button / primary pointer
      if (e.button !== undefined && e.button !== 0) return;
      e.preventDefault();

      dragIdxRef.current = index;
      overIdxRef.current = index;
      itemsSnapshot.current = [...items];
      setDraggingIdx(index);
      setOverIdx(index);

      const onMove = (ev: PointerEvent) => {
        // Determine which row the pointer is currently over
        const els = itemRefs.current;
        for (let i = 0; i < els.length; i++) {
          const el = els[i];
          if (!el) continue;
          const { top, bottom } = el.getBoundingClientRect();
          const mid = (top + bottom) / 2;
          // Insert before or after based on midpoint
          if (ev.clientY < mid) {
            if (overIdxRef.current !== i) {
              overIdxRef.current = i;
              setOverIdx(i);
            }
            return;
          }
        }
        // Below all items → last position
        const last = els.length - 1;
        if (overIdxRef.current !== last) {
          overIdxRef.current = last;
          setOverIdx(last);
        }
      };

      const onUp = () => {
        const from = dragIdxRef.current;
        const to = overIdxRef.current;

        if (from !== null && to !== null && from !== to) {
          const next = [...itemsSnapshot.current];
          const [moved] = next.splice(from, 1);
          next.splice(to, 0, moved);
          onReorder(next);
        }

        dragIdxRef.current = null;
        overIdxRef.current = null;
        setDraggingIdx(null);
        setOverIdx(null);

        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
      };

      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    },
    [items, onReorder],
  );

  return (
    <div className={cn(gap, className)}>
      {items.map((item, i) => (
        <div
          key={getKey(item, i)}
          ref={(el) => { itemRefs.current[i] = el; }}
          onPointerDown={(e) => handlePointerDown(e, i)}
          className={cn(
            "transition-opacity duration-100 touch-none select-none",
            draggingIdx === i && "opacity-40",
          )}
        >
          {/* Drop-position indicator above this item */}
          {overIdx === i && draggingIdx !== null && draggingIdx !== i && (
            <div className="h-0.5 w-full bg-primary rounded-full mb-1 mx-1" />
          )}
          {renderItem(item, i)}
        </div>
      ))}
    </div>
  );
}
