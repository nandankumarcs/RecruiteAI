import type { ReactNode } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, ChevronUp, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export interface ColumnDef<T> {
  key: string;
  label: string;
  /** If set, clicking the header sorts by this key */
  sortKey?: string;
  headerClassName?: string;
  className?: string;
  cell: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  rowKey: (row: T) => string;
  // sorting
  sortBy: string;
  sortOrder: "asc" | "desc";
  onSortChange: (sortBy: string, sortOrder: "asc" | "desc") => void;
  // pagination
  currentPage: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  // empty state
  emptyIcon?: ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
  // optional row className
  rowClassName?: (row: T) => string;
}

function SortIcon({ active, order }: { active: boolean; order: "asc" | "desc" }) {
  if (!active) return <ChevronsUpDown className="h-3 w-3 opacity-40" />;
  return order === "asc"
    ? <ChevronUp className="h-3 w-3 text-primary" />
    : <ChevronDown className="h-3 w-3 text-primary" />;
}

function Pagination({
  currentPage,
  totalPages,
  totalItems,
  onPageChange,
  label,
}: {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  label: string;
}) {
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1)
    .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
    .reduce<(number | "...")[]>((acc, p, idx, arr) => {
      if (idx > 0 && p - (arr[idx - 1] as number) > 1) acc.push("...");
      acc.push(p);
      return acc;
    }, []);

  return (
    <div className="flex items-center justify-between px-2 py-1 text-xs font-bold text-muted-foreground">
      <span className="uppercase tracking-widest">
        Page {currentPage} of {totalPages} &mdash; {totalItems} {label}
      </span>
      <div className="flex items-center gap-1">
        {(
          [
            { icon: ChevronsLeft, page: 1, disabled: currentPage === 1 },
            { icon: ChevronLeft, page: currentPage - 1, disabled: currentPage === 1 },
          ] as const
        ).map(({ icon: Icon, page, disabled }, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPageChange(page)}
            disabled={disabled}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-muted/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}

        {pages.map((item, idx) =>
          item === "..." ? (
            <span key={`ellipsis-${idx}`} className="h-8 w-8 flex items-center justify-center text-muted-foreground">
              …
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => onPageChange(item as number)}
              className={cn(
                "h-8 w-8 flex items-center justify-center rounded-lg transition-colors font-black tracking-tight",
                currentPage === item ? "bg-primary text-primary-foreground shadow-sm" : "hover:bg-muted/60"
              )}
            >
              {item}
            </button>
          )
        )}

        {(
          [
            { icon: ChevronRight, page: currentPage + 1, disabled: currentPage === totalPages },
            { icon: ChevronsRight, page: totalPages, disabled: currentPage === totalPages },
          ] as const
        ).map(({ icon: Icon, page, disabled }, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onPageChange(page)}
            disabled={disabled}
            className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-muted/60 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            <Icon className="h-4 w-4" />
          </button>
        ))}
      </div>
    </div>
  );
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  sortBy,
  sortOrder,
  onSortChange,
  currentPage,
  pageSize,
  totalItems,
  onPageChange,
  emptyIcon,
  emptyTitle = "No data",
  emptyDescription,
  rowClassName,
}: DataTableProps<T>) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  const handleHeaderClick = (col: ColumnDef<T>) => {
    if (!col.sortKey) return;
    if (sortBy === col.sortKey) {
      onSortChange(col.sortKey, sortOrder === "asc" ? "desc" : "asc");
    } else {
      onSortChange(col.sortKey, "desc");
    }
  };

  if (data.length === 0 && totalItems === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border/50 bg-card/20 py-16 text-center animate-in fade-in zoom-in duration-500">
        {emptyIcon && (
          <div className="mx-auto w-16 h-16 bg-muted/50 rounded-full flex items-center justify-center mb-4">
            {emptyIcon}
          </div>
        )}
        <h3 className="text-xl font-bold tracking-tight">{emptyTitle}</h3>
        {emptyDescription && (
          <p className="text-muted-foreground max-w-xs mx-auto mt-2">{emptyDescription}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {totalPages > 1 && (
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          totalItems={totalItems}
          onPageChange={onPageChange}
          label="rows"
        />
      )}

      <div className="overflow-hidden rounded-lg border border-border/50 bg-card/30 shadow-md backdrop-blur-sm">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="hover:bg-transparent border-border/40">
              {columns.map((col) => {
                const isSorted = sortBy === col.sortKey;
                const sortable = !!col.sortKey;
                return (
                  <TableHead
                    key={col.key}
                    onClick={sortable ? () => handleHeaderClick(col) : undefined}
                    className={cn(
                      "font-bold py-4 text-xs uppercase tracking-widest text-muted-foreground",
                      sortable && "cursor-pointer select-none hover:text-foreground transition-colors",
                      col.headerClassName
                    )}
                  >
                    {sortable ? (
                      <div className="flex items-center gap-1">
                        {col.label}
                        <SortIcon active={isSorted} order={sortOrder} />
                      </div>
                    ) : (
                      col.label
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row) => (
              <TableRow
                key={rowKey(row)}
                className={cn(
                  "group transition-all duration-200 hover:bg-primary/5 border-border/30",
                  rowClassName?.(row)
                )}
              >
                {columns.map((col) => (
                  <TableCell key={col.key} className={cn("py-4", col.className)}>
                    {col.cell(row)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
